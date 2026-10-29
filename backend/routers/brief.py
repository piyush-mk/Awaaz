"""Morning brief, reorder and Ask-your-munim (Phase 1, Agent D). Mounted at /api.

GET  /api/brief/today              text + audio url (services.tts_cache)
POST /api/reorder/draft            purchase order per supplier (cover x festival multiplier)
POST /api/reorder/{id}/send        WhatsApp the PO to the supplier
POST /api/ask                      read-only Q&A (sales_summary, top_items, stock_of, who_owes)
Helpers ready: services.stock_ops (velocity, days_of_cover), services.festivals.
"""
from fastapi import APIRouter

from routers._stub import not_implemented

router = APIRouter()


@router.get("/brief/today")
async def brief_today():
    not_implemented("GET /api/brief/today", "Agent D")


@router.post("/reorder/draft")
def reorder_draft():
    not_implemented("POST /api/reorder/draft", "Agent D")


@router.post("/reorder/{order_id}/send")
def reorder_send(order_id: int):
    not_implemented("POST /api/reorder/{id}/send", "Agent D")


@router.post("/ask")
async def ask():
    not_implemented("POST /api/ask", "Agent D")
