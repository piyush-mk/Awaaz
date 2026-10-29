# Awaaz: the AI munim (CLAUDE.md)

## What this is
Awaaz is a voice and camera AI manager for kirana stores, built for the Paytm Build for India AI Hackathon (Delhi, 31 Oct 2026, Track 1: Merchant Growth AI). The merchant speaks or points a phone camera; the shop's billing, stock, udhaar and accounts are recorded without typing. Sarvam AI is the official AI partner, so Sarvam models are preferred everywhere. Product vision: PRODUCT.md. Architecture: docs/ARCHITECTURE.md. Deploy and keys: RUNBOOK.md. Demo script: docs/DEMO.md.

## Running it

```bash
# Backend (Python 3.12)
cd backend
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env                 # every key is optional
.venv/bin/uvicorn main:app --reload --port 8000   # seeds the demo shop on first start

# Frontend
cd frontend && npm install && npm run dev          # http://localhost:5173 (proxies /api, /r, /k, /webhooks)

# Tests
cd backend && .venv/bin/pytest -q                  # 359 tests, no keys, no network
python scripts/smoke.py --base http://localhost:8000   # whole demo story over HTTP (resets demo data)
```

## Layout
- `backend/routers/`: HTTP endpoints (agent, cart, payments, invoices, khata, purchases, galla, brief, stock, whatsapp, admin, events, plus legacy voice/photo/inventory/billing/dashboard).
- `backend/services/`: logic and provider wrappers (sarvam, llm, vision, quantity, catalog, pricing, invoicing, stock_ops, receipts, whatsapp, khata, insights, reorder, fixtures).
- `backend/models.py`, `seed.py`: data model and the demo shop "Ramesh General Store" (seed is relative to today: run reset-demo before rehearsals).
- `frontend/src/pages/app/`: merchant phone app (Counter, Godown, Khata, Hisaab, Salaah). `pages/Soundbox.jsx`, `WhatsAppSim.jsx`, `StatusPage.jsx`, `TestConsole.jsx`. `api/client.js` is the single source of truth for API calls.

## Conventions
- Capture, understand, propose, confirm, commit, notify: money and stock only change after the merchant confirms (`PendingAction`).
- Every AI call returns `{data, source, latency_ms}` and falls back: Sarvam, secondary provider, rules, fixture. `DEMO_MODE=auto` must keep the demo working with no keys.
- Prices are MRP inclusive; GST is worked out of the MRP (`services/pricing.py`). Rates are data, not code.
- Run the API as a single worker (in-process event bus).
- Never commit `.env`, databases or keys. The repo is public.
- No API contract changes without telling the other person: endpoint shapes are covered by tests.

## UI
- Palette: ink navy `#0E1B33` / `#1B2330`, Paytm cyan `#00B9F5`, accent orange `#FF8A1F`, background `#ECF0F4`. IBM Plex Sans plus Noto Sans Devanagari.
- Mobile first (375px), touch targets at least 44px, Hindi headings large, no emoji (lucide-react icons).
- Rooms (bottom nav): Counter, Godown, Khata, Hisaab, Salaah.

## Writing style for docs and copy
Plain language, no em-dashes, no claims about literacy, and say "Indian languages mixed with English" rather than naming a single dialect.
