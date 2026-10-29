"""Counter cart (Agent A). Carts are keyed by session id and stored in models.Cart.

POST   /api/cart                          open a cart {session_id?, customer_id?} -> CartView
GET    /api/cart/{id}                     CartView (created empty on first use)
DELETE /api/cart/{id}                     clear the cart (new customer)
POST   /api/cart/{id}/lines               add/set lines {items:[{product_id|name, qty?, unit?, amount_rupees?}], mode}
PUT    /api/cart/{id}/lines/{product_id}  set quantity {qty, unit?} (qty 0 removes)
DELETE /api/cart/{id}/lines/{product_id}  remove a line
POST   /api/cart/{id}/customer            attach a customer {customer_id | upi_id | phone | name}
POST   /api/cart/{id}/usual               add the attached (or given) customer's usual basket
POST   /api/cart/{id}/checkout            Invoice(pending) + Payments + UPI intent; publishes `checkout`
GET    /api/cart/usual/{customer_id}      F16 usual basket as cart lines (also /api/cart/usual?upi_id=&phone=&name=)

`customers_router` (GET /api/customers/{id}/usual, GET /api/customers/lookup) is the same data under
the customer path; it only works once main.py mounts it at /api/customers (see the report).
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from services import catalog, counter, events, payments
from services.counter import CartView

router = APIRouter()
customers_router = APIRouter()


class OpenCart(BaseModel):
    session_id: Optional[str] = None
    customer_id: Optional[int] = None


class LineSpec(BaseModel):
    product_id: Optional[int] = None
    name: Optional[str] = None
    qty: Optional[float] = None
    unit: Optional[str] = None
    amount_rupees: Optional[float] = None


class LinesBody(BaseModel):
    items: list[LineSpec] = Field(default_factory=list)
    mode: str = "add"  # add | set


class QtyBody(BaseModel):
    qty: float
    unit: Optional[str] = None


class CustomerBody(BaseModel):
    customer_id: Optional[int] = None
    upi_id: Optional[str] = None
    phone: Optional[str] = None
    name: Optional[str] = None


class CheckoutBody(BaseModel):
    customer_id: Optional[int] = None
    splits: Optional[dict] = None  # {"cash": 300, "upi": 200, "khata": null, "customer_id": 2}
    rail: Optional[str] = None  # upi_intent (default) | simulated
    note: Optional[str] = None
    speak: bool = True


def _open_cart(db: Session, cart_id: str):
    return counter.get_cart(db, cart_id)


def _edit_cart(db: Session, cart_id: str):
    return counter.get_cart(db, cart_id, fresh_if_done=True)


def _done(db: Session, cart) -> CartView:
    db.commit()
    counter.announce_cart(db, cart, stage="manual")
    return counter.cart_view(db, cart)


@router.post("", response_model=CartView)
def create_cart(body: Optional[OpenCart] = None, db: Session = Depends(get_db)):
    body = body or OpenCart()
    cart = counter.get_cart(db, (body.session_id or uuid.uuid4().hex[:10]).strip(), fresh_if_done=True)
    if body.customer_id:
        if db.get(counter.Customer, body.customer_id) is None:
            raise HTTPException(404, f"Customer {body.customer_id} nahi mila")
        cart.customer_id = body.customer_id
    return _done(db, cart)


# F16: static paths first so they never match /{cart_id}
@router.get("/usual")
def usual_lookup(upi_id: Optional[str] = None, phone: Optional[str] = None, name: Optional[str] = None,
                 db: Session = Depends(get_db)):
    """Find a customer by UPI id / phone / name and return their usual basket as cart lines."""
    customer = counter.lookup_customer(db, upi_id=upi_id, phone=phone, name=name)
    if customer is None:
        raise HTTPException(404, "Customer nahi mila")
    return counter.usual_view(db, customer)


@router.get("/usual/{customer_id}")
def usual_by_id(customer_id: int, db: Session = Depends(get_db)):
    customer = db.get(counter.Customer, customer_id)
    if customer is None:
        raise HTTPException(404, f"Customer {customer_id} nahi mila")
    return counter.usual_view(db, customer)


@router.get("/{cart_id}", response_model=CartView)
def get_cart(cart_id: str, db: Session = Depends(get_db)):
    cart = _open_cart(db, cart_id)
    db.commit()
    return counter.cart_view(db, cart)


@router.delete("/{cart_id}", response_model=CartView)
def clear_cart(cart_id: str, db: Session = Depends(get_db)):
    cart = _open_cart(db, cart_id)
    counter.reset_cart(cart)
    db.commit()
    events.publish("store", "cart_updated", {"session_id": cart.id, "cart": counter.view_json(db, cart),
                                             "stage": "cleared"})
    return counter.cart_view(db, cart)


@router.post("/{cart_id}/lines", response_model=CartView)
def edit_lines(cart_id: str, body: LinesBody, db: Session = Depends(get_db)):
    """mode=add merges quantities into existing lines; mode=set replaces the quantity of a product
    (qty 0 removes it). A product can be given by product_id or a spoken/typed name."""
    if body.mode not in ("add", "set"):
        raise HTTPException(422, "mode must be 'add' or 'set'")
    cart = _edit_cart(db, cart_id)
    if cart.status != "open":
        raise HTTPException(409, "Bill ban chuka hai; naya cart shuru karein (DELETE /api/cart/{id})")
    index = catalog.load_index(db)
    lines = counter.read_lines(cart)
    unknown: list[str] = []
    for spec in body.items:
        d = spec.model_dump(exclude_none=True)
        if body.mode == "add":
            ln = counter.line_from_spec(db, index, d)
            if ln is None:
                unknown.append(str(d.get("name") or d.get("product_id")))
                continue
            counter.merge_into(lines, ln)
        else:
            target = counter.find_line(lines, index, d.get("product_id"), str(d.get("name") or ""))
            if target is None:
                ln = counter.line_from_spec(db, index, d) if d.get("qty", 0) > 0 else None
                if ln is None:
                    unknown.append(str(d.get("name") or d.get("product_id")))
                else:
                    lines.append(ln)
            elif (d.get("qty") or 0) <= 0:
                lines.remove(target)
            else:
                counter.set_line_qty(target, float(d["qty"]), d.get("unit"))
    if unknown and len(unknown) == len(body.items):
        raise HTTPException(404, f"Item nahi mila: {', '.join(unknown)}")
    counter.reprice(db, lines)
    counter.write_lines(cart, lines)
    return _done(db, cart)


@router.put("/{cart_id}/lines/{product_id}", response_model=CartView)
def set_quantity(cart_id: str, product_id: int, body: QtyBody, db: Session = Depends(get_db)):
    cart = _edit_cart(db, cart_id)
    if cart.status != "open":
        raise HTTPException(409, "Bill ban chuka hai")
    lines = counter.read_lines(cart)
    target = counter.find_line(lines, None, product_id)
    if target is None:
        raise HTTPException(404, "Cart mein yeh item nahi hai")
    if body.qty <= 0:
        lines.remove(target)
    else:
        counter.set_line_qty(target, body.qty, body.unit)
    counter.reprice(db, lines)
    counter.write_lines(cart, lines)
    return _done(db, cart)


@router.delete("/{cart_id}/lines/{product_id}", response_model=CartView)
def remove_line(cart_id: str, product_id: int, db: Session = Depends(get_db)):
    cart = _edit_cart(db, cart_id)
    if cart.status != "open":
        raise HTTPException(409, "Bill ban chuka hai")
    lines = counter.read_lines(cart)
    target = counter.find_line(lines, None, product_id)
    if target is None:
        raise HTTPException(404, "Cart mein yeh item nahi hai")
    lines.remove(target)
    counter.write_lines(cart, lines)
    return _done(db, cart)


@router.post("/{cart_id}/customer")
def attach_customer(cart_id: str, body: CustomerBody, db: Session = Depends(get_db)):
    """Attach a customer (recognised by UPI id, phone or name). Returns the cart, the customer and
    the usual basket offer ('Sharma ji ka usual?') for one-tap add via POST /{id}/usual."""
    customer = counter.lookup_customer(db, body.customer_id, body.upi_id, body.phone, body.name)
    if customer is None:
        raise HTTPException(404, "Customer nahi mila")
    cart = _edit_cart(db, cart_id)
    cart.customer_id = customer.id
    view = _done(db, cart)
    return {"cart": view, "customer": counter.customer_brief(customer),
            "usual": counter.usual_view(db, customer) if customer.usual_basket else None}


@router.post("/{cart_id}/usual", response_model=CartView)
def add_usual(cart_id: str, body: Optional[CustomerBody] = None, db: Session = Depends(get_db)):
    cart = _edit_cart(db, cart_id)
    if cart.status != "open":
        raise HTTPException(409, "Bill ban chuka hai")
    cid = (body.customer_id if body else None) or cart.customer_id
    customer = db.get(counter.Customer, cid) if cid else None
    if customer is None:
        raise HTTPException(404, "Pehle customer chuniye")
    lines = counter.read_lines(cart)
    added = counter.usual_lines(db, customer)
    if not added:
        raise HTTPException(404, f"{customer.name} ka usual basket nahi hai")
    for ln in added:
        counter.merge_into(lines, ln)
    cart.customer_id = customer.id
    counter.reprice(db, lines)
    counter.write_lines(cart, lines)
    return _done(db, cart)


@router.post("/{cart_id}/checkout")
async def checkout(cart_id: str, body: Optional[CheckoutBody] = None, db: Session = Depends(get_db)):
    """Create the bill. Default: one UPI payment for the full amount.

    Response (also published as the `checkout` event on channel `store`):
    {order_id, invoice_id, invoice_number, status, doc_type, total, amount_due, complete, upi_string,
    qr_payload, rail, items[], payments[], customer, receipt_url, spoken_text, audio_url, khata_warning}
    Cash-only or khata-only bills complete immediately (complete=true, invoice paid, stock deducted)."""
    body = body or CheckoutBody()
    cart = counter.get_cart(db, cart_id)
    return await payments.checkout_cart(db, cart, splits=body.splits, customer_id=body.customer_id,
                                        rail=body.rail, note=body.note, speak=body.speak)


# --- same data under /api/customers (needs a main.py mount, see module docstring) ---


@customers_router.get("/lookup")
def customer_lookup(upi_id: Optional[str] = None, phone: Optional[str] = None,
                    name: Optional[str] = None, db: Session = Depends(get_db)):
    customer = counter.lookup_customer(db, upi_id=upi_id, phone=phone, name=name)
    if customer is None:
        raise HTTPException(404, "Customer nahi mila")
    return {"customer": counter.customer_brief(customer),
            "usual": counter.usual_view(db, customer) if customer.usual_basket else None}


@customers_router.get("/{customer_id}/usual")
def customer_usual(customer_id: int, db: Session = Depends(get_db)):
    customer = db.get(counter.Customer, customer_id)
    if customer is None:
        raise HTTPException(404, f"Customer {customer_id} nahi mila")
    return counter.usual_view(db, customer)
