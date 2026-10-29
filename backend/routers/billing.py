"""Legacy bill API (shapes unchanged). GST is now MRP-inclusive: `subtotal` is the
taxable value and `grand_total` equals the sum of MRP x qty (Rs 249 for the demo cart).
`/confirm` now writes a real Invoice + Payment and deducts stock FIFO."""
from typing import List
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import Payment, Product
from schemas import Bill, BillConfirmRequest, BillItem, CartLine, ParsedItem
from services import events, invoicing, pricing, stock_ops
from services.clock import now_local

router = APIRouter()


def upi_string(amount: float, note: str = "Purchase at store") -> str:
    return (f"upi://pay?pa={quote(settings.merchant_upi_vpa)}&pn={quote(settings.merchant_name)}"
            f"&am={amount:.2f}&cu=INR&tn={quote(note)}")


@router.post("/generate", response_model=Bill)
def generate_bill(items: List[ParsedItem], db: Session = Depends(get_db)):
    store = invoicing.get_store(db)
    bill_items: list[BillItem] = []
    priced = []
    for item in items:
        product = db.get(Product, item.product_id) if item.product_id else None
        if product is None:
            raise HTTPException(status_code=404, detail=f"Product {item.product_id} not found")
        lt = pricing.price_line(item.quantity, product.price, product.gst_rate or 0.0,
                                bool(store.composition_scheme))
        priced.append(lt)
        bill_items.append(BillItem(
            product_id=product.id, name=product.name, name_hi=product.name_hi or "",
            quantity=item.quantity, unit=product.unit or "", unit_price=product.price,
            subtotal=lt.taxable, gst_rate=lt.gst_rate, gst_amount=round(lt.cgst + lt.sgst, 2),
            total=lt.total))
    totals = pricing.totals_for_lines(priced, bool(store.composition_scheme))
    return Bill(items=bill_items, subtotal=totals.taxable, total_gst=round(totals.cgst + totals.sgst, 2),
                grand_total=totals.total,
                upi_string=upi_string(totals.total, f"Purchase at {settings.merchant_name}"))


@router.post("/confirm")
def confirm_bill(req: BillConfirmRequest, db: Session = Depends(get_db)):
    lines: list[CartLine] = []
    for item in req.items:
        product = db.get(Product, item.product_id)
        if product is None:
            raise HTTPException(status_code=404, detail=f"Inventory for product {item.product_id} not found")
        available = stock_ops.current_stock(db, product.id)
        if available + 1e-9 < item.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock for {item.name}: {available:g} available, {item.quantity:g} requested")
        lines.append(CartLine(
            product_id=product.id, name=product.name, name_hi=product.name_hi or "", qty=item.quantity,
            unit=product.unit or "", sell_mode=product.sell_mode or "unit", base_unit=product.base_unit or "pc",
            unit_price=product.price, line_total=round(product.price * item.quantity, 2),
            gst_rate=product.gst_rate or 0.0))
    now = now_local()
    invoice = invoicing.create_invoice(db, lines, status="paid", at=now)
    db.add(Payment(invoice_id=invoice.id, mode="upi", amount=invoice.total, status="success",
                   order_id=f"ORD-LEG-{invoice.id}", rail="simulated", created_at=now, paid_at=now))
    updated_stock = invoicing.deduct_invoice_stock(db, invoice, allow_negative=False, at=now)
    alerts = []
    for info in updated_stock:
        product = db.get(Product, info["product_id"])
        if product and info["new_quantity"] <= (product.threshold or 0.0):
            alerts.append({"product_id": product.id, "name": product.name, "name_hi": product.name_hi,
                           "quantity": info["new_quantity"], "threshold": product.threshold})
    db.commit()
    events.publish("store", "payment_received", {"invoice_id": invoice.id, "number": invoice.number,
                                                 "amount": invoice.total})
    return {
        "success": True, "grand_total": invoice.total, "updated_stock": updated_stock,
        "low_stock_alerts": alerts, "invoice_number": invoice.number,
        "payment_message": f"Payment received via Paytm UPI. Rs {invoice.total:g} collected.",
    }
