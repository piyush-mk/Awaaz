"""Stock tools (Phase 1, Agent D).

GET  /api/stock/cover          days of cover per product
POST /api/stock/prices         daily fresh-item prices ("ande saat rupaye")
POST /api/stock/missed         record a MissedSale; GET /api/stock/missed for the weekly summary
"""
from fastapi import APIRouter

from routers._stub import not_implemented

router = APIRouter()


@router.get("/cover")
def cover():
    not_implemented("GET /api/stock/cover", "Agent D")


@router.post("/prices")
def set_prices():
    not_implemented("POST /api/stock/prices", "Agent D")


@router.post("/missed")
def add_missed():
    not_implemented("POST /api/stock/missed", "Agent D")


@router.get("/missed")
def list_missed():
    not_implemented("GET /api/stock/missed", "Agent D")
