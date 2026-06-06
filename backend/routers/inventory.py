from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from database import get_db
from models import Product, Inventory, Transaction
from schemas import InventoryItem, RestockRequest, ParsedItem
from typing import List
import re

router = APIRouter()


def _normalize_name(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s\u0900-\u097F-]", " ", (text or "").lower())).strip()


def _find_existing_product(db: Session, item: ParsedItem) -> Product | None:
    candidates = [item.name, item.name_hi]
    for candidate in candidates:
        cleaned = _normalize_name(candidate)
        if not cleaned:
            continue
        product = db.query(Product).filter(Product.name.ilike(f"%{cleaned}%")).first()
        if product:
            return product
        product = db.query(Product).filter(Product.name_hi.ilike(f"%{cleaned}%")).first()
        if product:
            return product
    return None


def _create_product_from_item(db: Session, item: ParsedItem) -> Product:
    product = Product(
        name=item.name,
        name_hi=item.name_hi or item.name,
        category="general",
        unit=item.unit,
        price=item.price,
        gst_rate=item.gst_rate,
        threshold=max(1, min(10, item.quantity)),
    )
    db.add(product)
    db.flush()
    return product


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
        product = None
        if item.product_id:
            product = db.query(Product).filter(Product.id == item.product_id).first()
        if not product:
            product = _find_existing_product(db, item)
        if not product:
            product = _create_product_from_item(db, item)

        inv = db.query(Inventory).filter(Inventory.product_id == product.id).first()
        if not inv:
            inv = Inventory(product_id=product.id, quantity=0)
            db.add(inv)

        old_qty = inv.quantity
        inv.quantity += item.quantity
        inv.last_updated = datetime.utcnow()

        db.add(Transaction(
            product_id=product.id,
            quantity_change=item.quantity,
            type="restock",
            amount=0.0,
            timestamp=datetime.utcnow(),
        ))

        updated.append({
            "product_id": product.id,
            "name": product.name,
            "name_hi": product.name_hi,
            "old_quantity": old_qty,
            "new_quantity": inv.quantity,
            "unit": product.unit,
            "alert": inv.quantity <= product.threshold if product else False,
            "created": bool(item.product_id is None),
        })

    db.commit()
    return {"success": True, "updated": updated}
