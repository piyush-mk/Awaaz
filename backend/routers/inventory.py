from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from database import get_db
from models import Product, Inventory, Transaction
from schemas import InventoryItem, RestockRequest, ParsedItem
from typing import List

router = APIRouter()


def get_stock_status(quantity: int, threshold: int) -> str:
    if quantity <= threshold:
        return "low"
    elif quantity <= threshold * 2:
        return "medium"
    return "high"


@router.get("", response_model=List[InventoryItem])
def get_inventory(db: Session = Depends(get_db)):
    products = db.query(Product).all()
    result = []
    for p in products:
        inv = p.inventory
        qty = inv.quantity if inv else 0
        result.append(InventoryItem(
            product_id=p.id,
            name=p.name,
            name_hi=p.name_hi,
            category=p.category,
            unit=p.unit,
            price=p.price,
            gst_rate=p.gst_rate,
            quantity=qty,
            threshold=p.threshold,
            status=get_stock_status(qty, p.threshold),
        ))
    return result


@router.post("/restock")
def restock_inventory(req: RestockRequest, db: Session = Depends(get_db)):
    updated = []
    for item in req.items:
        inv = db.query(Inventory).filter(Inventory.product_id == item.product_id).first()
        if not inv:
            inv = Inventory(product_id=item.product_id, quantity=0)
            db.add(inv)

        old_qty = inv.quantity
        inv.quantity += item.quantity
        inv.last_updated = datetime.utcnow()

        db.add(Transaction(
            product_id=item.product_id,
            quantity_change=item.quantity,
            type="restock",
            amount=0.0,
            timestamp=datetime.utcnow(),
        ))

        product = db.query(Product).filter(Product.id == item.product_id).first()
        updated.append({
            "product_id": item.product_id,
            "name": item.name,
            "name_hi": item.name_hi,
            "old_quantity": old_qty,
            "new_quantity": inv.quantity,
            "unit": item.unit,
            "alert": inv.quantity <= product.threshold if product else False,
        })

    db.commit()
    return {"success": True, "updated": updated}
