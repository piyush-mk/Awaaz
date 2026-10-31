"""Khata / udhaar ledger, salary-day reminders, passbook, Postpaid (simulated) and notebook import.

GET  /api/khata/customers                      balances, last payment, late payments, suggested limit, risk
POST /api/khata/customers                      add a customer
PATCH /api/khata/customers/{id}                edit name / phone / limit / language
GET  /api/khata/customers/{id}                 summary + ledger (newest first, running balance)
POST /api/khata/entries                        give udhaar / receive payment (+ WhatsApp + limit warning)
POST /api/khata/entries/{id}/confirm           customer-confirmed flag    (/dispute for the opposite)
POST /api/khata/reminders/preview|send         salary-day reminders (balance > 0)
GET  /api/khata/passbook/{token}               public customer passbook page (HTML);
GET  /api/khata/customers/{id}/passbook        same page by id (merchant side)
POST /api/khata/postpaid/offer                 SIMULATED Paytm Postpaid offer
POST /api/khata/postpaid/{offer_id}/approve    SIMULATED approval: shop paid now
GET  /api/khata/postpaid/{offer_id}[/page]     offer JSON / simulated approval page
POST /api/khata/import-photo                   notebook photo -> proposal (PendingAction khata_import)
GET  /api/khata/import/{action_id}             the proposal
POST /api/khata/import/{action_id}/confirm     create customers + opening entries

`public_router` serves GET /{token} for a `/k` mount: app.include_router(khata.public_router, prefix="/k").
"""
from __future__ import annotations

import html
from typing import Any, Literal, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import Customer, KhataEntry, PendingAction
from services import events, postpaid, vision
from services import khata as kh
from services import whatsapp as wa
from services.clock import now_local, today_local

router = APIRouter()
public_router = APIRouter()


# ---------------------------------------------------------------------------
# customers
# ---------------------------------------------------------------------------


def _customer_or_404(db: Session, customer_id: int) -> Customer:
    c = db.get(Customer, customer_id)
    if c is None:
        raise HTTPException(404, "customer not found")
    return c


@router.get("/customers")
def list_customers(min_balance: Optional[float] = None, q: Optional[str] = None,
                   sort: Literal["balance", "name", "risk", "recent"] = "balance",
                   db: Session = Depends(get_db)):
    rows = [kh.customer_summary(db, c) for c in db.query(Customer).order_by(Customer.id).all()
            if not kh.is_walk_in(c)]
    if min_balance is not None:
        rows = [r for r in rows if r["balance"] >= min_balance]
    if q:
        needle = q.lower()
        rows = [r for r in rows if needle in (r["name"] or "").lower() or needle in (r["name_hi"] or "")]
    order = {"high": 0, "medium": 1, "low": 2}
    if sort == "name":
        rows.sort(key=lambda r: r["name"].lower())
    elif sort == "risk":
        rows.sort(key=lambda r: (order[r["risk"]], -r["balance"]))
    elif sort == "recent":
        rows.sort(key=lambda r: r["last_entry_at"] or "", reverse=True)
    else:
        rows.sort(key=lambda r: -r["balance"])
    return rows


class CustomerIn(BaseModel):
    name: str = Field(min_length=1)
    name_hi: Optional[str] = None
    phone: Optional[str] = None
    upi_id: Optional[str] = None
    language: Optional[str] = None
    credit_limit: Optional[float] = None


@router.post("/customers", status_code=201)
def create_customer(payload: CustomerIn, db: Session = Depends(get_db)):
    c = Customer(name=payload.name.strip(), name_hi=payload.name_hi, phone=payload.phone, upi_id=payload.upi_id,
                 language=payload.language or "hi-IN",
                 credit_limit=payload.credit_limit if payload.credit_limit is not None else kh.DEFAULT_CREDIT_LIMIT)
    db.add(c)
    db.commit()
    return kh.customer_summary(db, c)


class CustomerPatch(BaseModel):
    name: Optional[str] = None
    name_hi: Optional[str] = None
    phone: Optional[str] = None
    upi_id: Optional[str] = None
    language: Optional[str] = None
    credit_limit: Optional[float] = None


@router.patch("/customers/{customer_id}")
def update_customer(customer_id: int, payload: CustomerPatch, db: Session = Depends(get_db)):
    c = _customer_or_404(db, customer_id)
    for field in ("name", "name_hi", "phone", "upi_id", "language", "credit_limit"):
        value = getattr(payload, field)
        if value is not None:
            setattr(c, field, value)
    db.commit()
    return kh.customer_summary(db, c)


@router.get("/customers/{customer_id}")
def get_customer(customer_id: int, db: Session = Depends(get_db)):
    c = _customer_or_404(db, customer_id)
    return {**kh.customer_summary(db, c), "entries": kh.ledger(db, c.id)}


# ---------------------------------------------------------------------------
# entries
# ---------------------------------------------------------------------------


class EntryIn(BaseModel):
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None  # spoken name, fuzzy matched when customer_id is absent
    kind: Literal["credit", "payment"] = "credit"
    amount: float = Field(gt=0)
    note: Optional[str] = None
    invoice_id: Optional[int] = None
    send_whatsapp: bool = True
    enforce_limit: bool = False  # True: refuse (409) when the limit would be passed


@router.post("/entries")
def add_entry(payload: EntryIn, db: Session = Depends(get_db)):
    customer = kh.resolve_customer(db, payload.customer_id, payload.customer_name)
    if customer is None:
        raise HTTPException(404, "customer not found (give customer_id or a matching customer_name)")
    try:
        if payload.kind == "credit":
            result = kh.give_credit(db, customer, payload.amount, payload.note, payload.invoice_id,
                                    payload.send_whatsapp, payload.enforce_limit)
        else:
            result = kh.receive_payment(db, customer, payload.amount, payload.note, payload.invoice_id,
                                        payload.send_whatsapp)
    except kh.LimitExceeded as exc:
        raise HTTPException(409, detail={"error": "credit_limit_exceeded", "warning": exc.warning})
    db.commit()
    db.refresh(result.entry)
    return result.to_dict()


def _entry_or_404(db: Session, entry_id: int) -> KhataEntry:
    e = db.get(KhataEntry, entry_id)
    if e is None:
        raise HTTPException(404, "entry not found")
    return e


class ConfirmIn(BaseModel):
    confirmed: bool = True
    note: Optional[str] = None


@router.post("/entries/{entry_id}/confirm")
def confirm_entry(entry_id: int, payload: ConfirmIn = Body(default_factory=ConfirmIn),
                  db: Session = Depends(get_db)):
    """Customer-confirmed flag (also used when the merchant ticks it by hand)."""
    e = kh.set_confirmation(db, _entry_or_404(db, entry_id), payload.confirmed, payload.note)
    db.commit()
    return kh.entry_dict(e)


@router.post("/entries/{entry_id}/dispute")
def dispute_entry(entry_id: int, payload: ConfirmIn = Body(default_factory=ConfirmIn),
                  db: Session = Depends(get_db)):
    e = _entry_or_404(db, entry_id)
    kh.set_confirmation(db, e, False, payload.note or "marked by shopkeeper")
    c = db.get(Customer, e.customer_id)
    events.publish_after_commit(db, "store", "khata_disputed", {
        "entry_id": e.id, "customer_id": e.customer_id, "customer": c.name if c else None,
        "amount": e.amount, "balance": kh.balance(db, e.customer_id), "text": payload.note or ""})
    db.commit()
    return kh.entry_dict(e)


# ---------------------------------------------------------------------------
# salary-day reminders
# ---------------------------------------------------------------------------


class ReminderIn(BaseModel):
    customer_ids: Optional[list[int]] = None
    min_balance: float = 1.0


def _reminder_header(rows: list[dict[str, Any]]) -> dict[str, Any]:
    in_window = kh.in_salary_window(today_local())
    return {
        "in_salary_window": in_window,
        "window_note": ("Salary-day reminders are meant for the 1st-7th of the month, when most "
                        "salaries arrive." + ("" if in_window else " Today is outside that window.")),
        "count": len(rows),
        "total_due": round(sum(r["balance"] for r in rows), 2),
    }


@router.post("/reminders/preview")
def reminders_preview(payload: ReminderIn = Body(default_factory=ReminderIn), db: Session = Depends(get_db)):
    rows = kh.reminder_candidates(db, payload.min_balance, payload.customer_ids)
    return {**_reminder_header(rows), "reminders": rows}


@router.post("/reminders/send")
def reminders_send(payload: ReminderIn = Body(default_factory=ReminderIn), db: Session = Depends(get_db)):
    rows = kh.reminder_candidates(db, payload.min_balance, payload.customer_ids)
    sent = []
    for r in rows:
        msg = wa.notify(db, r["phone"], r["text"], customer_id=r["customer_id"])
        sent.append({"customer_id": r["customer_id"], "name": r["name"], "balance": r["balance"],
                     "message_id": msg.id, "status": msg.status, "has_phone": r["has_phone"]})
    events.publish_after_commit(db, "store", "khata_reminders_sent", {"count": len(sent), "total_due": _reminder_header(rows)["total_due"]})
    db.commit()
    return {**_reminder_header(rows), "sent": sent}


# ---------------------------------------------------------------------------
# passbook page
# ---------------------------------------------------------------------------

_PAGE_CSS = """
:root{--bg:#F5F7FA;--card:#fff;--ink:#0b1f33;--mut:#5b6b7b;--blue:#00B9F5;--red:#d93025;--green:#1e8e3e}
@media (prefers-color-scheme:dark){:root{--bg:#0b1620;--card:#13232f;--ink:#e8f1f8;--mut:#93a4b3;--red:#ff6b61;--green:#5cd68a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.4 -apple-system,Segoe UI,Roboto,sans-serif}
.w{max-width:480px;margin:0 auto;padding:16px}.card{background:var(--card);border-radius:14px;padding:16px;margin-bottom:12px}
h1{font-size:20px;margin:0 0 2px}.mut{color:var(--mut);font-size:14px}.bal{font-size:36px;font-weight:700;margin:6px 0}
.row{display:flex;justify-content:space-between;gap:12px;padding:10px 0;border-top:1px solid rgba(128,128,128,.2)}
.row:first-child{border-top:0}.cr{color:var(--red)}.pay{color:var(--green)}.tag{font-size:12px;color:var(--red)}
a.btn,button.btn{display:block;text-align:center;background:var(--blue);color:#00263a;font-weight:700;border:0;
border-radius:12px;padding:14px;min-height:48px;text-decoration:none;width:100%;font-size:17px}
"""


def passbook_html(db: Session, c: Customer) -> str:
    bal = kh.balance(db, c.id)
    e = html.escape
    rows = []
    for item in kh.ledger(db, c.id)[:60]:
        credit = item["amount"] > 0
        label = e(item["note"] or ("Udhaar" if credit else "Jama"))
        flag = ' <span class="tag">galat bataya</span>' if item["disputed"] else ""
        rows.append(
            f'<div class="row"><div>{label}{flag}<div class="mut">{e((item["at"] or "")[:10])}</div></div>'
            f'<div class="{"cr" if credit else "pay"}">{"+" if credit else "-"}₹{kh.fmt_inr(abs(item["amount"]))}'
            f'<div class="mut">baaki ₹{kh.fmt_inr(item["running_balance"])}</div></div></div>')
    pay = (f'<a class="btn" href="{e(kh.pay_link(bal, "Khata"))}">₹{kh.fmt_inr(bal)} abhi chukayein (UPI)</a>'
           if bal > 0 else '<div class="mut">Aapka khata saaf hai. Dhanyavaad!</div>')
    return (f'<!doctype html><html lang="hi"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{e(c.name)} ka khata</title><style>{_PAGE_CSS}</style></head><body><div class="w">'
            f'<div class="card"><h1>{e(c.name)} ka khata</h1><div class="mut">{e(settings.merchant_name)}</div>'
            f'<div class="bal">₹{kh.fmt_inr(bal)}</div><div class="mut">{"baaki hai" if bal > 0 else "koi baaki nahi"}</div>'
            f'<div style="height:12px"></div>{pay}</div>'
            f'<div class="card"><b>Hisaab</b>{"".join(rows) or "<div class=mut>Abhi koi entry nahi.</div>"}</div>'
            f'<div class="mut">Koi entry galat lage toh WhatsApp par "galat" likh kar bhejein.</div>'
            f'</div></body></html>')


@router.get("/passbook/{token}", response_class=HTMLResponse)
def passbook_by_token(token: str, db: Session = Depends(get_db)):
    cid = kh.customer_id_from_token(token)
    c = db.get(Customer, cid) if cid else None
    if c is None:
        raise HTTPException(404, "passbook not found")
    return HTMLResponse(passbook_html(db, c))


@router.get("/customers/{customer_id}/passbook", response_class=HTMLResponse)
def passbook_by_id(customer_id: int, db: Session = Depends(get_db)):
    return HTMLResponse(passbook_html(db, _customer_or_404(db, customer_id)))


@public_router.get("/{token}", response_class=HTMLResponse)
def passbook_public(token: str, db: Session = Depends(get_db)):
    return passbook_by_token(token, db)


# ---------------------------------------------------------------------------
# Postpaid (simulated)
# ---------------------------------------------------------------------------


class PostpaidOfferIn(BaseModel):
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    amount: float = Field(gt=0)
    invoice_id: Optional[int] = None
    send_whatsapp: bool = False


@router.post("/postpaid/offer")
def postpaid_offer(payload: PostpaidOfferIn, db: Session = Depends(get_db)):
    customer = kh.resolve_customer(db, payload.customer_id, payload.customer_name)
    if customer is None:
        raise HTTPException(404, "customer not found")
    out = postpaid.create_offer(db, customer, payload.amount, payload.invoice_id, payload.send_whatsapp)
    db.commit()
    return out


def _offer_or_404(db: Session, offer_id: int) -> PendingAction:
    action = postpaid.get_offer(db, offer_id)
    if action is None:
        raise HTTPException(404, "postpaid offer not found")
    return action


@router.get("/postpaid/{offer_id}")
def postpaid_get(offer_id: int, db: Session = Depends(get_db)):
    return postpaid.view(_offer_or_404(db, offer_id))


@router.post("/postpaid/{offer_id}/approve")
def postpaid_approve(offer_id: int, db: Session = Depends(get_db)):
    action = _offer_or_404(db, offer_id)
    try:
        out = postpaid.approve(db, action)
    except postpaid.OfferError as exc:
        raise HTTPException(exc.status, exc.detail)
    db.commit()
    return out


@router.get("/postpaid/{offer_id}/page", response_class=HTMLResponse)
def postpaid_page(offer_id: int, db: Session = Depends(get_db)):
    """The page a customer opens from the WhatsApp link. SIMULATED: the button calls the approve endpoint."""
    action = _offer_or_404(db, offer_id)
    p, e = action.payload or {}, html.escape
    done = action.status == "confirmed"
    btn = ('<div class="mut">Approved (simulated). Dhanyavaad!</div>' if done else
           f'<button class="btn" onclick="fetch(\'/api/khata/postpaid/{offer_id}/approve\',{{method:\'POST\'}})'
           f'.then(()=>location.reload())">Paytm Postpaid se chukayein</button>')
    return HTMLResponse(
        f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>Paytm Postpaid (simulated)</title><style>{_PAGE_CSS}</style></head><body><div class="w">'
        f'<div class="card"><h1>Pay with Paytm Postpaid</h1><div class="tag">SIMULATED DEMO - no real money moves</div>'
        f'<div class="bal">₹{kh.fmt_inr(p.get("amount", 0))}</div>'
        f'<div class="mut">{e(settings.merchant_name)} - {e(str(p.get("customer", "")))}</div>'
        f'<p>{e(str(p.get("message_hi", "")))}</p>{btn}</div></div></body></html>')


# ---------------------------------------------------------------------------
# notebook photo import (F11)
# ---------------------------------------------------------------------------


@router.post("/import-photo")
async def import_photo(request: Request, db: Session = Depends(get_db)):
    """multipart upload (field `image`, `file` or `photo`) of a khata notebook page -> proposal."""
    form = await request.form()
    upload = next((form.get(k) for k in ("image", "file", "photo") if hasattr(form.get(k), "read")), None)
    if upload is None:
        raise HTTPException(422, "upload the notebook page as multipart field 'image'")
    data = await upload.read()
    mime = getattr(upload, "content_type", None) or "image/jpeg"
    try:
        result = await vision.extract_json_from_image(data, mime, "khata_page")
    except Exception as exc:  # noqa: BLE001 - DEMO_MODE=off with failing providers
        raise HTTPException(502, f"could not read the page: {str(exc)[:200]}")
    rows = kh.propose_import(db, result.data)
    action = PendingAction(kind="khata_import", status="proposed", source=result.source,
                           latency_ms=result.latency_ms, payload={"rows": rows})
    db.add(action)
    db.commit()
    return _import_view(action)


def _import_view(action: PendingAction) -> dict[str, Any]:
    rows = (action.payload or {}).get("rows", [])
    return {
        "action_id": action.id, "status": action.status, "source": action.source,
        "latency_ms": action.latency_ms, "rows": rows,
        "summary": {"rows": len(rows), "new_customers": sum(1 for r in rows if r["action"] == "create"),
                    "existing": sum(1 for r in rows if r["action"] == "add_to_existing"),
                    "included_amount": round(sum(r["amount"] for r in rows if r["include"]), 2)},
        "result": action.result,
    }


def _import_or_404(db: Session, action_id: int) -> PendingAction:
    action = db.get(PendingAction, action_id)
    if action is None or action.kind != "khata_import":
        raise HTTPException(404, "import not found")
    return action


class ImportRowEdit(BaseModel):
    index: int
    include: Optional[bool] = None
    name: Optional[str] = None
    amount: Optional[float] = None
    customer_id: Optional[int] = None


class ImportConfirmIn(BaseModel):
    rows: list[ImportRowEdit] = Field(default_factory=list)


@router.get("/import/{action_id}")
def import_get(action_id: int, db: Session = Depends(get_db)):
    return _import_view(_import_or_404(db, action_id))


@router.post("/import/{action_id}/confirm")
def import_confirm(action_id: int, payload: ImportConfirmIn = Body(default_factory=ImportConfirmIn),
                   db: Session = Depends(get_db)):
    action = _import_or_404(db, action_id)
    if action.status != "proposed":
        raise HTTPException(409, f"import is already {action.status}")
    edits = [e.model_dump(exclude_none=True) for e in payload.rows]
    result = kh.commit_import(db, action, edits)
    action.status = "confirmed"
    action.resolved_at = now_local()
    action.result = result
    events.publish_after_commit(db, "store", "khata_imported", {"action_id": action.id, **{
        k: result[k] for k in ("total_imported", "skipped")}, "customers": len(result["created_customers"]),
        "entries": len(result["entries"])})
    db.commit()
    return {"action_id": action.id, "status": "confirmed", **result}
