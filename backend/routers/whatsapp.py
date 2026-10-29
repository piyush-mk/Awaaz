"""WhatsApp (Phase 1, Agent B). Real Meta Cloud API with an in-app simulator fallback.

GET  /webhooks/whatsapp      Meta verification handshake (implemented here)
POST /webhooks/whatsapp      inbound messages: verify X-Hub-Signature-256 with WA_APP_SECRET,
                             download media, STT/vision, draft order (Agent B)
GET  /api/wa/outbox          messages shown in the /wa simulator
POST /api/wa/simulate-inbound   inject an inbound message from the simulator
"""
from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse

from config import settings
from routers._stub import not_implemented

webhook_router = APIRouter()
router = APIRouter()


@webhook_router.get("")
def verify(hub_mode: str = Query("", alias="hub.mode"),
           hub_verify_token: str = Query("", alias="hub.verify_token"),
           hub_challenge: str = Query("", alias="hub.challenge")):
    """Meta calls this once when the webhook URL is registered."""
    if hub_mode == "subscribe" and hub_verify_token == settings.wa_verify_token:
        return PlainTextResponse(hub_challenge)
    return PlainTextResponse("verification failed", status_code=403)


@webhook_router.post("")
async def inbound():
    not_implemented("POST /webhooks/whatsapp", "Agent B")


@router.get("/outbox")
def outbox():
    not_implemented("GET /api/wa/outbox", "Agent B")


@router.post("/simulate-inbound")
async def simulate_inbound():
    not_implemented("POST /api/wa/simulate-inbound", "Agent B")
