from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from database import get_db
from models import Product, Inventory, Transaction
from schemas import InventoryItem, RestockRequest
from pydantic import BaseModel
from typing import List


class ManualEditRequest(BaseModel):
    quantity: int
    reason: str = "manual_correction"


class AddProductRequest(BaseModel):
    name: str
    quantity: int
    unit: str = "unit"
    price: float = 0.0
    gst_rate: float = 0.0

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
        if item.product_id == 0:
            continue  # unmatched item from photo scan — skip
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


@router.post("/add-product")
def add_product(req: AddProductRequest, db: Session = Depends(get_db)):
    product = Product(
        name=req.name,
        name_hi=req.name,
        category="general",
        unit=req.unit,
        price=req.price,
        gst_rate=req.gst_rate,
        threshold=5,
    )
    db.add(product)
    db.flush()
    inv = Inventory(product_id=product.id, quantity=req.quantity, last_updated=datetime.utcnow())
    db.add(inv)
    db.add(Transaction(
        product_id=product.id,
        quantity_change=req.quantity,
        type="restock",
        amount=0.0,
        timestamp=datetime.utcnow(),
    ))
    db.commit()
    return {"success": True, "product_id": product.id, "name": product.name, "quantity": req.quantity}


@router.put("/{product_id}")
def update_inventory(product_id: int, req: ManualEditRequest, db: Session = Depends(get_db)):
    inv = db.query(Inventory).filter(Inventory.product_id == product_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Product not found in inventory")

    product = db.query(Product).filter(Product.id == product_id).first()
    old_qty = inv.quantity
    diff = req.quantity - old_qty

    inv.quantity = req.quantity
    inv.last_updated = datetime.utcnow()

    if diff != 0:
        db.add(Transaction(
            product_id=product_id,
            quantity_change=diff,
            type="manual_edit",
            amount=0.0,
            timestamp=datetime.utcnow(),
        ))

    db.commit()
    return {
        "success": True,
        "product_id": product_id,
        "name": product.name,
        "name_hi": product.name_hi,
        "old_quantity": old_qty,
        "new_quantity": req.quantity,
        "status": get_stock_status(req.quantity, product.threshold),
        "alert": req.quantity <= product.threshold,
    }
