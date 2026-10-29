"""Distributor bill scan (F6).

POST /api/purchases/scan                 photo -> vision 'purchase_bill' -> catalog match -> price guard,
                                         scheme check, expiry, duplicate -> PendingAction(kind='purchase_bill')
POST /api/purchases/{action_id}/confirm  commit (optional per-line corrections in the body)
POST /api/purchases/{action_id}/cancel
GET  /api/purchases                      confirmed bill history
GET  /api/purchases/suppliers            suppliers with purchase stats
GET  /api/purchases/{bill_id}            one bill with its items

`suppliers_router` is the same suppliers list for mounting at /api/suppliers (see report).
Confirmation publishes `stock_updated` on channel `store`.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import PendingAction, Product, PurchaseBill, PurchaseItem, Supplier
from services import events, purchases as svc, vision
from services.clock import now_local
from services.types import ProviderError

router = APIRouter()
suppliers_router = APIRouter()


class LineEdit(BaseModel):
    """Correction for one proposal line, addressed by its `index`."""

    index: int
    qty: Optional[float] = Field(None, ge=0)
    rate: Optional[float] = Field(None, ge=0)
    mrp: Optional[float] = Field(None, ge=0)
    free_qty: Optional[float] = Field(None, ge=0, description="free units actually received")
    batch: Optional[str] = None
    expiry: Optional[str] = None
    scheme_text: Optional[str] = None
    unit: Optional[str] = None
    product_id: Optional[int] = Field(None, description="map this line to an existing product")
    create_product: Optional[bool] = Field(None, description="create a catalog product for this line")
    new_product: Optional[dict] = Field(None, description="overrides for the new product (name, mrp, unit...)")
    skip: Optional[bool] = Field(None, description="leave this line out of the bill")


class ConfirmBody(BaseModel):
    lines: List[LineEdit] = Field(default_factory=list)
    supplier_id: Optional[int] = None
    supplier_name: Optional[str] = None
    create_new_products: bool = False
    force: bool = Field(False, description="record even if the bill number already exists")


async def _read_image(image: UploadFile) -> tuple[bytes, str]:
    data = await image.read()
    if not data:
        raise HTTPException(400, "Empty image upload")
    return data, image.content_type or "image/jpeg"


def _action(db: Session, action_id: int) -> PendingAction:
    action = db.get(PendingAction, action_id)
    if action is None or action.kind != "purchase_bill":
        raise HTTPException(404, f"No purchase bill proposal {action_id}")
    return action


def _proposal_out(action: PendingAction) -> dict:
    return {"action_id": action.id, "kind": action.kind, "status": action.status, **(action.payload or {}),
            "source": action.source, "latency_ms": action.latency_ms or 0,
            "demo_mode": action.source == "fixture"}


@router.post("/scan")
async def scan_bill(image: UploadFile = File(...), db: Session = Depends(get_db)):
    """Photo of a distributor invoice -> proposal. Nothing is written to stock until confirm."""
    data, mime = await _read_image(image)
    try:
        result = await vision.extract_json_from_image(data, mime, "purchase_bill")
    except ProviderError as exc:
        raise HTTPException(502, f"Bill scan failed: {exc}") from exc
    proposal = svc.build_proposal(db, result.data)
    action = PendingAction(kind="purchase_bill", payload=proposal, status="proposed",
                           source=result.source, latency_ms=result.latency_ms)
    db.add(action)
    db.commit()
    db.refresh(action)
    return _proposal_out(action)


@router.post("/{action_id}/confirm")
def confirm_bill(action_id: int, body: Optional[ConfirmBody] = Body(None), db: Session = Depends(get_db)):
    """Commit the proposal: PurchaseBill + items, new stock batches, cost prices, new products."""
    action = _action(db, action_id)
    edits = body.model_dump(exclude_unset=True) if body else {}
    try:
        result, evts = svc.commit(db, action, edits)
        db.commit()
    except svc.PurchaseError as exc:
        db.rollback()
        raise HTTPException(exc.status, exc.args[0]) from exc
    for name, data in evts:
        events.publish("store", name, data)
    return {"action_id": action.id, "status": "confirmed", **result}


@router.post("/{action_id}/cancel")
def cancel_bill(action_id: int, db: Session = Depends(get_db)):
    action = _action(db, action_id)
    if action.status == "confirmed":
        raise HTTPException(409, "Bill already confirmed")
    action.status = "cancelled"
    action.resolved_at = now_local()
    db.commit()
    return {"action_id": action.id, "status": "cancelled"}


def _supplier_rows(db: Session) -> list[dict]:
    stats = {sid: (n, total, last) for sid, n, total, last in
             db.query(PurchaseBill.supplier_id, func.count(PurchaseBill.id),
                      func.coalesce(func.sum(PurchaseBill.total), 0.0), func.max(PurchaseBill.created_at))
             .filter(PurchaseBill.status == "confirmed").group_by(PurchaseBill.supplier_id).all()}
    products = dict(db.query(Product.supplier_id, func.count(Product.id))
                    .filter(Product.active.is_(True)).group_by(Product.supplier_id).all())
    out = []
    for s in db.query(Supplier).order_by(Supplier.id).all():
        n, total, last = stats.get(s.id, (0, 0.0, None))
        out.append({"id": s.id, "name": s.name, "contact_name": s.contact_name, "phone": s.phone,
                    "gstin": s.gstin, "visit_day": s.visit_day, "lead_days": s.lead_days,
                    "bills": n, "total_purchased": round(float(total), 2),
                    "last_bill_at": last, "products": products.get(s.id, 0)})
    return out


@router.get("/suppliers")
def list_suppliers_here(db: Session = Depends(get_db)):
    return _supplier_rows(db)


@suppliers_router.get("")
def list_suppliers(db: Session = Depends(get_db)):
    """GET /api/suppliers (when mounted)."""
    return _supplier_rows(db)


def _bill_out(bill: PurchaseBill, with_items: bool = False) -> dict:
    out = {"id": bill.id, "supplier_id": bill.supplier_id,
           "supplier": bill.supplier.name if bill.supplier else None, "bill_no": bill.bill_no,
           "bill_date": bill.bill_date, "total": bill.total, "status": bill.status, "flags": bill.flags or [],
           "items_count": len(bill.items), "created_at": bill.created_at}
    if with_items:
        out["items"] = [{
            "id": i.id, "product_id": i.product_id, "name": i.product.name if i.product else i.name_raw,
            "name_raw": i.name_raw, "qty": i.qty, "unit": i.unit, "rate": i.rate, "prev_rate": i.prev_rate,
            "mrp": i.mrp, "batch_no": i.batch_no, "expiry": i.expiry, "scheme_text": i.scheme_text,
            "free_qty_expected": i.free_qty_expected, "free_qty_received": i.free_qty_received,
            "flags": i.flags or []} for i in bill.items]
    return out


@router.get("")
def list_purchases(status: str = "confirmed", supplier_id: Optional[int] = None, limit: int = 50,
                   db: Session = Depends(get_db)):
    q = db.query(PurchaseBill)
    if status != "all":
        q = q.filter(PurchaseBill.status == status)
    if supplier_id:
        q = q.filter(PurchaseBill.supplier_id == supplier_id)
    bills = q.order_by(PurchaseBill.created_at.desc(), PurchaseBill.id.desc()).limit(max(1, min(limit, 200))).all()
    return [_bill_out(b) for b in bills]


@router.get("/{bill_id}")
def get_purchase(bill_id: int, db: Session = Depends(get_db)):
    bill = db.get(PurchaseBill, bill_id)
    if bill is None:
        raise HTTPException(404, f"No purchase bill {bill_id}")
    return _bill_out(bill, with_items=True)
