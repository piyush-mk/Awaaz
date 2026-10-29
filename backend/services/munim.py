"""Ask your munim: read-only Q&A over the shop's data (plan F15).

Flow: question -> (LLM picks read-only tools) or (rules router when no LLM) -> tools run
against the DB -> answer in Hinglish + the data table. Every tool is read-only; the LLM
never gets a write tool and never sees raw SQL. The answer line for each tool is built
deterministically from the data; when the LLM was used it may re-word the answer, but only
if every number it writes appears in the tool results (otherwise the deterministic line stays).
"""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from models import Product
from services import brief, catalog, insights, llm, stock_ops
from services.clock import today_local
from services.insights import inr
from services.types import LLMUnavailable, ProviderError

LLM_TIMEOUT = 6.0

EXAMPLE_QUESTIONS = [
    "Is hafte sabse zyada kya bika?",
    "Kitna stock hai ghee?",
    "Kis kis ka udhaar baaki hai?",
    "Verma ji ka kitna baaki hai?",
    "Aaj ki sale kitni hui?",
    "Kya khatam ho raha hai?",
    "Kaunsa maal expire hone wala hai?",
]

_PERIOD_LABEL = {"today": "Aaj", "yesterday": "Kal", "week": "Is hafte", "month": "Is mahine"}


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _table(columns: list[str], rows: list[list[Any]]) -> dict[str, Any]:
    return {"columns": columns, "rows": rows}


# ---------------------------------------------------------------------------
# tools (all read-only). Each returns {"data", "table", "line"}.
# ---------------------------------------------------------------------------


def tool_sales_summary(db: Session, args: dict, today: date) -> dict[str, Any]:
    d = insights.sales_summary(db, args.get("period") or "today", today)
    label = _PERIOD_LABEL[d["period"]]
    if d["period"] == "today":
        line = f"Aaj ab tak {inr(d['total'])} ki sale hui, {d['invoices']} bill."
    elif d["period"] == "yesterday":
        line = f"Kal {inr(d['total'])} ki sale hui, {d['invoices']} bill"
    elif d["period"] == "week":
        line = f"Pichle 7 din mein {inr(d['total'])} ki sale hui, {d['invoices']} bill"
    else:
        line = f"{label} ab tak {inr(d['total'])} ki sale hui, {d['invoices']} bill"
    cmp_ = d["compare"]
    if cmp_ and cmp_["delta_pct"] is not None:
        pct = cmp_["delta_pct"]
        line += f", {cmp_['label']} se {abs(pct):g}% " + ("zyada." if pct >= 0 else "kam.")
    elif d["period"] != "today":
        line += "."
    rows = [[d["period"], d["total"], d["invoices"], d["avg_bill"]]]
    if cmp_:
        rows.append([f"compare: {cmp_['label']}", cmp_["total"], None, None])
    return {"data": d, "table": _table(["period", "sale", "bills", "avg_bill"], rows), "line": line}


def tool_top_items(db: Session, args: dict, today: date) -> dict[str, Any]:
    n = _int(args.get("n"), 5)
    d = insights.top_items(db, args.get("period") or "week", n, args.get("by") or "amount", today)
    label = _PERIOD_LABEL[d["period"]]
    items = d["items"]
    if not items:
        return {"data": d, "table": _table(["item", "qty", "amount"], []),
                "line": f"{label} abhi koi sale nahi hui."}
    shown = ", ".join(f"{r['name']} ({inr(r['amount'])})" for r in items[:5])
    line = f"{label} sabse zyada bika: {shown}."
    rows = [[i, r["name"], r["qty"], r["unit"], r["amount"]] for i, r in enumerate(items, 1)]
    return {"data": d, "table": _table(["rank", "item", "qty", "unit", "amount"], rows), "line": line}


def tool_stock_of(db: Session, args: dict, today: date) -> dict[str, Any]:
    phrase = str(args.get("product") or "").strip()
    index = catalog.load_index(db)
    matches = [p for p, _s in index.match_all(phrase)] if phrase else []
    if not matches and phrase:
        found, _ = index.find_in_phrase(phrase)
        matches = [found] if found else []
    if not matches:
        return {"data": {"product_query": phrase, "found": False, "matches": []},
                "table": _table(["item", "stock"], []), "line": f"'{phrase}' catalog mein nahi mila."}
    stock = stock_ops.stock_map(db)
    vel = insights.velocity_map(db, today)
    rows, data = [], []
    for p in matches[:4]:
        qty = stock.get(p.id, 0.0)
        cover = insights.cover_of(qty, vel.get(p.id, 0.0))
        data.append({"product_id": p.id, "name": p.name, "stock": qty, "unit": p.unit, "cover_days": cover,
                     "status": stock_ops.stock_status(qty, p.threshold or 0.0)})
        rows.append([p.name, qty, p.unit, cover])
    parts = []
    for r in data:
        s = f"{r['name']}: {r['stock']:g} {r['unit']} bacha hai"
        if r["cover_days"] is not None:
            s += f", lagbhag {round(r['cover_days']):g} din ka" if r["cover_days"] >= 0.75 else ", sirf aaj bhar ka"
        parts.append(s)
    return {"data": {"product_query": phrase, "found": True, "matches": data},
            "table": _table(["item", "stock", "unit", "cover_days"], rows), "line": ". ".join(parts) + "."}


def tool_who_owes(db: Session, args: dict, today: date) -> dict[str, Any]:
    customer = args.get("customer")
    d = insights.who_owes(db, _int(args.get("n"), 5), customer, today)
    rows = [[c["name"], c["balance"], c["days_outstanding"], c["late_payments"]] for c in d["customers"]]
    table = _table(["customer", "balance", "days_outstanding", "late_payments"], rows)
    if customer:
        if not d["found"]:
            return {"data": d, "table": table, "line": f"'{customer}' naam ka koi customer nahi mila."}
        c = d["customers"][0]
        if c["balance"] <= 0:
            return {"data": d, "table": table, "line": f"{c['name']} ka koi udhaar baaki nahi hai."}
        line = f"{c['name']} ka {inr(c['balance'])} baaki hai"
        if c["late_payments"]:
            line += f", {c['late_payments']} baar der se chukaya hai"
        return {"data": d, "table": table, "line": line + "."}
    if not d["customers"]:
        return {"data": d, "table": table, "line": "Kisi ka udhaar baaki nahi hai."}
    shown = ", ".join(f"{c['name']} {inr(c['balance'])}" for c in d["customers"][:5])
    line = f"Udhaar baaki: {shown}."
    if len(d["customers"]) > 5:
        line += f" Kul {inr(d['total_outstanding'])}, {d['customers_with_balance']} logon par."
    return {"data": d, "table": table, "line": line}


def tool_low_stock(db: Session, args: dict, today: date) -> dict[str, Any]:
    stock = stock_ops.stock_map(db)
    rows = []
    for p in db.query(Product).filter(Product.active.is_(True)).order_by(Product.id).all():
        qty = stock.get(p.id, 0.0)
        if qty <= (p.threshold or 0.0):
            rows.append({"product_id": p.id, "name": p.name, "stock": qty, "unit": p.unit,
                         "threshold": p.threshold})
    cover = insights.low_cover(db, today)
    data = {"below_threshold": rows, "low_cover": cover[:10]}
    table = _table(["item", "stock", "unit", "threshold"], [[r["name"], r["stock"], r["unit"], r["threshold"]]
                                                           for r in rows])
    if not rows:
        return {"data": data, "table": table, "line": "Sab cheezein theek stock mein hain."}
    shown = ", ".join(f"{r['name']} ({r['stock']:g})" for r in rows[:6])
    return {"data": data, "table": table, "line": f"{len(rows)} cheezein kam hain: {shown}."}


def tool_expiry_soon(db: Session, args: dict, today: date) -> dict[str, Any]:
    days = max(1, min(_int(args.get("days"), insights.EXPIRY_DAYS), 365))
    rows = insights.expiring_batches(db, days, today)
    claim = round(sum(r["claim_amount"] for r in rows), 2)
    data = {"days": days, "items": rows, "total_claim": claim}
    table = _table(["item", "qty", "expiry", "days_left", "claim"],
                   [[r["name"], r["qty"], r["expiry"], r["days_left"], r["claim_amount"]] for r in rows])
    if not rows:
        return {"data": data, "table": table, "line": f"Agle {days} din mein kuch expire nahi ho raha."}
    shown = ", ".join(f"{r['short_name']} ({r['days_left']} din)" for r in rows[:4])
    return {"data": data, "table": table,
            "line": f"{len(rows)} cheezein {days} din mein expire hongi: {shown}. Kul claim {inr(claim)}."}


def tool_udhaar_total(db: Session, args: dict, today: date) -> dict[str, Any]:
    d = insights.udhaar_total(db, today)
    line = f"Kul udhaar {inr(d['total_outstanding'])} baaki hai, {d['customers_with_balance']} logon par."
    if d["overdue_count"]:
        line += f" Inme se {d['overdue_count']} ka {inr(d['overdue_amount'])} {d['credit_days']} din se purana hai."
    return {"data": d, "table": _table(["total", "customers", "overdue", "overdue_amount"],
                                       [[d["total_outstanding"], d["customers_with_balance"],
                                         d["overdue_count"], d["overdue_amount"]]]), "line": line}


def tool_cash_gap(db: Session, args: dict, today: date) -> dict[str, Any]:
    day = None
    if args.get("day"):
        try:
            day = date.fromisoformat(str(args["day"]))
        except ValueError:
            day = None
    g = insights.cash_gap(db, day)
    if g is None:
        return {"data": None, "table": _table(["day", "expected", "counted", "diff"], []),
                "line": "Galla ka koi closing record nahi mila."}
    d = date.fromisoformat(g["day"])
    when = "Kal" if (today - d).days == 1 else ("Aaj" if d == today else f"{d.day}/{d.month} ko")
    if g["status"] == "theek":
        line = f"{when} galla bilkul theek tha, {inr(g['counted'])} mila."
    else:
        line = (f"{when} galla {inr(abs(g['diff']))} {g['status']} tha: {inr(g['expected'])} hona chahiye tha, "
                f"{inr(g['counted'])} mila.")
    return {"data": g, "table": _table(["day", "expected", "counted", "diff"],
                                       [[g["day"], g["expected"], g["counted"], g["diff"]]]), "line": line}


TOOLS: dict[str, Callable[[Session, dict, date], dict[str, Any]]] = {
    "sales_summary": tool_sales_summary, "top_items": tool_top_items, "stock_of": tool_stock_of,
    "who_owes": tool_who_owes, "low_stock": tool_low_stock, "expiry_soon": tool_expiry_soon,
    "udhaar_total": tool_udhaar_total, "cash_gap": tool_cash_gap,
}


def _fn(name: str, description: str, properties: dict, required: Optional[list[str]] = None) -> dict:
    return {"type": "function", "function": {"name": name, "description": description, "parameters": {
        "type": "object", "properties": properties, "required": required or []}}}


_PERIOD = {"type": "string", "enum": ["today", "yesterday", "week", "month"],
           "description": "aaj=today, kal=yesterday, is hafte=week (last 7 days), is mahine=month"}

TOOL_SCHEMAS: list[dict] = [
    _fn("sales_summary", "Total sale, bill count and comparison for a period.", {"period": _PERIOD}, ["period"]),
    _fn("top_items", "Best-selling items for a period.", {
        "period": _PERIOD, "n": {"type": "integer", "description": "how many items, default 5"},
        "by": {"type": "string", "enum": ["amount", "qty"]}}, ["period"]),
    _fn("stock_of", "Current stock and days of cover of one product.", {
        "product": {"type": "string", "description": "spoken product name, e.g. ghee, maggi"}}, ["product"]),
    _fn("who_owes", "Customers who owe udhaar; pass customer for one person's balance.", {
        "n": {"type": "integer"}, "customer": {"type": "string", "description": "spoken name, e.g. Verma ji"}}),
    _fn("low_stock", "Items at or below their alert threshold.", {}),
    _fn("expiry_soon", "Stock batches expiring soon, with the claim value.", {
        "days": {"type": "integer", "description": "default 7"}}),
    _fn("udhaar_total", "Total udhaar outstanding and how much is overdue.", {}),
    _fn("cash_gap", "Latest galla (cash drawer) closing: expected vs counted.", {
        "day": {"type": "string", "description": "optional YYYY-MM-DD"}}),
]


def run_tool(db: Session, name: str, args: Optional[dict] = None, today: Optional[date] = None
             ) -> Optional[dict[str, Any]]:
    """Execute one read-only tool; None for an unknown name. Never raises on bad arguments."""
    fn = TOOLS.get(name)
    if fn is None:
        return None
    args = args if isinstance(args, dict) else {}
    try:
        out = fn(db, args, today or today_local())
    except Exception as exc:  # a broken tool must not break the answer
        return {"name": name, "args": args, "data": None, "table": _table([], []),
                "line": "Yeh jaankari abhi nahi nikal paya.", "error": str(exc)[:120]}
    return {"name": name, "args": args, **out}


# ---------------------------------------------------------------------------
# rules router (no LLM / no key)
# ---------------------------------------------------------------------------

_STOP = {"ka", "ki", "ke", "ko", "kitna", "kitne", "kitni", "baaki", "baki", "hai", "hain", "udhaar", "udhar",
         "khata", "khate", "kya", "kis", "kaun", "kon", "aaj", "kal", "total", "kul", "batao", "bataiye",
         "bolo", "dena", "dene", "se", "mein", "me", "ye", "yeh", "mera", "meri", "sab", "sabka", "hafte",
         "hafta", "mahine", "mahina", "week", "month", "stock", "sale", "bika", "bik", "sabse", "zyada"}


def _words(text: str) -> list[str]:
    return catalog.normalize(text).split()


def _find_customer(db: Session, words: list[str]) -> Optional[str]:
    for w in words:
        if len(w) < 3 or w in _STOP or w in catalog.HONORIFICS or w.isdigit():
            continue
        c, score = catalog.match_customer(db, w, threshold=85)
        if c is not None:
            return w + " ji" if not w.endswith("ji") else w
    return None


def _find_product_phrase(db: Session, words: list[str]) -> Optional[str]:
    index = catalog.load_index(db)
    for span in range(min(index.max_alias_words, len(words)), 0, -1):
        for i in range(len(words) - span + 1):
            phrase = " ".join(words[i:i + span])
            if phrase in _STOP:
                continue
            if index.alias_map.get(phrase):
                return phrase
    return None


def _period_of(w: set[str]) -> Optional[str]:
    if w & {"aaj", "today", "abhi"}:
        return "today"
    if w & {"kal", "yesterday"}:
        return "yesterday"
    if w & {"hafte", "hafta", "week", "saptah", "haftey"}:
        return "week"
    if w & {"mahine", "mahina", "month", "mahine"}:
        return "month"
    return None


def route(db: Session, question: str) -> list[tuple[str, dict]]:
    """Map a question to [(tool, args)] with keyword rules. Empty list when nothing matches."""
    words = _words(question)
    w = set(words)
    period = _period_of(w)
    if w & {"expiry", "expire", "expired", "exp", "kharab"}:
        return [("expiry_soon", {})]
    if (w & {"galla", "gala", "gullak"}) or ("cash" in w and w & {"gap", "kam", "diff", "theek"}):
        return [("cash_gap", {})]
    if w & {"udhaar", "udhar", "baaki", "baki", "khata", "khate", "dena", "dene", "ledger"}:
        cust = _find_customer(db, words)
        if cust:
            return [("who_owes", {"customer": cust})]
        if w & {"kis", "kaun", "kon", "list", "naam", "sabka", "sabhi", "kiska", "kiske"}:
            return [("who_owes", {"n": 10})]
        if w & {"total", "kul", "kitna", "kitni", "sab", "overall"}:
            return [("udhaar_total", {})]
        return [("who_owes", {"n": 5})]
    sold = w & {"bika", "bik", "bikta", "bikti", "biki", "becha", "selling", "sale", "bikri", "bikree"}
    if (w & {"sabse", "top", "best", "zyada"}) and sold and not w & {"stock", "bacha", "bache"}:
        return [("top_items", {"period": period or "week", "n": 5})]
    product = _find_product_phrase(db, words)
    if product and (w & {"stock", "bacha", "bachi", "bache", "kitna", "kitne", "kitni", "hai", "hain", "available"}) \
            and not sold:
        return [("stock_of", {"product": product})]
    if w & {"kam", "khatam", "khatm", "low", "shortage", "khatam", "mangwana", "mangana", "reorder"} \
            or (w & {"stock"} and not product):
        return [("low_stock", {})]
    if sold or w & {"sale", "hisaab", "kamai", "collection", "bikri", "turnover", "kamaya"}:
        return [("sales_summary", {"period": period or "today"})]
    if product:
        return [("stock_of", {"product": product})]
    return []


# ---------------------------------------------------------------------------
# answer
# ---------------------------------------------------------------------------

NOT_UNDERSTOOD = ("Yeh sawaal abhi samajh nahi aaya. Aap sale, stock, udhaar, expiry ya galla ke baare "
                  "mein pooch sakte hain.")

REPHRASE_SYSTEM = (
    "Tum Ramesh General Store ke munim ho. User ke sawaal ka jawab sirf neeche diye 'results' se do, "
    "1 se 3 chhote Hinglish (roman) vaakya mein, bolne layak. Koi number invent ya round mat karo; sirf "
    "results ke numbers digits mein likho. Rupaye ₹ ke saath. Bullet ya table mat banao."
)


async def _llm_pick_tools(question: str) -> tuple[list[tuple[str, dict]], str, int]:
    messages = [
        {"role": "system", "content": (
            "Tum Ramesh General Store ke munim ho. Dukaan ke sawaal ka jawab dene ke liye diye gaye "
            "read-only tools chalao. Kabhi jawab khud mat banao; hamesha ek ya zyada tool chuno.")},
        {"role": "user", "content": question},
    ]
    try:
        res = await llm.complete(messages, tools=TOOL_SCHEMAS, timeout=LLM_TIMEOUT)
    except (LLMUnavailable, ProviderError):
        return [], "rules", 0
    except Exception:
        return [], "rules", 0
    calls = [(c.name, c.arguments) for c in res.data.tool_calls if c.name in TOOLS][:3]
    return calls, res.source, res.latency_ms


async def _llm_rephrase(question: str, results: list[dict]) -> Optional[str]:
    payload = [{"tool": r["name"], "args": r["args"], "data": r["data"]} for r in results]
    messages = [{"role": "system", "content": REPHRASE_SYSTEM},
                {"role": "user", "content": f"sawaal: {question}\nresults:\n" +
                 json.dumps(payload, ensure_ascii=False, default=str)[:6000]}]
    try:
        res = await llm.complete(messages, timeout=LLM_TIMEOUT)
    except Exception:
        return None
    text = brief._clean_llm_text(res.data.content)
    if not text or len(text) > 500:
        return None
    ok, _bad = brief.verify_numbers(text, {"results": payload})
    return text if ok else None


async def ask(db: Session, question: str, today: Optional[date] = None, use_llm: bool = True
              ) -> dict[str, Any]:
    """Answer one question. Returns answer text, spoken text, tool results and the first table."""
    today = today or today_local()
    question = (question or "").strip()
    calls: list[tuple[str, dict]] = []
    source, latency = "rules", 0
    if question and use_llm:
        calls, source, latency = await _llm_pick_tools(question)
    if not calls and question:
        calls = route(db, question)
        source, latency = "rules", 0
    results = [r for r in (run_tool(db, n, a, today) for n, a in calls) if r is not None]
    if not results:
        answer = NOT_UNDERSTOOD
    else:
        answer = " ".join(r["line"] for r in results)
        if source in ("sarvam", "paytm"):
            reworded = await _llm_rephrase(question, results)
            if reworded:
                answer = reworded
    return {
        "question": question, "answer": answer, "spoken_text": brief.spoken_version(answer),
        "tools": [{"name": r["name"], "args": r["args"], "data": r["data"]} for r in results],
        "table": results[0]["table"] if results else None,
        "tables": [{"tool": r["name"], **r["table"]} for r in results],
        "understood": bool(results), "source": source, "latency_ms": latency,
    }
