"""Payments (Phase 1, Agent A).

GET  /api/payments/{order_id}            status
POST /api/payments/{order_id}/simulate   mark success, deduct stock FIFO, SSE, WhatsApp receipt
"""
from fastapi import APIRouter

from routers._stub import not_implemented

router = APIRouter()


@router.get("/{order_id}")
def get_payment(order_id: str):
    not_implemented("GET /api/payments/{order_id}", "Agent A")


@router.post("/{order_id}/simulate")
def simulate_payment(order_id: str):
    not_implemented("POST /api/payments/{order_id}/simulate", "Agent A")
