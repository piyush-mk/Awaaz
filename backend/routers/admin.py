"""Admin: provider health, status page data, pre-demo checklist and demo reset (Agent D).

GET  /api/admin/health          provider states; add ?live=1 to ping providers that have keys
GET  /api/admin/status          human-readable summary for the /status page
GET  /api/admin/demo-checklist  pre-demo pass/fail from database facts
POST /api/admin/reset-demo      drop and reseed the Ramesh General Store scenario
"""
import os
import subprocess
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import seed as seed_module
from config import REPO_DIR, settings
from database import get_db
from models import Customer, Invoice, Product
from services import brief as brief_svc
from services import cash, events, health, insights, quantity, stock_ops
from services.clock import day_bounds, now_local, today_local

router = APIRouter()


def _provider(configured: bool) -> dict:
    if settings.fixtures_only:
        mode = "fixture"
    else:
        mode = "live" if configured else ("fixture" if settings.fixtures_allowed else "missing")
    return {"configured": configured, "mode": mode}


def _counts(db: Session) -> dict:
    start, end = day_bounds(today_local())
    return {"products": db.query(Product).count(), "customers": db.query(Customer).count(),
            "invoices": db.query(Invoice).count(),
            "invoices_today": db.query(Invoice).filter(Invoice.status != "cancelled",
                                                        Invoice.created_at >= start,
                                                        Invoice.created_at < end).count()}


@router.get("/health")
async def get_health(live: bool = False, db: Session = Depends(get_db)):
    """Provider health. `services.<name>.state` is live | fallback | fixture | missing_key.
    Real (tiny) pings run only with `?live=1`, only for providers that have keys, never in
    DEMO_MODE=on. Key values are never returned."""
    pinged: list[str] = []
    if live:
        pinged = await health.run_live_checks(db)
    else:
        health.ping_db(db)
    services = health.snapshot()
    summary: dict[str, int] = {}
    for s in services.values():
        summary[s["state"]] = summary.get(s["state"], 0) + 1
    degraded = services["db"]["state"] != "live" or any(
        s["state"] == "fallback" for s in services.values())
    return {
        "status": "degraded" if degraded else "ok", "time": now_local().isoformat(timespec="seconds"),
        "demo_mode": settings.demo_mode, "live_checked": live, "pinged": pinged,
        "db": _counts(db), "services": services, "summary": summary,
        "providers": {
            "sarvam": _provider(settings.has_sarvam), "paytm_llm": _provider(settings.has_paytm),
            "xai_vision": _provider(settings.has_xai),
            "whatsapp": {"configured": settings.has_whatsapp,
                         "mode": "live" if settings.has_whatsapp else "simulator"},
        },
        "live_checks": {n: health.state_of(n) for n in pinged} if live else None,
    }


def _commit_hash() -> str | None:
    for var in ("GIT_COMMIT", "BUILD_COMMIT", "COMMIT_SHA"):
        if os.getenv(var):
            return os.getenv(var)[:12]
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(REPO_DIR), capture_output=True,
                             text=True, timeout=2)
        return out.stdout.strip() or None if out.returncode == 0 else None
    except Exception:
        return None


@router.get("/status")
def get_status(db: Session = Depends(get_db)):
    """Everything the /status page shows: config booleans, effective mode, counts, IST time, build."""
    now = now_local()
    if settings.fixtures_only:
        effective, note = "fixtures", "DEMO_MODE=on: koi bahari AI call nahi, sab fixtures se"
    elif settings.demo_mode == "off":
        effective, note = "live_only", "DEMO_MODE=off: fixtures band, provider error seedha dikhega"
    elif settings.has_sarvam:
        effective, note = "live_with_fallback", "Sarvam live; fail hone par rules/fixtures"
    else:
        effective, note = "fixtures_no_key", "SARVAM_API_KEY nahi hai: fixtures/rules se chal raha hai"
    services = health.snapshot()
    return {
        "app": "Awaaz: the AI Munim", "version": "2.0.0", "store": settings.merchant_name,
        "time_ist": now.strftime("%Y-%m-%d %H:%M:%S") + " IST", "time_iso": now.isoformat(timespec="seconds"),
        "build": {"commit": _commit_hash(), "python_env": "venv" if os.getenv("VIRTUAL_ENV") else "system"},
        "demo_mode": {"setting": settings.demo_mode, "effective": effective, "note": note},
        "config": {
            "sarvam_key": settings.has_sarvam, "paytm_key": settings.has_paytm, "xai_key": settings.has_xai,
            "whatsapp_configured": settings.has_whatsapp,
            "whatsapp_verify_token_default": settings.wa_verify_token == "awaaz-verify",
            "wa_app_secret": bool(settings.wa_app_secret), "upi_vpa": settings.merchant_upi_vpa,
            "public_base_url": settings.public_base_url,
            "models": {"stt": settings.sarvam_stt_model, "llm": settings.sarvam_llm_model,
                       "tts": settings.sarvam_tts_model, "speaker": settings.sarvam_tts_speaker,
                       "vision": settings.sarvam_vision_model},
        },
        "counts": _counts(db),
        "services": {n: {"state": s["state"], "effective": s["effective"]} for n, s in services.items()},
        "next_steps": [m for ok, m in [
            (settings.has_sarvam or settings.fixtures_only, "SARVAM_API_KEY daalein (backend/.env)"),
            (settings.has_whatsapp, "WA_TOKEN aur WA_PHONE_NUMBER_ID daalein (warna WhatsApp simulator chalega)"),
            (settings.public_base_url.startswith("https"), "PUBLIC_BASE_URL https par set karein (mic/camera/webhook ke liye)"),
        ] if not ok],
    }


def _check(cid: str, label: str, expected: Any, actual: Any, ok: bool, level: str = "required") -> dict:
    return {"id": cid, "label": label, "expected": expected, "actual": actual, "ok": bool(ok), "level": level}


@router.get("/demo-checklist")
def demo_checklist(db: Session = Depends(get_db)):
    """Pre-demo checklist: the seeded numbers the pitch relies on, plus advisory key checks."""
    today = today_local()
    items: list[dict] = []

    lines = quantity.parse_order("do maggi ek surf excel chaar colgate", db)
    cart = round(sum(ln.line_total for ln in lines), 2)
    items.append(_check("cart_249", "2 Maggi + 1 Surf Excel + 4 Colgate = Rs 249", 249.0, cart, cart == 249.0))

    galla = cash.expected_cash(db)
    items.append(_check("galla_6850", "Galla expected cash", 6850.0, galla, galla == 6850.0))

    y = insights.sales_on(db, today - timedelta(days=1))
    items.append(_check("yesterday_8420", "Kal ki sale", 8420.0, y, y == 8420.0))
    w = insights.sales_on(db, today - timedelta(days=8))
    pct = insights.pct_change(y, w)
    items.append(_check("week_delta_12", "Pichle hafte se +12%", 12.0, pct, pct is not None and abs(pct - 12.0) < 0.6))

    ghee = db.query(Product).filter(Product.name.ilike("%ghee%")).first()
    cover = stock_ops.days_of_cover(db, ghee.id) if ghee else None
    items.append(_check("ghee_cover_2d", "Ghee ~2 din ka cover", "1.8 - 2.2", cover,
                        cover is not None and 1.8 <= cover <= 2.2))

    kurkure = db.query(Product).filter(Product.name.ilike("%kurkure%")).count()
    items.append(_check("kurkure_absent", "Kurkure catalog mein nahi (missed-sale demo)", 0, kurkure, kurkure == 0))
    asks = [m for m in insights.missed_sales(db, 7) if m["product_name"].lower() == "kurkure"]
    items.append(_check("kurkure_asked_6", "Kurkure is hafte 6 baar maanga gaya", 6,
                        asks[0]["count"] if asks else 0, bool(asks) and asks[0]["count"] == 6))

    verma = db.query(Customer).filter(Customer.name == "Verma ji").first()
    bal = round(float(verma.balance), 2) if verma else None
    items.append(_check("verma_850", "Verma ji ka udhaar", 850.0, bal, bal == 850.0))

    surf = db.query(Product).filter(Product.name == "Surf Excel").first()
    rate = (insights.last_purchase_map(db).get(surf.id) or {}).get("rate") if surf else None
    items.append(_check("surf_rate_42", "Surf Excel ka last distributor rate", 42.0, rate, rate == 42.0))

    colgate = db.query(Product).filter(Product.name == "Colgate").first()
    cq = stock_ops.current_stock(db, colgate.id) if colgate else None
    items.append(_check("colgate_12", "Colgate stock 12 (bill ke baad '8 left')", 12.0, cq, cq == 12.0))

    from services import festivals
    fest = festivals.next_festival(today)
    items.append(_check("festival_upcoming", "Agla tyohaar calendar mein hai", "Dhanteras/Diwali",
                        f"{fest['name']} ({fest['days_away']} din)" if fest else None,
                        fest is not None and fest["days_away"] <= 14, "advisory"))
    items.append(_check("sarvam_key", "SARVAM_API_KEY set", True, settings.has_sarvam, settings.has_sarvam, "advisory"))
    items.append(_check("whatsapp_keys", "WhatsApp Cloud API keys set (warna simulator)", True,
                        settings.has_whatsapp, settings.has_whatsapp, "advisory"))
    items.append(_check("demo_mode_auto", "DEMO_MODE=auto (live + safe fallback)", "auto", settings.demo_mode,
                        settings.demo_mode == "auto", "advisory"))

    required = [i for i in items if i["level"] == "required"]
    return {"ready": all(i["ok"] for i in required), "passed": sum(1 for i in items if i["ok"]),
            "total": len(items), "failed": [i["id"] for i in required if not i["ok"]],
            "warnings": [i["id"] for i in items if i["level"] == "advisory" and not i["ok"]],
            "items": items, "time": now_local().isoformat(timespec="seconds")}


@router.post("/reset-demo")
def reset_demo():
    """Drop and reseed the Ramesh General Store scenario (use between rehearsals)."""
    brief_svc.clear_cache()
    health.reset()
    result = seed_module.seed(reset=True, verbose=False)
    events.publish("store", "demo_reset", {"at": now_local().isoformat(timespec="seconds")})
    return result
