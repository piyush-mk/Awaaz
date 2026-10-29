"""Counter cart (Phase 1, Agent A). Backed by models.Cart; lines are schemas.CartLine dicts.

POST /api/cart                    create/open a cart for a session
GET  /api/cart/{id}               current cart (schemas.Cart)
POST /api/cart/{id}/lines         add/replace/remove lines
POST /api/cart/{id}/checkout      Invoice + Payment(pending) + UPI intent; publishes SSE
"""
from fastapi import APIRouter

from routers._stub import not_implemented

router = APIRouter()


@router.post("")
def create_cart():
    not_implemented("POST /api/cart", "Agent A")


@router.get("/{cart_id}")
def get_cart(cart_id: str):
    not_implemented("GET /api/cart/{id}", "Agent A")


@router.post("/{cart_id}/lines")
def edit_lines(cart_id: str):
    not_implemented("POST /api/cart/{id}/lines", "Agent A")


@router.post("/{cart_id}/checkout")
def checkout(cart_id: str):
    not_implemented("POST /api/cart/{id}/checkout", "Agent A")
