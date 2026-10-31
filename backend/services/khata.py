"""Khata (udhaar) ledger helpers shared by billing, the counter agent and the khata router.

Sign convention (see models.KhataEntry): amount > 0 is credit given, amount < 0 is a payment received.

Stable contract (never change these signatures; none of them commit, the caller owns the transaction):
    balance(db, customer_id) -> float
    add_credit(db, customer_id, amount, invoice_id=None, note=None) -> KhataEntry
    record_payment(db, customer_id, amount, invoice_id=None, note=None) -> KhataEntry

Higher level helpers (Agent A's voice udhaar should call these):
    give_credit(db, customer, amount, note=None, invoice_id=None, send=True, enforce_limit=False)
    receive_payment(db, customer, amount, note=None, invoice_id=None, send=True)
        -> EntryResult (entry, balances, limit warning, the WhatsApp Message). They flush, publish
           `khata_updated` on the `store` channel and queue the customer's WhatsApp confirmation.
    confirm_message(customer, amount, new_balance)  pure text, Hinglish or English
    suggested_limit(customer) / limit_reason(customer)  pure
"""
from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional
from urllib.parse import quote, urlencode

from sqlalchemy import func
from sqlalchemy.orm import Session

from config import settings
from models import Customer, KhataEntry, Message, PendingAction
from services import catalog, events
from services import whatsapp as wa
from services.clock import now_local, today_local

DISPUTE_TAG = "[DISPUTED]"
DEFAULT_CREDIT_LIMIT = 1000.0


# ---------------------------------------------------------------------------
# core ledger (stable contract)
# ---------------------------------------------------------------------------


def balance(db: Session, customer_id: int) -> float:
    """What the customer owes right now (positive means they owe the shop)."""
    total = db.query(func.coalesce(func.sum(KhataEntry.amount), 0.0)).filter(
        KhataEntry.customer_id == customer_id
    ).scalar()
    return round(float(total or 0.0), 2)


def _announce(db: Session, entry: KhataEntry) -> None:
    """Tell open screens the ledger moved (voice udhaar and khata bills come through here)."""
    customer = db.get(Customer, entry.customer_id)
    events.publish_after_commit(db, "store", "khata_updated", {
        "customer_id": entry.customer_id, "customer": customer.name if customer else None, "entry_id": entry.id,
        "amount": entry.amount, "kind": "credit" if entry.amount > 0 else "payment",
        "balance": balance(db, entry.customer_id),
    })


def add_credit(
    db: Session,
    customer_id: int,
    amount: float,
    invoice_id: Optional[int] = None,
    note: Optional[str] = None,
) -> KhataEntry:
    """Record udhaar given to a customer."""
    entry = KhataEntry(customer_id=customer_id, amount=abs(float(amount)), invoice_id=invoice_id, note=note)
    db.add(entry)
    db.flush()
    _announce(db, entry)
    return entry


def record_payment(
    db: Session,
    customer_id: int,
    amount: float,
    invoice_id: Optional[int] = None,
    note: Optional[str] = None,
) -> KhataEntry:
    """Record money received against a customer's khata."""
    entry = KhataEntry(customer_id=customer_id, amount=-abs(float(amount)), invoice_id=invoice_id, note=note)
    db.add(entry)
    db.flush()
    _announce(db, entry)
    return entry


# ---------------------------------------------------------------------------
# formatting and pure helpers
# ---------------------------------------------------------------------------


def fmt_inr(n: float) -> str:
    """Indian digit grouping without the rupee sign: 1350 -> '1,350'; 150000 -> '1,50,000'."""
    n = round(float(n), 2)
    sign = "-" if n < 0 else ""
    n = abs(n)
    whole = int(n)
    paise = int(round((n - whole) * 100))
    if paise == 100:
        whole, paise = whole + 1, 0
    s = str(whole)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups + [tail])
    if paise:
        s += f".{paise:02d}"
    return sign + s


def _english(customer: Any) -> bool:
    return str(getattr(customer, "language", "") or "").lower().startswith("en")


def confirm_message(customer: Any, amount: float, new_balance: float) -> str:
    """WhatsApp text for a khata entry. `amount` > 0 is credit given, < 0 a payment received.

    Hindi/Hinglish (default): "₹500 aapke khate mein jude. Kul baaki ₹1,350. Galat ho toh reply karein."
    """
    a = fmt_inr(abs(amount))
    if _english(customer):
        if amount >= 0:
            return f"₹{a} added to your khata. Total due ₹{fmt_inr(new_balance)}. Reply if this is wrong."
        if new_balance <= 0:
            return f"₹{a} received. Your khata is now clear. Thank you."
        return f"₹{a} received, ₹{fmt_inr(new_balance)} still due. Thank you."
    if amount >= 0:
        return f"₹{a} aapke khate mein jude. Kul baaki ₹{fmt_inr(new_balance)}. Galat ho toh reply karein."
    if new_balance <= 0:
        return f"₹{a} mile. Aapka khata ab saaf hai. Dhanyavaad."
    return f"₹{a} mile, baaki ₹{fmt_inr(new_balance)}. Dhanyavaad."


def _round50(x: float) -> float:
    return float(max(0, int(round(x / 50.0)) * 50))


def suggested_limit(customer: Any) -> float:
    """Credit limit to propose, from the base `credit_limit` and how often they paid late.

    0 late: the base limit. 1 late: 80% of it. 2 late: 60%, at most 1,000. 3 or more late: at most 500.
    """
    base = float(getattr(customer, "credit_limit", None) or DEFAULT_CREDIT_LIMIT)
    late = int(getattr(customer, "late_payments", 0) or 0)
    if late <= 0:
        return base
    if late == 1:
        return min(base, _round50(base * 0.8))
    if late == 2:
        return min(base, 1000.0, _round50(base * 0.6))
    return min(base, 500.0)


def limit_reason(customer: Any) -> str:
    """Plain-language (Hinglish) reason for `suggested_limit`, '' when there is no reduction."""
    late = int(getattr(customer, "late_payments", 0) or 0)
    base = float(getattr(customer, "credit_limit", None) or DEFAULT_CREDIT_LIMIT)
    sug = suggested_limit(customer)
    if late <= 0 or sug >= base:
        return ""
    name = getattr(customer, "name", None) or "Customer"
    times = "ek baar" if late == 1 else f"pichhli {late} baar"
    return f"{name} ne {times} der se chukaya. Limit ₹{fmt_inr(sug)} tak rakhein?"


def risk_label(customer: Any, bal: float) -> str:
    """'high' | 'medium' | 'low' (shown as a coloured chip next to the customer)."""
    late = int(getattr(customer, "late_payments", 0) or 0)
    limit = min(float(getattr(customer, "credit_limit", None) or DEFAULT_CREDIT_LIMIT), suggested_limit(customer))
    if late >= 3 or (limit > 0 and bal > limit * 1.2):
        return "high"
    if late >= 1 or (limit > 0 and bal >= limit * 0.8):
        return "medium"
    return "low"


def effective_limit(customer: Any) -> float:
    """The limit actually applied: the smaller of the stored and the suggested one."""
    return min(float(getattr(customer, "credit_limit", None) or DEFAULT_CREDIT_LIMIT), suggested_limit(customer))


def is_disputed(entry: KhataEntry) -> bool:
    return bool(entry.note and DISPUTE_TAG in entry.note)


def upi_link(vpa: str, payee: str, amount: float, note: str = "") -> str:
    """UPI intent string. Many chat clients do not make `upi://` clickable; the amount is also in the text."""
    params = {"pa": vpa, "pn": payee, "cu": "INR"}
    if amount and amount > 0:
        params["am"] = f"{amount:.2f}"
    if note:
        params["tn"] = note
    return "upi://pay?" + urlencode(params, quote_via=quote)


def pay_link(amount: float, note: str = "Khata") -> str:
    return upi_link(settings.merchant_upi_vpa, settings.merchant_name, amount, note)


# ---------------------------------------------------------------------------
# passbook token
# ---------------------------------------------------------------------------


def _secret() -> bytes:
    return (os.getenv("KHATA_TOKEN_SECRET") or settings.wa_app_secret or "awaaz-passbook-dev-secret").encode()


def passbook_token(customer_id: int) -> str:
    """Stable signed token '<id>.<hmac16>'; no database column needed."""
    sig = hmac.new(_secret(), f"passbook:{customer_id}".encode(), hashlib.sha256).hexdigest()[:16]
    return f"{customer_id}.{sig}"


def customer_id_from_token(token: str) -> Optional[int]:
    try:
        raw_id, _sig = token.split(".", 1)
        cid = int(raw_id)
    except (ValueError, AttributeError):
        return None
    return cid if hmac.compare_digest(passbook_token(cid), token) else None


def passbook_url(customer_id: int) -> str:
    return f"{settings.public_base_url.rstrip('/')}/api/khata/passbook/{passbook_token(customer_id)}"


# ---------------------------------------------------------------------------
# summaries
# ---------------------------------------------------------------------------


def is_walk_in(customer: Customer) -> bool:
    return (customer.name or "").lower().startswith("walk-in")


def resolve_customer(db: Session, customer_id: Optional[int] = None,
                     name: Optional[str] = None) -> Optional[Customer]:
    """Customer by id, else fuzzy by spoken name."""
    if customer_id:
        return db.get(Customer, int(customer_id))
    if name:
        cust, _score = catalog.match_customer(db, name)
        return cust
    return None


def customer_summary(db: Session, c: Customer) -> dict[str, Any]:
    bal = balance(db, c.id)
    last_pay = (db.query(KhataEntry).filter(KhataEntry.customer_id == c.id, KhataEntry.amount < 0)
                .order_by(KhataEntry.at.desc(), KhataEntry.id.desc()).first())
    last_entry = (db.query(KhataEntry).filter(KhataEntry.customer_id == c.id)
                  .order_by(KhataEntry.at.desc(), KhataEntry.id.desc()).first())
    disputed = sum(1 for e in db.query(KhataEntry).filter(KhataEntry.customer_id == c.id,
                                                          KhataEntry.note.contains(DISPUTE_TAG)).all())
    limit = float(c.credit_limit or DEFAULT_CREDIT_LIMIT)
    sug = suggested_limit(c)
    eff = min(limit, sug)
    return {
        "id": c.id,
        "name": c.name,
        "name_hi": c.name_hi,
        "phone": c.phone,
        "upi_id": c.upi_id,
        "language": c.language,
        "balance": bal,
        "credit_limit": limit,
        "late_payments": int(c.late_payments or 0),
        "suggested_limit": sug,
        "limit_reason": limit_reason(c),
        "over_limit": bal > eff,
        "risk": risk_label(c, bal),
        "last_payment_at": last_pay.at.isoformat() if last_pay and last_pay.at else None,
        "last_payment_amount": abs(last_pay.amount) if last_pay else None,
        "last_entry_at": last_entry.at.isoformat() if last_entry and last_entry.at else None,
        "disputed_entries": disputed,
        "passbook_url": passbook_url(c.id),
    }


def entry_dict(e: KhataEntry, running: Optional[float] = None) -> dict[str, Any]:
    out = {
        "id": e.id,
        "customer_id": e.customer_id,
        "amount": e.amount,
        "kind": "credit" if e.amount > 0 else "payment",
        "invoice_id": e.invoice_id,
        "note": e.note,
        "wa_status": e.wa_status,
        "confirmed_by_customer": bool(e.confirmed_by_customer),
        "disputed": is_disputed(e),
        "at": e.at.isoformat() if e.at else None,
    }
    if running is not None:
        out["running_balance"] = round(running, 2)
    return out


def ledger(db: Session, customer_id: int, newest_first: bool = True) -> list[dict[str, Any]]:
    entries = (db.query(KhataEntry).filter(KhataEntry.customer_id == customer_id)
               .order_by(KhataEntry.at, KhataEntry.id).all())
    running = 0.0
    rows = []
    for e in entries:
        running += e.amount
        rows.append(entry_dict(e, running))
    return list(reversed(rows)) if newest_first else rows


# ---------------------------------------------------------------------------
# give credit / receive payment (ledger + WhatsApp + event)
# ---------------------------------------------------------------------------


class LimitExceeded(Exception):
    def __init__(self, warning: dict[str, Any]):
        super().__init__(warning.get("message_hi", "credit limit exceeded"))
        self.warning = warning


@dataclass
class EntryResult:
    entry: KhataEntry
    customer: Customer
    balance_before: float
    balance_after: float
    credit_limit: float
    suggested_limit: float
    limit_reason: str
    warning: Optional[dict[str, Any]] = None
    message: Optional[Message] = None
    text: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        msg = self.message
        return {
            "entry": entry_dict(self.entry),
            "customer": {"id": self.customer.id, "name": self.customer.name},
            "balance_before": self.balance_before,
            "balance_after": self.balance_after,
            "credit_limit": self.credit_limit,
            "suggested_limit": self.suggested_limit,
            "limit_reason": self.limit_reason,
            "warning": self.warning,
            "whatsapp": ({"message_id": msg.id, "status": msg.status, "channel": msg.channel,
                          "to": msg.to, "text": msg.body} if msg else None),
        }


def limit_warning(customer: Customer, bal_after: float) -> Optional[dict[str, Any]]:
    """Warning dict when the new balance passes the limit actually applied, else None."""
    eff = effective_limit(customer)
    if bal_after <= eff:
        return None
    reason = limit_reason(customer)
    text = reason + " " if reason else ""
    text += f"Abhi baaki ₹{fmt_inr(bal_after)} ho gaya, limit ₹{fmt_inr(eff)} hai."
    return {
        "over_limit": True,
        "limit": eff,
        "balance_after": bal_after,
        "late_payments": int(customer.late_payments or 0),
        "reason": reason,
        "message_hi": text.strip(),
        "blocked": False,
        "postpaid_available": True,
    }


def _post_entry(db: Session, customer: Customer, signed: float, note: Optional[str],
                invoice_id: Optional[int], send: bool) -> EntryResult:
    before = balance(db, customer.id)
    entry = KhataEntry(customer_id=customer.id, amount=signed, invoice_id=invoice_id, note=note)
    db.add(entry)
    db.flush()
    after = balance(db, customer.id)
    warning = limit_warning(customer, after) if signed > 0 else None
    result = EntryResult(entry, customer, before, after, float(customer.credit_limit or DEFAULT_CREDIT_LIMIT),
                         suggested_limit(customer), limit_reason(customer), warning)
    result.text = confirm_message(customer, signed, after)
    if send:
        msg = wa.notify(db, customer.phone, result.text, customer_id=customer.id)
        result.message = msg
        will_send_real = wa._will_deliver(msg, db)
        entry.wa_status = "queued" if will_send_real else "sent"
        if will_send_real:
            wa.link_khata_entry(msg.id, entry.id)
    events.publish_after_commit(db, "store", "khata_updated", {
        "customer_id": customer.id, "customer": customer.name, "entry_id": entry.id,
        "amount": signed, "kind": "credit" if signed > 0 else "payment",
        "balance": after, "balance_before": before, "warning": warning,
        "wa_status": entry.wa_status,
    })
    return result


def give_credit(db: Session, customer: Customer, amount: float, note: Optional[str] = None,
                invoice_id: Optional[int] = None, send: bool = True,
                enforce_limit: bool = False) -> EntryResult:
    """Udhaar: write the entry, WhatsApp the customer, publish `khata_updated`.

    With `enforce_limit=True` raises `LimitExceeded` (nothing written) when the limit would be passed;
    otherwise the result carries `warning` and the entry is still written."""
    amount = abs(float(amount))
    if amount <= 0:
        raise ValueError("amount must be positive")
    if enforce_limit:
        warning = limit_warning(customer, balance(db, customer.id) + amount)
        if warning:
            warning["blocked"] = True
            raise LimitExceeded(warning)
    return _post_entry(db, customer, amount, note, invoice_id, send)


def receive_payment(db: Session, customer: Customer, amount: float, note: Optional[str] = None,
                    invoice_id: Optional[int] = None, send: bool = True) -> EntryResult:
    """Customer paid against their khata."""
    amount = abs(float(amount))
    if amount <= 0:
        raise ValueError("amount must be positive")
    return _post_entry(db, customer, -amount, note, invoice_id, send)


def set_confirmation(db: Session, entry: KhataEntry, confirmed: bool, note: Optional[str] = None) -> KhataEntry:
    """Customer said sahi (True) or galat (False). False tags the entry as disputed."""
    entry.confirmed_by_customer = bool(confirmed)
    base = (entry.note or "").replace(DISPUTE_TAG, "").strip(" |")
    if confirmed:
        entry.note = base or None
    else:
        tail = f"{DISPUTE_TAG} {note}".strip() if note else DISPUTE_TAG
        entry.note = f"{base} | {tail}" if base else tail
    db.flush()
    return entry


def latest_open_entry(db: Session, customer_id: int) -> Optional[KhataEntry]:
    """The entry a customer's 'sahi/galat' reply refers to: the newest one not yet answered."""
    return (db.query(KhataEntry).filter(KhataEntry.customer_id == customer_id)
            .order_by(KhataEntry.at.desc(), KhataEntry.id.desc()).first())


# ---------------------------------------------------------------------------
# salary-day reminders
# ---------------------------------------------------------------------------


def in_salary_window(day: Optional[date] = None) -> bool:
    """Reminders are meant for the 1st to 7th of the month, when most salaries arrive."""
    return (day or today_local()).day <= 7


def reminder_text(customer: Customer, bal: float) -> str:
    store = settings.merchant_name
    book = passbook_url(customer.id)
    pay = pay_link(bal, "Khata")
    if _english(customer):
        return (f"Hello {customer.name}, this is {store}. ₹{fmt_inr(bal)} is due on your khata. "
                f"You can pay now: {pay}\nSee your khata: {book}\nThank you.")
    return (f"Namaste {customer.name}, {store} se. Aapke khate mein ₹{fmt_inr(bal)} baaki hain. "
            f"Salary aane par yahan se chuka dein: {pay}\nApna khata dekhein: {book}\nDhanyavaad.")


def reminder_candidates(db: Session, min_balance: float = 0.01,
                        customer_ids: Optional[list[int]] = None) -> list[dict[str, Any]]:
    rows = []
    for c in db.query(Customer).order_by(Customer.id).all():
        if is_walk_in(c) or (customer_ids is not None and c.id not in customer_ids):
            continue
        bal = balance(db, c.id)
        if bal < min_balance:
            continue
        rows.append({
            "customer_id": c.id, "name": c.name, "phone": c.phone, "has_phone": bool(wa.normalize_phone(c.phone)),
            "balance": bal, "language": c.language, "text": reminder_text(c, bal),
            "pay_link": pay_link(bal, "Khata"), "passbook_url": passbook_url(c.id),
        })
    rows.sort(key=lambda r: -r["balance"])
    return rows


# ---------------------------------------------------------------------------
# khata notebook photo import (F11)
# ---------------------------------------------------------------------------


def _parse_date(raw: Any) -> Optional[datetime]:
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(str(raw)[:10], fmt)
        except ValueError:
            continue
    return None


def propose_import(db: Session, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Vision rows [{customer, amount, date, note}] -> proposal lines with fuzzy-matched customers.

    New people default to include=True; people already in the ledger default to include=False (their
    balance is shown so the merchant can decide) to avoid double counting."""
    proposal = []
    for i, r in enumerate(rows):
        name = str(r.get("customer") or "").strip()
        if not name:
            continue
        cust, score = catalog.match_customer(db, name)
        match = None
        if cust is not None:
            match = {"customer_id": cust.id, "name": cust.name, "score": round(score, 1),
                     "current_balance": balance(db, cust.id)}
        proposal.append({
            "index": i, "name": name, "amount": float(r.get("amount") or 0.0),
            "date": r.get("date"), "note": r.get("note") or "",
            "match": match,
            "action": "add_to_existing" if match else "create",
            "include": match is None and float(r.get("amount") or 0.0) > 0,
        })
    return proposal


def commit_import(db: Session, action: PendingAction, edits: Optional[list[dict[str, Any]]] = None
                  ) -> dict[str, Any]:
    """Create customers and opening KhataEntry rows from a `khata_import` PendingAction."""
    by_index = {int(e["index"]): e for e in (edits or []) if "index" in e}
    created: dict[str, Customer] = {}
    new_customers, entries, skipped = [], [], 0
    for line in action.payload.get("rows", []):
        edit = by_index.get(int(line["index"]), {})
        if not edit.get("include", line.get("include", False)):
            skipped += 1
            continue
        name = str(edit.get("name") or line["name"]).strip()
        amount = float(edit.get("amount", line["amount"]) or 0.0)
        if amount <= 0 or not name:
            skipped += 1
            continue
        cust: Optional[Customer] = None
        cid = edit.get("customer_id") or ((line.get("match") or {}).get("customer_id")
                                         if line.get("action") == "add_to_existing" else None)
        if cid:
            cust = db.get(Customer, int(cid))
        if cust is None:
            cust = created.get(name.lower())
        if cust is None:
            cust = Customer(name=name, credit_limit=DEFAULT_CREDIT_LIMIT, language="hi-IN")
            db.add(cust)
            db.flush()
            created[name.lower()] = cust
            new_customers.append({"id": cust.id, "name": cust.name})
        note = "Purani bahi se (notebook import)"
        if line.get("note"):
            note += f": {line['note']}"
        entry = KhataEntry(customer_id=cust.id, amount=amount, note=note,
                           at=_parse_date(line.get("date")) or now_local(), confirmed_by_customer=False)
        db.add(entry)
        db.flush()
        entries.append({"entry_id": entry.id, "customer_id": cust.id, "customer": cust.name, "amount": amount})
    return {"created_customers": new_customers, "entries": entries, "skipped": skipped,
            "total_imported": round(sum(e["amount"] for e in entries), 2)}
