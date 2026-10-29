"""Awaaz v2 FastAPI app. Run as a SINGLE uvicorn worker (in-process SSE bus):

    uvicorn main:app --port 8000
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import seed as seed_module
from config import settings
from database import SessionLocal, init_db
from models import Product
from routers import (admin, agent, billing, brief, cart, dashboard, events, galla, inventory,
                     invoices, khata, payments, photo, purchases, stock, voice, whatsapp)

init_db()


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Fresh database: load the Ramesh General Store demo data."""
    db = SessionLocal()
    try:
        empty = db.query(Product).count() == 0
    finally:
        db.close()
    if empty:
        seed_module.seed(verbose=False)
    yield


app = FastAPI(title="Awaaz: the AI Munim", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- legacy (shapes frozen) ---
app.include_router(voice.router, prefix="/api/voice", tags=["Voice AI"])
app.include_router(inventory.router, prefix="/api/inventory", tags=["Inventory"])
app.include_router(billing.router, prefix="/api/bill", tags=["Billing"])
app.include_router(dashboard.router, prefix="/api", tags=["Dashboard"])
app.include_router(photo.router, prefix="/api/photo", tags=["Photo Inventory"])

# --- v2 (stubs until Phase 1) ---
app.include_router(agent.router, prefix="/api/agent", tags=["Agent"])
app.include_router(agent.actions_router, prefix="/api/actions", tags=["Agent"])
app.include_router(cart.router, prefix="/api/cart", tags=["Cart"])
app.include_router(payments.router, prefix="/api/payments", tags=["Payments"])
app.include_router(invoices.router, prefix="/api/invoices", tags=["Invoices"])
app.include_router(invoices.public_router, prefix="/r", tags=["Receipts"])
app.include_router(khata.router, prefix="/api/khata", tags=["Khata"])
app.include_router(whatsapp.webhook_router, prefix="/webhooks/whatsapp", tags=["WhatsApp"])
app.include_router(whatsapp.router, prefix="/api/wa", tags=["WhatsApp"])
app.include_router(purchases.router, prefix="/api/purchases", tags=["Purchases"])
app.include_router(galla.router, prefix="/api/galla", tags=["Galla"])
app.include_router(brief.router, prefix="/api", tags=["Brief"])
app.include_router(stock.router, prefix="/api/stock", tags=["Stock"])
app.include_router(events.router, prefix="/api", tags=["Events"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])


@app.get("/")
def root():
    return {"status": "ok", "app": "Awaaz: the AI Munim", "version": "2.0.0"}


@app.get("/health")
def health():
    return {"status": "healthy"}
