"""Admin: health skeleton and demo reset (Agent D extends health with live provider pings)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import seed as seed_module
from config import settings
from database import get_db
from models import Customer, Invoice, Product
from services.clock import now_local

router = APIRouter()


def _provider(configured: bool) -> dict:
    if settings.fixtures_only:
        mode = "fixture"
    else:
        mode = "live" if configured else ("fixture" if settings.fixtures_allowed else "missing")
    return {"configured": configured, "mode": mode}


@router.get("/health")
def health(db: Session = Depends(get_db)):
    """Config and DB snapshot. Does NOT call providers yet (Agent D adds live pings)."""
    return {
        "status": "ok", "time": now_local().isoformat(timespec="seconds"),
        "demo_mode": settings.demo_mode,
        "db": {"products": db.query(Product).count(), "customers": db.query(Customer).count(),
               "invoices": db.query(Invoice).count()},
        "providers": {
            "sarvam": _provider(settings.has_sarvam), "paytm_llm": _provider(settings.has_paytm),
            "xai_vision": _provider(settings.has_xai),
            "whatsapp": {"configured": settings.has_whatsapp,
                         "mode": "live" if settings.has_whatsapp else "simulator"},
        },
        "live_checks": None,
    }


@router.post("/reset-demo")
def reset_demo():
    """Drop and reseed the Ramesh General Store scenario (use between rehearsals)."""
    return seed_module.seed(reset=True, verbose=False)
