"""Galla closing (Phase 1, Agent C).

GET  /api/galla/expected     services.cash.expected_cash (implemented helper)
POST /api/galla/scan         photo -> services.vision (task='cash') -> editable denominations
POST /api/galla/close        persist CashClosing, return the difference and tomorrow's PO
"""
from fastapi import APIRouter

from routers._stub import not_implemented

router = APIRouter()


@router.get("/expected")
def expected():
    not_implemented("GET /api/galla/expected", "Agent C")


@router.post("/scan")
async def scan_cash():
    not_implemented("POST /api/galla/scan", "Agent C")


@router.post("/close")
def close_day():
    not_implemented("POST /api/galla/close", "Agent C")
