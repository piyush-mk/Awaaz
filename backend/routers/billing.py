from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from database import get_db
from models import Product, Inventory, Transaction
from schemas import ParsedItem, Bill, BillItem, BillConfirmRequest
from typing import List

router = APIRouter()

MERCHANT_UPI = "paytm.merchant@paytm"
MERCHANT_NAME = "Ramesh General Store"


@router.post("/generate", response_model=Bill)
def generate_bill(items: List[ParsedItem], db: Session = Depends(get_db)):
    bill_items = []
    subtotal = 0.0
    total_gst = 0.0

    for item in items:
        product = None
        if item.product_id:
            product = db.query(Product).filter(Product.id == item.product_id).first()

        unit_price = product.price if product else item.price
        item_subtotal = unit_price * item.quantity
        gst_rate = product.gst_rate if product else item.gst_rate
        gst_amount = round(item_subtotal * gst_rate / 100, 2)
        item_total = item_subtotal + gst_amount

        bill_items.append(BillItem(
            product_id=product.id if product else None,
            name=product.name if product else item.name,
            name_hi=product.name_hi if product else item.name_hi,
            quantity=item.quantity,
            unit=product.unit if product else item.unit,
            unit_price=unit_price,
            subtotal=round(item_subtotal, 2),
            gst_rate=gst_rate,
            gst_amount=gst_amount,
            total=round(item_total, 2),
        ))

        subtotal += item_subtotal
        total_gst += gst_amount

    grand_total = round(subtotal + total_gst, 2)

    upi_string = (
        f"upi://pay?pa={MERCHANT_UPI}"
        f"&pn={MERCHANT_NAME.replace(' ', '%20')}"
        f"&am={grand_total}"
        f"&cu=INR"
        f"&tn=Purchase%20at%20{MERCHANT_NAME.replace(' ', '%20')}"
    )

    return Bill(
        items=bill_items,
        subtotal=round(subtotal, 2),
        total_gst=round(total_gst, 2),
        grand_total=grand_total,
        upi_string=upi_string,
    )


@router.post("/confirm")
def confirm_bill(req: BillConfirmRequest, db: Session = Depends(get_db)):
    updated_stock = []
    alerts = []

    for item in req.items:
        if not item.product_id:
            # Custom item: bill was generated, but there is no stock row to deduct.
            continue

        inv = db.query(Inventory).filter(Inventory.product_id == item.product_id).first()
        if not inv:
            raise HTTPException(status_code=404, detail=f"Inventory for product {item.product_id} not found")

        if inv.quantity < item.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock for {item.name}: {inv.quantity} available, {item.quantity} requested"
            )

        old_qty = inv.quantity
        inv.quantity -= item.quantity
        inv.last_updated = datetime.utcnow()

        product = db.query(Product).filter(Product.id == item.product_id).first()

        db.add(Transaction(
            product_id=item.product_id,
            quantity_change=-item.quantity,
            type="sale",
            amount=item.total,
            timestamp=datetime.utcnow(),
        ))

        stock_info = {
            "product_id": item.product_id,
            "name": item.name,
            "name_hi": item.name_hi,
            "old_quantity": old_qty,
            "new_quantity": inv.quantity,
            "unit": item.unit,
        }
        updated_stock.append(stock_info)

        if product and inv.quantity <= product.threshold:
            alerts.append({
                "product_id": item.product_id,
                "name": item.name,
                "name_hi": item.name_hi,
                "quantity": inv.quantity,
                "threshold": product.threshold,
            })

    db.commit()

    return {
        "success": True,
        "grand_total": req.grand_total,
        "updated_stock": updated_stock,
        "low_stock_alerts": alerts,
        "payment_message": f"Payment received via Paytm UPI. ₹{req.grand_total} collected.",
    }
