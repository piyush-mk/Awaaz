"""Distributor bill scan (Phase 1, Agent C).

POST /api/purchases/scan     photo -> services.vision (task='purchase_bill') -> catalog match ->
                             price guard + scheme check -> PendingAction(kind='purchase_bill')
GET  /api/purchases, /api/purchases/{id}
Confirming the PendingAction (routers/agent.py actions) writes StockBatch, cost and expiry.
"""
from fastapi import APIRouter

from routers._stub import not_implemented

router = APIRouter()


@router.post("/scan")
async def scan_bill():
    not_implemented("POST /api/purchases/scan", "Agent C")


@router.get("")
def list_purchases():
    not_implemented("GET /api/purchases", "Agent C")


@router.get("/{bill_id}")
def get_purchase(bill_id: int):
    not_implemented("GET /api/purchases/{id}", "Agent C")
