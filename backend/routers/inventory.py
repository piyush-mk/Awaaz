"""Legacy inventory API (shapes unchanged), now backed by StockBatch / StockMove."""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import Product
from schemas import InventoryItem, RestockRequest
from services import stock_ops
from services.clock import now_local


class ManualEditRequest(BaseModel):
    quantity: float
    reason: str = "manual_correction"


class AddProductRequest(BaseModel):
    name: str
    quantity: float
    unit: str = "unit"
    price: float = 0.0
    gst_rate: float = 0.0


router = APIRouter()


def get_stock_status(quantity: float, threshold: float) -> str:
    return stock_ops.stock_status(quantity, threshold)


@router.get("", response_model=List[InventoryItem])
def get_inventory(db: Session = Depends(get_db)):
    stock = stock_ops.stock_map(db)
    result = []
    for p in db.query(Product).filter(Product.active.is_(True)).order_by(Product.id).all():
        qty = stock.get(p.id, 0.0)
        result.append(InventoryItem(
            product_id=p.id, name=p.name, name_hi=p.name_hi or "", category=p.category or "general",
            unit=p.unit or "", price=p.price, gst_rate=p.gst_rate or 0.0, quantity=qty,
            threshold=p.threshold or 0.0, status=get_stock_status(qty, p.threshold or 0.0),
        ))
    return result


@router.post("/restock")
def restock_inventory(req: RestockRequest, db: Session = Depends(get_db)):
    updated = []
    for item in req.items:
        if not item.product_id:
            continue  # unmatched/custom item: skip restock
        product = db.get(Product, item.product_id)
        if product is None:
            continue
        old_qty = stock_ops.current_stock(db, product.id)
        stock_ops.add_stock(db, product.id, item.quantity, cost_price=product.cost_price,
                            supplier_id=product.supplier_id, note="voice/photo restock")
        new_qty = round(old_qty + item.quantity, 3)
        updated.append({
            "product_id": product.id, "name": item.name, "name_hi": item.name_hi,
            "old_quantity": old_qty, "new_quantity": new_qty, "unit": item.unit,
            "alert": new_qty <= (product.threshold or 0.0),
        })
    db.commit()
    return {"success": True, "updated": updated}


@router.post("/add-product")
def add_product(req: AddProductRequest, db: Session = Depends(get_db)):
    product = Product(name=req.name, name_hi=req.name, aliases=[req.name], category="general",
                      unit=req.unit, mrp=req.price, gst_rate=req.gst_rate, threshold=5)
    db.add(product)
    db.flush()
    stock_ops.add_stock(db, product.id, req.quantity, note="new product", at=now_local())
    db.commit()
    return {"success": True, "product_id": product.id, "name": product.name, "quantity": req.quantity}


@router.put("/{product_id}")
def update_inventory(product_id: int, req: ManualEditRequest, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found in inventory")
    old_qty = stock_ops.current_stock(db, product_id)
    stock_ops.set_stock(db, product_id, req.quantity, kind="adjust", note=req.reason)
    db.commit()
    threshold = product.threshold or 0.0
    return {
        "success": True, "product_id": product_id, "name": product.name, "name_hi": product.name_hi,
        "old_quantity": old_qty, "new_quantity": req.quantity,
        "status": get_stock_status(req.quantity, threshold), "alert": req.quantity <= threshold,
    }
