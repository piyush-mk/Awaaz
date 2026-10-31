"""The counter brain: session carts, voice-agent tool execution and the propose/confirm/commit loop.

Used by routers/agent.py (voice), routers/cart.py (manual cart) and the /api/actions endpoints.

UTTERANCE PIPELINE (`run_utterance`)
  1. The rules parser result (fixtures.rules_tool_calls) is applied to the session cart at once
     and `cart_updated` is published on the `store` channel (<50 ms, before any LLM answers).
  1b. FAST PATH (settings.fast_path, default on): when the rules parser fully explains the utterance
     (`fast_path_ok`: every word is a matched item, quantity, unit, filler or known command; no
     udhaar/payment/price/undo/checkout words) the LLM is skipped and the reply is built at once
     (`source: "rules"`). Everything else continues below.
  2. The LLM tool-calling path (llm.complete_or_rules, 4 s budget) runs next. When a real model
     (sarvam / paytm) answers with tool calls, its result REPLACES the rules result for this
     utterance: the cart is restored to its pre-utterance state and the LLM calls are applied
     (so nothing is added twice). Rules/fixture answers are the same calls, so they are skipped.
  3. Cart edits (add_to_cart, remove_item, set_quantity) apply immediately and leave an audit row
     (PendingAction kind=cart_edit, status=confirmed) that "galat hai" can undo.
     Money and stock commits (checkout, split_payment, add_udhaar, record_khata_payment, restock,
     set_price) become PendingAction rows with status=proposed, resolved by
     POST /api/actions/{id}/confirm | /cancel or by saying "haan" / "galat hai".

SPEECH. Replies are worded by services/voice_style.py and never wait for TTS: the response carries
`speech {text, pace, pending, key, audio_url, ack}` (services/speech.py) and a finished clip is announced
by the `speech_ready` event on the `store` channel.

OTHER AGENTS' ACTION KINDS. `register_action_handler(kind, confirm, cancel=None)` (or a module
attribute `ACTION_HANDLERS = {kind: fn | {"confirm": fn, "cancel": fn}}` in routers.purchases,
routers.galla, routers.khata, routers.stock, routers.brief, routers.whatsapp, routers.admin) lets
a feature commit its own PendingAction kinds through the same endpoints. A handler is
`fn(db, action, body) -> dict | None` (sync or async); it must not commit (the caller does).
"""
from __future__ import annotations

import asyncio
import importlib
import inspect
import logging
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config import settings
from models import Cart as CartRow, Customer, MissedSale, PendingAction, Product
from schemas import Cart as CartSchema, CartLine, PendingActionOut
from services import (catalog, events, fixtures, invoicing, khata, llm, payments, phrases, pricing,
                      quantity, receipts, stock_ops, whatsapp)
from services import speech as speech_svc
from services import voice_style
from services.clock import now_local
from services.quantity import Qty
from services.types import ToolCall

log = logging.getLogger("awaaz.counter")

CART_EDITS = {"add_to_cart", "remove_item", "set_quantity", "add_usual"}
PROPOSALS = {"checkout", "split_payment", "add_udhaar", "record_khata_payment", "restock", "set_price"}
TOOL_ALIASES = {"set_qty": "set_quantity", "remove": "remove_item", "add": "add_to_cart",
                "add_item": "add_to_cart", "add_items": "add_to_cart", "bill": "checkout",
                "udhaar": "add_udhaar", "khata_payment": "record_khata_payment",
                "stock_in": "restock", "set_prices": "set_price"}


# ---------------------------------------------------------------------------
# cart storage and views
# ---------------------------------------------------------------------------


class CartView(CartSchema):
    """schemas.Cart plus UI conveniences."""

    customer: Optional[dict] = None
    item_count: int = 0
    weigh_instructions: list[str] = Field(default_factory=list)


def get_cart(db: Session, session_id: str, *, fresh_if_done: bool = False) -> CartRow:
    """The cart for a session, created on first use. With `fresh_if_done` a finished sale
    (checked out / cancelled) is reset so the next customer starts a new cart."""
    cart = db.get(CartRow, session_id)
    if cart is None:
        try:
            with db.begin_nested():  # savepoint: a lost race must not poison the whole request
                cart = CartRow(id=session_id, lines=[], status="open")
                db.add(cart)
                db.flush()
        except IntegrityError:
            # Two requests opened the same new session at once (React StrictMode, a fast double tap):
            # the other one won, so use the cart it created.
            cart = db.get(CartRow, session_id)
            if cart is None:
                raise
    elif fresh_if_done and cart.status != "open":
        reset_cart(cart)
    return cart


def reset_cart(cart: CartRow) -> None:
    cart.lines = []
    cart.status = "open"
    cart.invoice_id = None
    cart.customer_id = None


def read_lines(cart: CartRow) -> list[CartLine]:
    return [CartLine(**d) for d in (cart.lines or [])]


def write_lines(cart: CartRow, lines: list[CartLine]) -> None:
    cart.lines = [ln.model_dump() for ln in lines]


def reprice(db: Session, lines: list[CartLine]) -> pricing.InvoiceTotals:
    """Set every line_total from MRP-inclusive pricing and return GST-split totals."""
    comp = bool(invoicing.get_store(db).composition_scheme)
    priced = []
    for ln in lines:
        lt = pricing.price_line(ln.qty, ln.unit_price, ln.gst_rate, comp, ln.amount_rupees)
        ln.line_total = lt.total
        priced.append(lt)
    return pricing.totals_for_lines(priced, comp)


def customer_brief(c: Optional[Customer]) -> Optional[dict]:
    if c is None:
        return None
    return {"id": c.id, "name": c.name, "name_hi": c.name_hi, "phone": c.phone, "upi_id": c.upi_id,
            "balance": round(float(c.balance or 0.0), 2), "credit_limit": c.credit_limit,
            "late_payments": c.late_payments, "has_usual": bool(c.usual_basket)}


def cart_view(db: Session, cart: CartRow) -> CartView:
    lines = read_lines(cart)
    totals = reprice(db, lines)
    customer = db.get(Customer, cart.customer_id) if cart.customer_id else None
    return CartView(
        id=cart.id, lines=lines, customer_id=cart.customer_id, status=cart.status or "open",
        invoice_id=cart.invoice_id, total=totals.total, taxable_total=totals.taxable,
        cgst_total=totals.cgst, sgst_total=totals.sgst, updated_at=cart.updated_at,
        customer=customer_brief(customer), item_count=len(lines),
        weigh_instructions=[f"{ln.name}: {ln.weigh_instruction}" for ln in lines if ln.weigh_instruction])


def view_json(db: Session, cart: CartRow) -> dict:
    return jsonable_encoder(cart_view(db, cart))


def announce_cart(db: Session, cart: CartRow, **extra: Any) -> None:
    """Publish `cart_updated` on the store channel (commit first so readers see the data)."""
    events.publish("store", "cart_updated", {"session_id": cart.id, "cart": view_json(db, cart), **extra})


# ---------------------------------------------------------------------------
# lines from specs
# ---------------------------------------------------------------------------


def _num(x: Any) -> Optional[float]:
    try:
        return float(x) if x not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _qty_of(qty: Any, unit: Any, amount: Any) -> Optional[Qty]:
    amt = _num(amount)
    if amt is not None and amt > 0:
        return Qty(amt, "amount", raw=f"{amt:g} rupaye")
    q = _num(qty)
    if q is None:
        return None
    u = str(unit or "").strip().lower()
    kind, factor = quantity.UNITS.get(u, ("bare", 1.0)) if u else ("bare", 1.0)
    return Qty(q * factor, kind, unit=u or None, raw=f"{q:g} {u}".strip())


def line_from_spec(db: Session, index: catalog.CatalogIndex, spec: dict) -> Optional[CartLine]:
    """Build a priced CartLine from {product_id|name, qty?, unit?, amount_rupees?}; None if unknown."""
    q = _qty_of(spec.get("qty", spec.get("quantity")), spec.get("unit"), spec.get("amount_rupees",
                                                                                    spec.get("amount")))
    product: Optional[Product] = None
    score = 100.0
    pid = spec.get("product_id")
    if pid not in (None, ""):
        try:
            product = db.get(Product, int(pid))
        except (TypeError, ValueError):
            product = None
        if product is not None and not product.active:
            product = None
    name = str(spec.get("name") or spec.get("product") or "").strip()
    if product is None and name:
        cands = index.match_all(name)
        if cands:
            product = quantity.choose_product([p for p, _ in cands], q)
            score = cands[0][1]
        else:
            product, score = index.find_in_phrase(name)
    if product is None:
        return None
    return quantity.build_line(product, q, name or product.name, score)


def _recompute(ln: CartLine) -> None:
    if ln.amount_rupees is not None:
        ln.qty = quantity.amount_to_quantity(ln.amount_rupees, ln.unit_price)
        ln.line_total = round(ln.amount_rupees, 2)
    else:
        ln.line_total = round(ln.qty * ln.unit_price, 2)
    if ln.sell_mode == "loose" and ln.base_unit in ("kg", "l"):
        ln.weigh_instruction = quantity.weigh_instruction(ln.qty, ln.base_unit)


def merge_into(lines: list[CartLine], new: CartLine) -> None:
    """Add a line, merging into an existing line for the same product when possible."""
    for ln in lines:
        if new.product_id is not None and ln.product_id == new.product_id:
            if ln.amount_rupees is None and new.amount_rupees is None:
                ln.qty = round(ln.qty + new.qty, 3)
                _recompute(ln)
                return
            if ln.amount_rupees is not None and new.amount_rupees is not None:
                ln.amount_rupees = round(ln.amount_rupees + new.amount_rupees, 2)
                _recompute(ln)
                return
    lines.append(new)


def find_line(lines: list[CartLine], index: Optional[catalog.CatalogIndex], product_id: Any = None,
              name: str = "") -> Optional[CartLine]:
    pid = _num(product_id)
    if pid is not None:
        for ln in lines:
            if ln.product_id == int(pid):
                return ln
    name = (name or "").strip()
    if name:
        if index is not None:
            product, _ = index.find_in_phrase(name)
            if product is not None:
                for ln in lines:
                    if ln.product_id == product.id:
                        return ln
        n = catalog.normalize(name)
        for ln in lines:
            if n and (n in catalog.normalize(ln.name) or catalog.normalize(ln.name) in n):
                return ln
    return None


def set_line_qty(ln: CartLine, qty: float, unit: Any = None) -> None:
    """Set a line's quantity (grams/ml converted for loose goods); clears amount-based pricing."""
    u = str(unit or "").strip().lower()
    if u and ln.sell_mode == "loose":
        kind, factor = quantity.UNITS.get(u, ("bare", 1.0))
        if kind in ("weight", "volume"):
            qty = qty * factor
    ln.qty = round(float(qty), 3)
    ln.amount_rupees = None
    ln.flags = [f for f in ln.flags if f not in ("amount_rounded_to_whole_units", "default_qty")]
    _recompute(ln)


# ---------------------------------------------------------------------------
# customers and the usual basket (F16)
# ---------------------------------------------------------------------------


def lookup_customer(db: Session, customer_id: Any = None, upi_id: Optional[str] = None,
                    phone: Optional[str] = None, name: Optional[str] = None) -> Optional[Customer]:
    if customer_id not in (None, ""):
        return db.get(Customer, int(customer_id))
    if upi_id:
        c = db.query(Customer).filter(Customer.upi_id.ilike(upi_id.strip())).first()
        if c:
            return c
    if phone:
        digits = re.sub(r"\D", "", phone)[-10:]
        if digits:
            for c in db.query(Customer).filter(Customer.phone.isnot(None)).all():
                if re.sub(r"\D", "", c.phone or "").endswith(digits):
                    return c
    if name:
        c, _ = catalog.match_customer(db, name)
        return c
    return None


def usual_lines(db: Session, customer: Customer) -> list[CartLine]:
    lines: list[CartLine] = []
    for item in customer.usual_basket or []:
        product = db.get(Product, int(item.get("product_id", 0) or 0))
        if product is None or not product.active:
            continue
        qty = float(item.get("qty", 1) or 1)
        kind = "weight" if product.is_loose and product.base_unit == "kg" else \
            "volume" if product.is_loose and product.base_unit == "l" else "count"
        lines.append(quantity.build_line(product, Qty(qty, kind), product.name, 100.0))
    return lines


def usual_view(db: Session, customer: Customer) -> dict:
    lines = usual_lines(db, customer)
    totals = reprice(db, lines)
    return {"customer": customer_brief(customer), "lines": jsonable_encoder(lines),
            "total": totals.total, "prompt": f"{customer.name} ka usual?",
            "spoken_text": f"{customer.name} ka usual: " + ", ".join(
                receipts.spoken_item(ln) for ln in lines) + f". Kul ₹{receipts.fmt_money(totals.total)}."
            if lines else f"{customer.name} ka koi usual basket nahi hai."}


# ---------------------------------------------------------------------------
# tool schemas (OpenAI format) and the LLM prompt
# ---------------------------------------------------------------------------

_ITEM = {"type": "object", "properties": {
    "product_id": {"type": "integer", "description": "catalog id if known"},
    "name": {"type": "string", "description": "spoken product name"},
    "qty": {"type": "number"},
    "unit": {"type": "string", "description": "packet, kg, gram, litre, ml, dozen..."},
    "amount_rupees": {"type": "number", "description": "for 'Rs N ka X' loose sales"}}}


def _tool(name: str, desc: str, props: dict, required: tuple = ()) -> dict:
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props, "required": list(required)}}}


TOOLS = [
    _tool("add_to_cart", "Add items the customer asks for to the cart.",
          {"items": {"type": "array", "items": _ITEM}}, ("items",)),
    _tool("remove_item", "Remove a product from the cart.",
          {"product_id": {"type": "integer"}, "name": {"type": "string"}}),
    _tool("set_quantity", "Change the quantity of a product already in the cart ('Maggi teen nahi, do').",
          {"product_id": {"type": "integer"}, "name": {"type": "string"}, "qty": {"type": "number"},
           "unit": {"type": "string"}}, ("qty",)),
    _tool("checkout", "Customer is done; total the bill ('bas, kitna hua').", {}),
    _tool("split_payment", "Pay one bill in parts. Omit the part that is 'the rest'.",
          {"cash": {"type": "number"}, "upi": {"type": "number"}, "khata": {"type": "number"},
           "customer": {"type": "string"}}),
    _tool("add_udhaar", "Write credit (udhaar) into a customer's khata.",
          {"customer": {"type": "string"}, "amount": {"type": "number"}}, ("customer", "amount")),
    _tool("record_khata_payment", "A customer paid back some of their khata.",
          {"customer": {"type": "string"}, "amount": {"type": "number"}}, ("customer", "amount")),
    _tool("restock", "Add received stock to inventory.", {"items": {"type": "array", "items": _ITEM}},
          ("items",)),
    _tool("set_price", "Set today's selling price of a product.",
          {"product_id": {"type": "integer"}, "product": {"type": "string"}, "price": {"type": "number"},
           "unit": {"type": "string"}}, ("price",)),
    _tool("missed_sale", "A customer asked for something the shop does not have.",
          {"product": {"type": "string"}}, ("product",)),
    _tool("answer", "Reply in short Hinglish when no other tool fits.", {"text": {"type": "string"}},
          ("text",)),
]


def build_messages(db: Session, cart: CartRow, index: catalog.CatalogIndex, transcript: str,
                   context: str) -> list[dict]:
    cat = "\n".join(
        f"{p.id}|{p.name}|{p.name_hi}|{','.join(str(a) for a in (p.aliases or [])[:3])}|{p.unit}|"
        f"{p.sell_mode}|{p.price:g}" for p in index.products)
    cust = ", ".join(f"{c.id}:{c.name}" for c in db.query(Customer).order_by(Customer.id).limit(12)
                     if not (c.name or "").lower().startswith("walk-in"))
    lines = read_lines(cart)
    cart_txt = "; ".join(f"{ln.name} x{ln.qty:g} {ln.unit}" for ln in lines) or "empty"
    system = (
        f"You are Awaaz, the munim (clerk) of {settings.merchant_name}, a kirana store. The merchant and "
        f"customers speak Hinglish. Context: {context}. Understand the utterance and call tools; never "
        "invent products that are not in the catalog (use missed_sale for those). Amounts are in rupees. "
        "Loose goods (sell_mode=loose) are priced per kg/litre: 'bees rupaye ki cheeni' means "
        "amount_rupees=20. In context=stock use restock instead of add_to_cart. Reply with tool calls only; "
        "use answer for short replies.\n"
        f"CATALOG (id|name|hindi|aliases|unit|mode|price):\n{cat}\nCUSTOMERS: {cust}\nCART: {cart_txt}")
    return [{"role": "system", "content": system}, {"role": "user", "content": transcript}]


# ---------------------------------------------------------------------------
# extra rules the shared parser does not cover
# ---------------------------------------------------------------------------

_UNDO = {"galat", "undo", "cancel", "ruko", "rukiye", "रद्द", "गलत"}
_UNDO_FILL = {"hai", "kar", "do", "karo", "ye", "yeh", "sab", "bhai", "bhaiya", "ji", "wala", "nahi",
              "dijiye", "bilkul", "ruk", "jao"}
_NO = {"nahi", "nahin", "na", "no", "नहीं"}
_YES_CORE = {"haan", "han", "ha", "haa", "theek", "thik", "confirm", "yes", "ok", "okay", "bilkul",
             "sahi", "done", "हाँ", "हां", "ठीक"}
_YES_FILLER = {"ji", "hai", "kar", "do", "karo", "dijiye", "bilkul", "bhaiya", "to", "toh"}


def classify_control(norm: str) -> Optional[str]:
    """'undo' | 'no' | 'confirm' | None for short control phrases."""
    words = norm.split()
    if not words or len(words) > 4:
        return None
    if (set(words) & _UNDO and set(words) <= (_UNDO | _UNDO_FILL)) or "rehne do" in norm \
            or "reh ne do" in norm:
        return "undo"
    if len(words) <= 2 and set(words) <= (_NO | {"ji"}):
        return "no"
    if set(words) & _YES_CORE and set(words) <= (_YES_CORE | _YES_FILLER):
        return "confirm"
    return None


def first_number(norm: str, index: catalog.CatalogIndex) -> Optional[float]:
    toks = quantity._tokenize(norm.split(), index)
    for i, t in enumerate(toks):
        if t.kind in ("num", "mult", "frac", "pre", "numunit", "numrupee"):
            q, _ = quantity._read_qty(toks, i)
            if q is not None:
                return q.value
    return None


_PAID_BACK = re.compile(r"^(?P<name>.+?)\s+(?:ne|se)\s+(?P<rest>.+)$")
_PAID_WORDS = {"diye", "diya", "jama", "chukaye", "chukaya", "chuka", "wapas", "bhare", "bhara", "mile",
               "mila", "payment", "diye."}
_SET_PRICE = re.compile(r"^(?P<name>.+?)\s+(?:ka|ki)\s+(?:rate|bhav|bhaav|daam|dam|price)\s+(?P<rest>.+)$")
_USUAL = ("usual", "roz wala", "hamesha wala", "wahi roz", "रोज़ वाला", "रोज वाला")


_REMOVE = re.compile(r"^(?P<name>.+?)\s+(?:ko\s+)?(?:hata do|hatao|hata dijiye|hata de|nikal do|nikaal do|"
                     r"nikalo|cancel kar do|cancel karo|nahi chahiye|mat do|rehne do)$")
_FIX_NAHI = re.compile(r"^(?P<name>.+?)\s+nahi\s+(?P<new>.+)$")
_FIX_KARO = re.compile(r"^(?P<name>.+?)\s+(?:ko\s+)?(?P<new>.+?)\s+(?:kar do|karo|kar dijiye|kar de)$")


def _cart_fix(norm: str, index: catalog.CatalogIndex, lines: list[CartLine]) -> Optional[list[ToolCall]]:
    """'Maggi teen nahi, do' / 'Maggi do karo' -> set_quantity; 'Colgate hata do' -> remove_item.
    Only fires for products already in the cart."""
    def in_cart(phrase: str) -> Optional[CartLine]:
        product, _ = index.find_in_phrase(phrase)
        return next((ln for ln in lines if product is not None and ln.product_id == product.id), None)

    m = _REMOVE.match(norm)
    if m and (ln := in_cart(m.group("name"))):
        return [ToolCall("remove_item", {"product_id": ln.product_id, "name": ln.name})]
    for rx in (_FIX_NAHI, _FIX_KARO):
        m = rx.match(norm)
        if m and (ln := in_cart(m.group("name"))):
            qty = first_number(m.group("new"), index)
            if qty is not None:
                return [ToolCall("set_quantity", {"product_id": ln.product_id, "name": ln.name,
                                                  "qty": qty})]
    return None


def extra_rules(db: Session, norm: str, index: catalog.CatalogIndex,
                lines: Optional[list[CartLine]] = None) -> Optional[list[ToolCall]]:
    """Intents the shared rules parser does not know: cart fixes, khata payment, set price, usual."""
    if lines:
        fix = _cart_fix(norm, index, lines)
        if fix:
            return fix
    m = _PAID_BACK.match(norm)
    if m and set(m.group("rest").split()) & _PAID_WORDS:
        customer, _ = catalog.match_customer(db, m.group("name"))
        amt = first_number(m.group("rest"), index)
        if customer is not None and amt:
            return [ToolCall("record_khata_payment", {"customer": m.group("name"), "amount": amt,
                                                      "customer_id": int(customer.id)})]
    m = _SET_PRICE.match(norm)
    if m:
        product, _ = index.find_in_phrase(m.group("name"))
        price = first_number(m.group("rest"), index)
        if product is not None and price:
            return [ToolCall("set_price", {"product_id": int(product.id), "product": product.name,
                                           "price": price})]
    if any(w in norm for w in _USUAL):
        spoken = re.split(r"\s+(?:ka|ki|ke|ko|wala|usual)\b", norm)[0]
        customer, _ = catalog.match_customer(db, spoken) if spoken and "usual" not in spoken else (None, 0)
        return [ToolCall("add_usual", {"customer_id": int(customer.id) if customer else None})]
    return None


# ---------------------------------------------------------------------------
# tool execution
# ---------------------------------------------------------------------------


@dataclass
class Ctx:
    db: Session
    session_id: str
    cart: CartRow
    index: catalog.CatalogIndex
    context: str
    transcript: str
    source: str = "rules"
    latency_ms: int = 0


@dataclass
class Out:
    spoken: list[str] = field(default_factory=list)  # sentences from non-edit tools, in call order
    added: list[CartLine] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # remove / set_quantity sentences
    unmatched: list[str] = field(default_factory=list)
    missed: list[str] = field(default_factory=list)
    actions: list[PendingAction] = field(default_factory=list)
    applied: list[dict] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    money_proposed: bool = False
    paces: list[float] = field(default_factory=list)  # pace of every line said, for the combined reply

    def say(self, line: voice_style.Line, into: Optional[list[str]] = None) -> None:
        (self.spoken if into is None else into).append(line.text)
        self.paces.append(line.pace)


def canon(name: str) -> str:
    return TOOL_ALIASES.get(name, name)


def _items_of(args: dict) -> list[dict]:
    items = args.get("items")
    if isinstance(items, list) and items:
        return [i for i in items if isinstance(i, dict)]
    if args.get("name") or args.get("product_id") or args.get("product"):
        return [args]
    return []


def _qty_text(ln: CartLine) -> str:
    """'2', '450 gram', '1 kilo 500 gram', '2 litre' for a cart line, as it is said aloud."""
    spoken = receipts.spoken_item(ln)  # '<qty words> <name>'
    return spoken[: -len(ln.name)].strip() if spoken.endswith(ln.name) else f"{ln.qty:g}"


def _loose_line(ln: CartLine, session_id: Optional[str]) -> voice_style.Line:
    """'₹20 ki Cheeni, 450 gram. Tol dijiye.' from a line that has a weigh instruction."""
    instr = ln.weigh_instruction or ""
    qty_text, verb = instr, "Tol"
    for suffix, v in (" tolo", "Tol"), (" naap lo", "Naap"):
        if instr.endswith(suffix):
            qty_text, verb = instr[: -len(suffix)].strip(), v
    label = f"{_rs(ln.amount_rupees)} ki {ln.name}" if ln.amount_rupees else ln.name
    return voice_style.line("loose_item", session=session_id, label=label, name=ln.name,
                            qty_text=qty_text, verb=verb)


def apply_cart_edit(ctx: Ctx, call: ToolCall, out: Out) -> None:
    name = canon(call.name)
    args = call.arguments or {}
    lines = read_lines(ctx.cart)
    if name == "add_to_cart":
        for spec in _items_of(args):
            ln = line_from_spec(ctx.db, ctx.index, spec)
            if ln is None:
                out.unmatched.append(str(spec.get("name") or spec.get("product") or "").strip())
                continue
            merge_into(lines, ln)
            out.added.append(ln)
        out.applied.append({"tool": name, "count": len(out.added)})
    elif name == "remove_item":
        target = find_line(lines, ctx.index, args.get("product_id"), str(args.get("name") or args.get("product") or ""))
        if target is None:
            out.say(voice_style.line("nothing_understood", session=ctx.session_id), out.notes)
        else:
            lines.remove(target)
            out.say(voice_style.line("item_removed", session=ctx.session_id, name=target.name), out.notes)
            out.applied.append({"tool": name, "product_id": target.product_id})
    elif name == "set_quantity":
        target = find_line(lines, ctx.index, args.get("product_id"), str(args.get("name") or args.get("product") or ""))
        qty = _num(args.get("qty", args.get("quantity")))
        if target is None or qty is None:
            out.say(voice_style.line("nothing_understood", session=ctx.session_id), out.notes)
        elif qty <= 0:
            lines.remove(target)
            out.say(voice_style.line("item_removed", session=ctx.session_id, name=target.name), out.notes)
            out.applied.append({"tool": name, "product_id": target.product_id, "qty": 0})
        else:
            set_line_qty(target, qty, args.get("unit"))
            out.say(voice_style.line("qty_changed", session=ctx.session_id, name=target.name,
                                     qty_text=_qty_text(target)), out.notes)
            if target.weigh_instruction:
                out.say(_loose_line(target, ctx.session_id), out.notes)
            out.applied.append({"tool": name, "product_id": target.product_id, "qty": target.qty})
    elif name == "add_usual":
        customer = lookup_customer(ctx.db, args.get("customer_id")) if args.get("customer_id") else (
            ctx.db.get(Customer, ctx.cart.customer_id) if ctx.cart.customer_id else None)
        if customer is None or not customer.usual_basket:
            out.say(voice_style.line("ask_customer", session=ctx.session_id), out.notes)
        else:
            for ln in usual_lines(ctx.db, customer):
                merge_into(lines, ln)
                out.added.append(ln)
            ctx.cart.customer_id = customer.id
            out.applied.append({"tool": name, "customer_id": customer.id})
    reprice(ctx.db, lines)
    write_lines(ctx.cart, lines)
    out.tools.append(name)


def resolve_customer(ctx: Ctx, args: dict) -> Optional[Customer]:
    cid = _num(args.get("customer_id"))
    if cid is not None:
        c = ctx.db.get(Customer, int(cid))
        if c:
            return c
    spoken = args.get("customer") or args.get("name")
    if spoken:
        c, _ = catalog.match_customer(ctx.db, str(spoken))
        if c:
            return c
    if not spoken and ctx.cart.customer_id:
        return ctx.db.get(Customer, ctx.cart.customer_id)
    return None


def propose(ctx: Ctx, out: Out, kind: str, payload: dict, supersede: tuple = ()) -> PendingAction:
    for old in ctx.db.query(PendingAction).filter(
            PendingAction.session_id == ctx.session_id, PendingAction.status == "proposed",
            PendingAction.kind.in_(supersede or ("__none__",))).all():
        old.status = "cancelled"
        old.resolved_at = now_local()
    action = PendingAction(kind=kind, payload=jsonable_encoder(payload), status="proposed",
                           source=ctx.source, latency_ms=ctx.latency_ms, session_id=ctx.session_id)
    ctx.db.add(action)
    ctx.db.flush()
    out.actions.append(action)
    return action


def _rs(x: float) -> str:
    return f"₹{receipts.fmt_money(x)}"


def apply_other(ctx: Ctx, call: ToolCall, out: Out) -> None:
    name = canon(call.name)
    args = call.arguments or {}
    db = ctx.db
    out.tools.append(name)
    sid = ctx.session_id

    if name == "checkout":
        lines = read_lines(ctx.cart)
        if not lines:
            out.say(voice_style.line("cart_empty", session=sid))
            return
        totals = reprice(db, lines)
        customer = resolve_customer(ctx, args) if (args.get("customer") or args.get("customer_id")) else None
        if customer:
            ctx.cart.customer_id = customer.id
        propose(ctx, out, "checkout", {
            "session_id": ctx.session_id, "total": totals.total, "item_count": len(lines),
            "customer_id": ctx.cart.customer_id,
            "summary": f"Bill {_rs(totals.total)}, {len(lines)} items"}, ("checkout", "split_payment"))
        out.money_proposed = True
        out.say(voice_style.line("confirm_needed", session=sid, total=totals.total))

    elif name == "split_payment":
        lines = read_lines(ctx.cart)
        if not lines:
            out.say(voice_style.line("cart_empty", session=sid))
            return
        totals = reprice(db, lines)
        splits = {k: _num(args.get(k)) for k in ("cash", "upi", "khata") if k in args}
        try:
            parts = payments.allocate(totals.total, splits)
        except HTTPException:
            out.say(voice_style.line("split_mismatch", session=sid, total=totals.total))
            return
        customer = resolve_customer(ctx, args)
        needs_customer = parts["khata"] > 0 and customer is None
        if customer:
            ctx.cart.customer_id = customer.id
        bits = [f"{_rs(parts[m])} {label}" for m, label in (("cash", "cash"), ("upi", "Paytm"),
                                                           ("khata", "khate mein")) if parts[m] > 0]
        propose(ctx, out, "split_payment", {
            "session_id": ctx.session_id, "total": totals.total, "parts": parts,
            "customer_id": customer.id if customer else ctx.cart.customer_id,
            "needs_customer": needs_customer,
            "summary": "Bill " + _rs(totals.total) + ": " + ", ".join(bits)}, ("checkout", "split_payment"))
        out.money_proposed = True
        if needs_customer:
            out.say(voice_style.line("split_parts", session=sid, total=totals.total, parts=", ".join(bits)))
            out.say(voice_style.line("ask_khata_customer", session=sid))
        else:
            out.say(voice_style.line("split_summary", session=sid, total=totals.total,
                                     parts=", ".join(bits)))

    elif name in ("add_udhaar", "record_khata_payment"):
        customer = resolve_customer(ctx, args)
        amount = _num(args.get("amount"))
        if customer is None:
            out.say(voice_style.line("ask_customer", session=sid))
            return
        if not amount or amount <= 0:
            out.say(voice_style.line("ask_amount", session=sid, customer=customer.name))
            return
        bal = khata.balance(db, customer.id)
        if name == "add_udhaar":
            after = round(bal + amount, 2)
            limit = float(customer.credit_limit or 0.0)
            late = int(customer.late_payments or 0)
            suggested = max(500.0, round(limit * (1 - 0.25 * late) / 50.0) * 50.0)
            over = after > limit
            payload = {"customer_id": customer.id, "customer_name": customer.name, "amount": amount,
                       "balance_before": bal, "balance_after": after, "credit_limit": limit,
                       "late_payments": late, "suggested_limit": suggested, "over_limit": over,
                       "risk": "high" if over or late >= 3 else "low",
                       "summary": f"{customer.name} ke khate mein {_rs(amount)}"}
            msg = voice_style.line("udhaar_over_limit" if over else "udhaar_proposed", session=sid,
                                   customer=customer.name, amount=amount)
            propose(ctx, out, "add_udhaar", payload)
        else:
            after = round(bal - amount, 2)
            payload = {"customer_id": customer.id, "customer_name": customer.name, "amount": amount,
                       "balance_before": bal, "balance_after": after,
                       "summary": f"{customer.name} se {_rs(amount)} mile"}
            msg = voice_style.line("khata_payment", session=sid, customer=customer.name, amount=amount)
            propose(ctx, out, "record_khata_payment", payload)
        out.money_proposed = True
        out.say(msg)

    elif name == "restock":
        items = []
        for spec in _items_of(args):
            ln = line_from_spec(db, ctx.index, {**spec, "amount_rupees": None})
            if ln is None:
                out.unmatched.append(str(spec.get("name") or spec.get("product") or "").strip())
                continue
            items.append({"product_id": ln.product_id, "name": ln.name, "name_hi": ln.name_hi,
                          "quantity": ln.qty, "unit": ln.unit})
        if not items:
            out.say(voice_style.line("restock_ask", session=sid))
            return
        spoken_items = ", ".join(
            f"{i['quantity']:g} {i['unit']} {i['name']}" if i["unit"] in ("kg", "litre")
            else f"{i['quantity']:g} {i['name']}" for i in items)
        propose(ctx, out, "restock", {"items": items, "summary": f"Stock in: {spoken_items}"})
        out.money_proposed = True
        out.say(voice_style.line("restock_proposed", session=sid, items=spoken_items))

    elif name == "set_price":
        price = _num(args.get("price"))
        product = db.get(Product, int(args["product_id"])) if _num(args.get("product_id")) else None
        if product is None and (args.get("product") or args.get("name")):
            product, _ = ctx.index.find_in_phrase(str(args.get("product") or args.get("name")))
        if product is None or not price or price <= 0:
            out.say(voice_style.line("price_ask", session=sid))
            return
        unit = "kg" if product.is_loose and product.base_unit == "kg" else \
            "litre" if product.is_loose and product.base_unit == "l" else product.unit
        propose(ctx, out, "set_price", {"product_id": product.id, "name": product.name, "unit": unit,
                                        "old_price": product.price, "new_price": price,
                                        "summary": f"{product.name} ka rate {_rs(product.price)} se {_rs(price)}"})
        out.money_proposed = True
        out.say(voice_style.line("price_proposed", session=sid, name=product.name, old_price=product.price,
                                 new_price=price, unit=unit))

    elif name == "missed_sale":
        pname = str(args.get("product") or args.get("name") or "").strip()
        if pname and pname.lower() not in [m.lower() for m in out.missed]:
            product = db.get(Product, int(args["product_id"])) if _num(args.get("product_id")) else None
            db.add(MissedSale(product_name=pname.title() if pname.islower() else pname,
                              product_id=product.id if product else None))
            out.missed.append(pname)
            out.say(voice_style.line("missed_sale", session=sid, name=pname.title()))

    elif name == "answer":
        text = str(args.get("text") or "").strip()
        if text:
            out.spoken.append(text)
            out.paces.append(voice_style.pace_for(None, text))


def compose_spoken(db: Session, ctx: Ctx, out: Out, cart_changed: bool) -> tuple[str, float]:
    """The reply for one utterance: (text, pace). Weigh-out instructions first (the merchant has to
    act on them), then what was added with the running total, then notes and other tools' sentences."""
    sid = ctx.session_id
    parts: list[str] = []
    paces: list[float] = list(out.paces)
    total_said = False
    plain = [ln for ln in out.added if not ln.weigh_instruction]
    for ln in out.added:
        if ln.weigh_instruction:
            line = _loose_line(ln, sid)
            parts.append(line.text)
            paces.append(line.pace)
    lines_now = read_lines(ctx.cart)
    show_total = cart_changed and not out.money_proposed and bool(lines_now)
    if out.added:
        names = ", ".join(receipts.spoken_item(ln) for ln in plain)
        named = {"items": names} if plain and len(plain) <= 3 and len(names) <= 70 else {}
        if show_total:
            if plain:
                # Spoken confirmations stay short (TTS time grows with length): read the items back only when the
                # whole line is ~48 characters or less; otherwise the screen shows them and the voice says the total.
                line = voice_style.line("items_added", session=sid, total=reprice(db, lines_now).total,
                                        max_chars=48, **named)
            else:
                line = voice_style.line("total_now", session=sid, total=reprice(db, lines_now).total)
            total_said = True
        elif named:
            line = voice_style.line("items_noted", session=sid, **named)
        else:
            line = voice_style.line("generic_ok", session=sid)
        parts.append(line.text)
        paces.append(line.pace)
    parts.extend(out.notes)
    if cart_changed and not out.money_proposed and not total_said:
        if lines_now:
            line = voice_style.line("total_now", session=sid, total=reprice(db, lines_now).total)
        else:
            line = voice_style.line("cart_empty", session=sid)
        parts.append(line.text)
        paces.append(line.pace)
    parts.extend(out.spoken)
    text = voice_style.clip(" ".join(p for p in parts if p), 220)
    pace = max(0.93, min(paces)) if paces else voice_style.pace_for(None, text)
    return text, round(pace, 2)


# ---------------------------------------------------------------------------
# propose / confirm / commit
# ---------------------------------------------------------------------------

_HANDLERS: dict[str, dict[str, Callable]] = {}
_DISCOVERY = ("routers.purchases", "routers.galla", "routers.khata", "routers.stock", "routers.brief",
              "routers.whatsapp", "routers.admin")


def register_action_handler(kind: str, confirm: Callable, cancel: Optional[Callable] = None) -> None:
    """Register how another feature commits (and optionally cancels) its PendingAction kind."""
    _HANDLERS[kind] = {"confirm": confirm, **({"cancel": cancel} if cancel else {})}


def _handler(kind: str, which: str) -> Optional[Callable]:
    if kind in _HANDLERS and which in _HANDLERS[kind]:
        return _HANDLERS[kind][which]
    for modname in _DISCOVERY:
        mod = sys.modules.get(modname)
        if mod is None:
            try:
                mod = importlib.import_module(modname)
            except Exception:  # noqa: BLE001  (another agent's module may be broken or absent)
                continue
        table = getattr(mod, "ACTION_HANDLERS", None)
        if isinstance(table, dict) and kind in table:
            h = table[kind]
            if isinstance(h, dict):
                return h.get(which)
            return h if which == "confirm" else None
    return None


async def _call(fn: Callable, *args: Any) -> Any:
    res = fn(*args)
    return await res if inspect.isawaitable(res) else res


def action_json(action: PendingAction) -> dict:
    return PendingActionOut.model_validate(action).model_dump(mode="json")


def _wa(db: Session, customer: Customer, body: str) -> bool:
    if not customer.phone:
        return False
    whatsapp.notify(db, customer.phone, body, type="text", customer_id=customer.id)
    return True


def _inr(x: float) -> str:
    """Indian digit grouping for messages: 1350 -> '1,350', 123456 -> '1,23,456'."""
    n = int(round(abs(x)))
    s = str(n)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups + [tail])
    return ("-" if x < 0 else "") + s


async def _commit_checkout(db: Session, action: PendingAction, body: dict) -> dict:
    cart = db.get(CartRow, action.payload.get("session_id"))
    if cart is None:
        raise HTTPException(404, "Cart nahi mila")
    res = await payments.checkout_cart(db, cart, customer_id=body.get("customer_id") or
                                       action.payload.get("customer_id"))
    return res


async def _commit_split(db: Session, action: PendingAction, body: dict) -> dict:
    cart = db.get(CartRow, action.payload.get("session_id"))
    if cart is None:
        raise HTTPException(404, "Cart nahi mila")
    cid = body.get("customer_id") or action.payload.get("customer_id") or cart.customer_id
    parts = action.payload.get("parts") or {}
    if parts.get("khata", 0) > 0 and not cid:
        raise HTTPException(400, "Khate ke liye customer_id chahiye (body: {\"customer_id\": N})")
    return await payments.checkout_cart(db, cart, splits={**parts, "customer_id": cid}, customer_id=cid)


def _commit_udhaar(db: Session, action: PendingAction, body: dict) -> dict:
    p = action.payload
    entry = khata.add_credit(db, p["customer_id"], p["amount"], note="Udhaar (voice)")
    customer = db.get(Customer, p["customer_id"])
    bal = khata.balance(db, p["customer_id"])
    sent = _wa(db, customer, f"₹{_inr(p['amount'])} aapke khate mein jude. Kul baaki ₹{_inr(bal)}. "
                             "Galat ho toh reply karein.")
    if sent:
        entry.wa_status = "queued"
    return {"entry_id": entry.id, "balance": bal, "whatsapp": sent,
            "spoken_text": voice_style.line("udhaar_confirmed", session=action.session_id,
                                            customer=customer.name, amount=p["amount"],
                                            balance=bal).text}


def _commit_khata_payment(db: Session, action: PendingAction, body: dict) -> dict:
    p = action.payload
    entry = khata.record_payment(db, p["customer_id"], p["amount"], note="Payment (voice)")
    customer = db.get(Customer, p["customer_id"])
    bal = khata.balance(db, p["customer_id"])
    sent = _wa(db, customer, f"₹{_inr(p['amount'])} mil gaye. Kul baaki ₹{_inr(max(bal, 0))}. Dhanyavaad.")
    return {"entry_id": entry.id, "balance": bal, "whatsapp": sent,
            "spoken_text": voice_style.line("khata_payment_done", session=action.session_id,
                                            customer=customer.name, amount=p["amount"],
                                            balance=max(bal, 0)).text}


def _commit_restock(db: Session, action: PendingAction, body: dict) -> dict:
    updated = []
    for it in action.payload.get("items", []):
        before = stock_ops.current_stock(db, it["product_id"])
        stock_ops.add_stock(db, it["product_id"], float(it["quantity"]), kind="restock",
                            ref=f"action:{action.id}", note="voice stock-in")
        updated.append({"product_id": it["product_id"], "name": it["name"], "unit": it.get("unit", ""),
                        "old_quantity": before, "new_quantity": round(before + float(it["quantity"]), 3)})
    db.flush()
    text = ", ".join(f"{u['name']} {u['new_quantity']:g}" for u in updated[:3])
    if len(updated) > 3:
        text += f" aur {len(updated) - 3} aur"
    return {"updated": updated,
            "spoken_text": voice_style.line("restock_done", session=action.session_id, items=text).text}


def _commit_set_price(db: Session, action: PendingAction, body: dict) -> dict:
    p = action.payload
    product = db.get(Product, p["product_id"])
    if product is None:
        raise HTTPException(404, "Product nahi mila")
    new = float(p["new_price"])
    product.mrp = new
    if product.is_loose:
        product.loose_price_per_base = new
    return {"product_id": product.id, "price": new,
            "spoken_text": voice_style.line("price_done", session=action.session_id, name=product.name,
                                            price=new).text}


for _kind, _fn in (("checkout", _commit_checkout), ("split_payment", _commit_split),
                   ("add_udhaar", _commit_udhaar), ("record_khata_payment", _commit_khata_payment),
                   ("restock", _commit_restock), ("set_price", _commit_set_price)):
    register_action_handler(_kind, _fn)


async def resolve_action(db: Session, action_id: int, decision: str, body: Optional[dict] = None,
                         speak: bool = True) -> dict:
    """Confirm or cancel a PendingAction. Returns {action, result, spoken_text, audio_url, cart?}."""
    body = body or {}
    action = db.get(PendingAction, action_id)
    if action is None:
        raise HTTPException(404, f"Action {action_id} nahi mila")
    result: dict = {}
    already = False
    if decision == "confirm":
        if action.status == "confirmed":
            already = True
            result = dict(action.result or {})
        elif action.status == "cancelled":
            raise HTTPException(409, "Yeh action cancel ho chuka hai")
        else:
            fn = _handler(action.kind, "confirm")
            if fn is None:
                raise HTTPException(501, f"'{action.kind}' ke liye commit handler register nahi hai")
            result = await _call(fn, db, action, body) or {}
            action.status = "confirmed"
            action.resolved_at = now_local()
            action.result = jsonable_encoder(result)
            db.commit()
    else:
        if action.status == "confirmed":
            raise HTTPException(409, "Yeh action confirm ho chuka hai, cancel nahi ho sakta")
        if action.status == "proposed":
            fn = _handler(action.kind, "cancel")
            if fn is not None:
                result = await _call(fn, db, action, body) or {}
            action.status = "cancelled"
            action.resolved_at = now_local()
            action.result = jsonable_encoder(result) or None
            db.commit()
        else:
            already = True
        result = result or {}
        result.setdefault("spoken_text", voice_style.line("action_cancelled", session=action.session_id).text)

    session = action.session_id or action.payload.get("session_id")
    spoken = str(result.get("spoken_text") or "")
    # A commit may already carry its own `speech` (checkout); otherwise ask for the clip now. Either
    # way nothing here waits for TTS: a missing clip is generated in the background (`speech_ready`).
    speech = result.get("speech") if (not already and isinstance(result.get("speech"), dict)) else None
    if speech is None:
        speech = speech_svc.request(spoken, session_id=session, speak=speak and bool(spoken),
                                    ack=phrases.ack_for("done", session=session))
    audio_url = speech.get("audio_url")
    cart = db.get(CartRow, session) if session else None
    if not already:
        events.publish("store", "action_resolved", jsonable_encoder({
            "id": action.id, "kind": action.kind, "status": action.status, "session_id": session,
            "summary": (action.payload or {}).get("summary"), "spoken_text": spoken, "speech": speech}))
        if cart is not None:
            announce_cart(db, cart)
    return {"action": action_json(action), "result": result, "spoken_text": spoken,
            "audio_url": audio_url, "speech": speech, "already_resolved": already,
            "cart": view_json(db, cart) if cart is not None else None}


# ---------------------------------------------------------------------------
# the utterance pipeline
# ---------------------------------------------------------------------------


def _latest(db: Session, session_id: str, statuses: tuple, kinds: Optional[tuple] = None,
            exclude_kind: Optional[str] = None) -> Optional[PendingAction]:
    q = db.query(PendingAction).filter(PendingAction.session_id == session_id,
                                       PendingAction.status.in_(statuses))
    if kinds:
        q = q.filter(PendingAction.kind.in_(kinds))
    if exclude_kind:
        q = q.filter(PendingAction.kind != exclude_kind)
    return q.order_by(PendingAction.id.desc()).first()


def _timings(started: float, stt_ms: Optional[int] = None, parse_ms: Optional[int] = None,
             llm_ms: Optional[int] = None) -> dict:
    """Cheap latency visibility: null where a stage was skipped (typed text has no STT, the fast path no LLM)."""
    return {"stt_ms": stt_ms, "parse_ms": parse_ms, "llm_ms": llm_ms,
            "total_ms": int((time.perf_counter() - started) * 1000)}


def _envelope(db: Session, cart: CartRow, *, transcript: str, spoken: str, speech: dict,
              actions: list[PendingAction], source: str, started: float, stt_source: str,
              timings: Optional[dict] = None, applied: Optional[list] = None, **extra: Any) -> dict:
    timings = timings or _timings(started)
    return {
        "transcript": transcript, "cart": view_json(db, cart),
        "actions": [action_json(a) for a in actions], "applied": applied or [],
        "spoken_text": spoken, "audio_url": speech.get("audio_url"), "speech": speech,
        "source": source, "stt_source": stt_source,
        "latency_ms": timings["total_ms"], "timings": timings,
        "demo_mode": settings.fixtures_only or stt_source == "fixture" or source == "fixture",
        "session_id": cart.id, **extra}


def _say(text: str, session_id: str, speak: bool, *, kind: Optional[str] = None,
         pace: Optional[float] = None, ack: Optional[str] = None) -> dict:
    return speech_svc.request(text, kind=kind, pace=pace, session_id=session_id, speak=speak, ack=ack)


async def _control(db: Session, cart: CartRow, kind: str, transcript: str, started: float,
                   stt_source: str, speak: bool, stt_ms: Optional[int] = None) -> dict:
    """'haan' confirms, 'galat hai' / 'cancel' undoes the newest pending action or cart edit."""
    touched: list[PendingAction] = []
    sid = cart.id
    if kind == "confirm":
        action = _latest(db, cart.id, ("proposed",), exclude_kind="cart_edit")
        if action is None:
            line = voice_style.line("nothing_to_confirm", session=sid)
            spoken, speech = line.text, _say(line.text, sid, speak, kind=line.kind,
                                             ack=phrases.ack_for("unclear", session=sid))
        else:
            res = await resolve_action(db, action.id, "confirm", {}, speak=speak)
            spoken, speech = res["spoken_text"], res["speech"]
            touched.append(action)
        db.refresh(cart)
        return _envelope(db, cart, transcript=transcript, spoken=spoken, speech=speech, actions=touched,
                         source="rules", started=started, stt_source=stt_source,
                         timings=_timings(started, stt_ms, 0), control="confirm")

    pending = _latest(db, cart.id, ("proposed",), exclude_kind="cart_edit")
    last_edit = _latest(db, cart.id, ("confirmed",), kinds=("cart_edit",))
    line = voice_style.line("nothing_to_undo", session=sid)
    if pending is not None and (kind == "no" or last_edit is None or pending.id > last_edit.id):
        await resolve_action(db, pending.id, "cancel", {}, speak=False)
        line = voice_style.line("action_cancelled", session=sid)
        touched.append(pending)
    elif kind == "undo" and last_edit is not None:
        if cart.status != "open":
            line = voice_style.line("undo_after_bill", session=sid)
        else:
            cart.lines = (last_edit.payload or {}).get("before", [])
            last_edit.status = "cancelled"
            last_edit.resolved_at = now_local()
            db.commit()
            announce_cart(db, cart, undone=True)
            line = voice_style.line("undo_done", session=sid)
    speech = _say(line.text, sid, speak, kind=line.kind, pace=line.pace,
                  ack=phrases.ack_for("cancelled" if touched else "unclear", session=sid))
    return _envelope(db, cart, transcript=transcript, spoken=line.text, speech=speech, actions=touched,
                     source="rules", started=started, stt_source=stt_source,
                     timings=_timings(started, stt_ms, 0), control="undo")


# Words that mean more than "add these items": money, khata, prices, undo, checkout. An utterance with
# any of them never takes the fast path, even if the item parser explains the rest.
INTENT_WORDS = {
    "udhaar", "udhar", "khata", "khate", "उधार", "खाता", "खाते", "cash", "paytm", "upi", "phonepe", "gpay",
    "naqad", "nakad", "rate", "bhav", "bhaav", "daam", "dam", "price", "galat", "undo", "cancel", "ruko",
    "rukiye", "nahi", "nahin", "khatam", "usual", "jama", "wapas", "bill", "total", "hisaab", "kitna",
    "kitne", "payment", "diye", "diya", "chukaya", "chukaye"}
FAST_CALLS = {"add_to_cart", "restock"}
FAST_FIX_CALLS = {"remove_item", "set_quantity"}


def fast_path_ok(norm: str, context: str, extra: Optional[list[ToolCall]],
                 rule_calls: list[ToolCall], index: catalog.CatalogIndex) -> bool:
    """True when the rules parser fully explains the utterance, so the LLM adds nothing but latency:
    items with explicit or defaulted quantities, or a cart fix ('Maggi hata do', 'Colgate ek kar do')
    that matched a line already in the cart. See quantity.ParseOutcome.explained."""
    if not settings.fast_path or context not in ("counter", "stock") or not rule_calls:
        return False
    names = {canon(c.name) for c in rule_calls}
    words = set(norm.split())
    if extra:  # "maggi teen nahi do" is a fix, but "maggi ka rate pachaas kar do" is a price change
        return names <= FAST_FIX_CALLS and not (words & (INTENT_WORDS - {"nahi", "nahin"}))
    if names != {"add_to_cart"} and names != {"restock"}:
        return False
    if words & INTENT_WORDS:
        return False
    return quantity.parse_order_full(norm, index=index).explained


async def run_utterance(db: Session, *, session_id: str, transcript: str, context: str = "counter",
                        customer_id: Optional[int] = None, stt_source: str = "rules",
                        started: Optional[float] = None, speak: bool = True,
                        stt_ms: Optional[int] = None) -> dict:
    """Run one transcript through the pipeline described in the module docstring."""
    started = started if started is not None else time.perf_counter()
    cart = get_cart(db, session_id, fresh_if_done=True)
    if customer_id:
        if db.get(Customer, customer_id) is None:
            raise HTTPException(404, f"Customer {customer_id} nahi mila")
        cart.customer_id = customer_id
    norm = catalog.normalize(transcript)
    if not norm:
        line = voice_style.line("nothing_heard", session=session_id)
        return _envelope(db, cart, transcript=transcript, spoken=line.text, actions=[],
                         speech=_say(line.text, session_id, speak, kind=line.kind, pace=line.pace,
                                     ack=phrases.ack_for("silent", session=session_id)),
                         source="rules", started=started, stt_source=stt_source,
                         timings=_timings(started, stt_ms))

    control = classify_control(norm)
    if control:
        return await _control(db, cart, control, transcript, started, stt_source, speak, stt_ms)

    index = catalog.load_index(db)
    ctx = Ctx(db, session_id, cart, index, context, transcript)
    snapshot = [dict(d) for d in (cart.lines or [])]

    # 1. rules result, applied to the cart immediately
    t_parse = time.perf_counter()
    rule_calls: list[ToolCall] = []
    extra: Optional[list[ToolCall]] = None
    if context != "ask":
        extra = extra_rules(db, norm, index, read_lines(cart))
        rule_calls = extra or fixtures.rules_tool_calls(transcript, db, context)
    fast = fast_path_ok(norm, context, extra, rule_calls, index)
    edit_calls = [c for c in rule_calls if canon(c.name) in CART_EDITS]
    out = Out()
    ctx.source = "rules" if fast else ("fixture" if settings.fixtures_only else "rules")
    for call in edit_calls:
        try:
            apply_cart_edit(ctx, call, out)
        except Exception as exc:  # noqa: BLE001
            log.exception("cart edit failed")
            out.errors.append(str(exc))
    if edit_calls:
        db.commit()
        announce_cart(db, cart, transcript=transcript, source=ctx.source, stage="rules")
    parse_ms = int((time.perf_counter() - t_parse) * 1000)

    # 2. LLM tool calling, reconciled over the rules result (skipped on the fast path)
    llm_calls: Optional[list[ToolCall]] = None
    llm_text = ""
    final_source = ctx.source
    latency = 0
    llm_ms: Optional[int] = None
    if not fast:
        t_llm = time.perf_counter()
        try:
            res = await asyncio.wait_for(
                llm.complete_or_rules(build_messages(db, cart, index, transcript, context), db,
                                      tools=TOOLS, context=context, timeout=4.0), timeout=5.5)
            if res.source in ("sarvam", "paytm"):
                if res.data.tool_calls:
                    llm_calls = [ToolCall("restock" if context == "stock" and canon(c.name) == "add_to_cart"
                                          else canon(c.name), c.arguments or {}, c.id)
                                 for c in res.data.tool_calls if c.name]
                elif res.data.content:
                    llm_text = res.data.content
                if llm_calls is not None or llm_text:
                    final_source, latency = res.source, res.latency_ms
        except Exception as exc:  # noqa: BLE001  (timeout, LLMUnavailable, bad shape): keep rules result
            log.info("llm path skipped: %s", exc.__class__.__name__)
        llm_ms = int((time.perf_counter() - t_llm) * 1000)
    ctx.source, ctx.latency_ms = final_source, latency

    if llm_calls is not None:
        cart.lines = snapshot  # replace, never double-add
        out = Out()
        calls = llm_calls
        for call in calls:
            try:
                (apply_cart_edit if canon(call.name) in CART_EDITS else apply_other)(ctx, call, out)
            except Exception as exc:  # noqa: BLE001
                log.exception("tool %s failed", call.name)
                out.errors.append(f"{call.name}: {exc}")
        # LLM text next to tool calls is ignored; calls are authoritative
    else:
        for call in rule_calls:
            if canon(call.name) in CART_EDITS:
                continue
            try:
                apply_other(ctx, call, out)
            except Exception as exc:  # noqa: BLE001
                log.exception("tool %s failed", call.name)
                out.errors.append(f"{call.name}: {exc}")
        if not rule_calls and llm_text:
            out.spoken.append(llm_text)
            out.paces.append(voice_style.pace_for(None, llm_text))

    # missed sales for names that were asked for but are not in the catalog
    for name in out.unmatched:
        if name and name.lower() not in [m.lower() for m in out.missed]:
            apply_other(ctx, ToolCall("missed_sale", {"product": name}), out)

    cart_changed = list(cart.lines or []) != snapshot
    if context == "ask" and not out.spoken:
        out.say(voice_style.line("ask_unavailable", session=session_id))
    spoken, pace = compose_spoken(db, ctx, out, cart_changed)
    understood = bool(spoken)
    if not spoken:
        line = voice_style.line("nothing_understood", session=session_id)
        spoken, pace = line.text, line.pace

    if cart_changed:
        db.add(PendingAction(kind="cart_edit", status="confirmed", session_id=session_id,
                             source=final_source, latency_ms=latency, resolved_at=now_local(),
                             payload={"transcript": transcript, "before": snapshot, "tools": out.tools,
                                      "summary": ", ".join(out.tools)}))
    db.commit()
    if (cart_changed and llm_calls is not None) or out.actions:
        announce_cart(db, cart, transcript=transcript, source=final_source, stage="llm")

    situation = ("unclear" if not understood else "money" if out.actions else
                 "added" if out.added else "done")
    speech = _say(spoken, session_id, speak, pace=pace,
                  ack=phrases.ack_for(situation, session=session_id))
    for action in out.actions:
        events.publish("store", "action_proposed", jsonable_encoder(
            {"session_id": session_id, "action": action_json(action), "spoken_text": spoken,
             "speech": speech}))
    events.publish("store", "utterance", {"session_id": session_id, "transcript": transcript,
                                          "spoken_text": spoken, "audio_url": speech["audio_url"],
                                          "speech": speech, "source": final_source})
    return _envelope(db, cart, transcript=transcript, spoken=spoken, speech=speech,
                     actions=out.actions, source=final_source, started=started, stt_source=stt_source,
                     timings=_timings(started, stt_ms, parse_ms, llm_ms),
                     applied=out.applied, missed=out.missed, errors=out.errors)
