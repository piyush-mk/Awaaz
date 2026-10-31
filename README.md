# Awaaz: voice and camera AI for every Paytm merchant

> Bolo. Dikhao. Ho gaya. (Speak. Show. Done.)

Paytm Build for India AI Hackathon, Delhi. Track 1: Merchant Growth AI. Team PinkFloyd.

India's kirana stores run on three things no app has digitised well: speech, paper and trust. Orders are spoken across the counter, stock arrives on distributor bills, and credit lives in a notebook. Awaaz keeps the khata, runs the counter and advises the owner, built to work on the Paytm Soundbox and the Paytm for Business app. The merchant speaks or points a phone camera, and the shop's whole day is recorded without typing.

Paytm already knows how much every kirana earns. Awaaz records what they sell, what they are owed and what to do next.

> Deploying or fixing a deployment? Read [docs/MERGE-DECISIONS.md](docs/MERGE-DECISIONS.md) first.

## Live demo

Deployed at **https://65-20-73-34.sslip.io** (HTTPS, so the microphone and camera work on phones).

| Page | Link |
|---|---|
| Merchant phone app | https://65-20-73-34.sslip.io/app |
| Soundbox emulator | https://65-20-73-34.sslip.io/soundbox |
| WhatsApp simulator | https://65-20-73-34.sslip.io/wa |
| Status and demo checklist | https://65-20-73-34.sslip.io/status |
| API docs | https://65-20-73-34.sslip.io/docs |

**Tested** (31 Oct 2026, the `feat/awaaz-v2` build hosted in Mumbai with live Sarvam and OpenRouter keys, before the merge in `docs/MERGE-DECISIONS.md`):
- All backend tests pass, with no keys and no network.
- The end-to-end smoke script (`scripts/smoke.py --live`) plays the whole demo story over HTTP and passes 35 of 35 checks against the deployed instance, with real vision on a distributor bill (8 of 8 lines, total to the paisa) and a handwritten Hindi list (7 of 7 items).
- The Soundbox, WhatsApp simulator and phone app were exercised in a headless browser, and live events stream through the HTTPS proxy.
- Not yet verified: real WhatsApp delivery (simulator only for now), the microphone and camera on a real phone, and how the spoken replies sound.

**Speed** (measured from a laptop in India, live Sarvam):

| | Before | Now |
|---|---|---|
| Voice order to cart | 3.0 s | **0.5 s** |
| Typed order to cart | 1.3 to 1.7 s (LLM) | **under 0.1 s server time** (LLM skipped for plain orders) |
| Spoken reply | blocked the response (+2 to 4 s) | generated separately, short lines, cached phrases play instantly |

Most of the gain came from running the API in Mumbai instead of the US (speech recognition 1.1 s to 0.25 s, LLM 0.7 s to 0.14 s, every request 330 ms closer), and the rest from the LLM-free fast path and non-blocking speech. Host the API in the same region as your users and the AI provider.

If a page shows stale numbers, press **Reset demo data** on `/status` (the demo shop's data is relative to today).

## What it does

| Room | Features |
|---|---|
| **Counter** (काउंटर) | Voice billing in Indian languages mixed with English. "Bees rupaye ki cheeni" becomes a 450 g line ("450 gram tolo"). Exact-amount UPI QR, spoken confirmation, GST worked out of the MRP (Bill of Supply for composition stores), split payments, undo by voice, parchi (handwritten list) photo to cart, "usual basket" for regulars, WhatsApp text and voice receipts |
| **Godown** (गोदाम) | Distributor bill photo to stock with a price guard (Surf Rs3 costlier) and a scheme guard (free packet not counted), expiry alerts and return-claim amounts, shelf photo audit, voice stock-in, missed-sale tracking |
| **Khata** (खाता) | Udhaar by voice with an instant WhatsApp confirmation to the customer, credit limits from payment history, khata notebook photo import, salary-day reminders, simulated Paytm Postpaid offer at the counter, customer passbook page |
| **Hisaab** (हिसाब) | Today's sales, payment split, hourly and 14-day charts, margin, invoices with public receipt pages, galla (cash) photo count checked against the day's bills |
| **Salaah** (सलाह, from the header) | Spoken morning brief, festival-aware reorder drafts sent to suppliers on WhatsApp, "ask about the shop" by voice, WhatsApp voice-note and photo orders from customers, and a chat assistant that answers customers like the shopkeeper would (what is in stock, MRP prices, their own khata balance, order status, small talk) and passes anything it is unsure about to the owner |

Any result that came from demo data carries a small `demo` chip, and `/status` shows which providers are live. Money and stock never change without the merchant's confirmation ("haan" or a tap).

## Pages

| URL | What |
|---|---|
| `/app` | Merchant phone app (mobile first): the five rooms above |
| `/soundbox` | Emulator of the Paytm AI Soundbox, driven live by events: listening, bill, QR, paid |
| `/wa` | WhatsApp simulator that can also play the customer (text, voice note, photo) |
| `/status` | Provider health, demo checklist, reset button |
| `/test` | Engineering console with canned requests for every endpoint |
| `/docs` | Interactive API docs (FastAPI) |

## Quick start (no API keys needed)

Requirements: Python 3.12, Node 20.

```bash
# Backend
cd backend
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env              # every key is optional
.venv/bin/uvicorn main:app --reload --port 8000

# Frontend (second terminal)
cd frontend
npm install
npm run dev                       # http://localhost:5173
```

On first start the database seeds itself with a demo shop, "Ramesh General Store" in Laxmi Nagar: about 40 products, 45 days of sales, suppliers, and customers with udhaar balances. Open http://localhost:5173/app.

Without keys the app runs on fixtures and rules: speech cannot be transcribed, so use the **Type** box on the Counter tab (or the sample phrases on `/soundbox`), and photo scans return built-in sample results. Everything else, including payments, stock, khata, receipts, the brief and reorders, works for real against the local database.

### Try the demo story

1. `/status`: press **Reset demo data**.
2. `/soundbox` in one window, `/app` in another.
3. Counter, type `do maggi ek surf excel chaar colgate`: the cart totals Rs249. Add `bees rupaye ki cheeni` for "450 gram tolo".
4. **Bill banao**, then **Payment aa gaya**: the Soundbox shows the QR, then "received".
5. Khata, give Verma ji Rs500 udhaar: his WhatsApp confirmation appears in `/wa`.
6. Godown, bill scan: price and scheme flags appear. Hisaab, galla: Rs150 short.

The full script with props is in [docs/DEMO.md](docs/DEMO.md).

### Tests

```bash
cd backend && .venv/bin/pytest -q          # no keys, no network
python scripts/smoke.py --base http://localhost:8000   # plays the whole demo story over HTTP
```

## Going live: API keys

Put keys in `backend/.env` (never commit it). All are optional; `DEMO_MODE=auto` falls back to fixtures per call so the demo always completes.

| Variable | Purpose |
|---|---|
| `SARVAM_API_KEY` | Speech to text (Saaras), LLM with tool calling (Sarvam-105B), text to speech (Bulbul), vision |
| `OPENROUTER_API_KEY` | Backup AI when Sarvam fails: chat with tool calling (`OPENROUTER_MODEL`, default `anthropic/claude-haiku-5.5`) and vision (`OPENROUTER_VISION_MODEL`, default `google/gemini-3.1-flash-lite`). Credit is limited, so it is only used after Sarvam fails |
| `WA_TOKEN`, `WA_PHONE_NUMBER_ID`, `WA_APP_SECRET`, `WA_VERIFY_TOKEN` | WhatsApp Cloud API. Without them the in-app simulator is used |
| `MERCHANT_UPI_VPA`, `MERCHANT_NAME` | Receiver of the demo QR. **Real money if scanned** |
| `PUBLIC_BASE_URL` | Public https URL of the backend (receipt links, webhooks, CORS) |
| `DEMO_MODE` | `auto` (default), `on` (never call external APIs), `off` (surface provider errors) |
| `DATABASE_URL` | Defaults to a SQLite file in `backend/` |

Check `/status` (or `GET /api/admin/health?live=1`) to see which providers are live, falling back, or missing a key.

## How it is built

```
 phone /app    Soundbox /soundbox    WhatsApp sim /wa
      |               |  SSE events        |
      v               v                    v
  FastAPI  routers: agent, cart, payments, invoices, khata, purchases,
           galla, brief, stock, whatsapp, admin, events
  services: sarvam, openrouter, llm, vision, quantity, catalog, pricing, invoicing,
            stock_ops, receipts, whatsapp, khata, insights, reorder, ...
  SQLite (SQLAlchemy)
```

- One pattern everywhere: capture (voice, photo, WhatsApp), understand (Sarvam), propose (a pending action), the merchant confirms, then commit and notify.
- Every AI call goes through a provider chain with fallback: Sarvam first (it is the primary provider for speech, chat, tool calling and vision), then OpenRouter as the backup, then deterministic rules (chat) or a demo fixture. Vision runs Sarvam, then OpenRouter, then a fixture.
- The rules parser answers in milliseconds and the cart updates immediately; the LLM result reconciles shortly after.
- Run the API as a **single worker**: live events use an in-process bus.

Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Deployment and day-of checklist: [RUNBOOK.md](RUNBOOK.md). Product vision: [PRODUCT.md](PRODUCT.md).

## Repository layout

```
backend/            FastAPI app (routers/, services/, models.py, seed.py, tests/)
frontend/           React + Vite + Tailwind (src/pages/app, Soundbox, WhatsAppSim, StatusPage)
scripts/            smoke.py (end-to-end), deploy.sh (generic redeploy)
docs/               ARCHITECTURE.md, DEMO.md
PRODUCT.md          The product vision and ecosystem
RUNBOOK.md          Keys, rehearsal checklist, deployment, troubleshooting
```

## Status and limits

- Built for a hackathon prototype. Payments use a real UPI intent QR plus a "payment received" simulation; a Paytm Dynamic QR adapter point exists but is not enabled. Postpaid and the Soundbox are emulated and labelled as such.
- Live Sarvam, Meta WhatsApp and camera/microphone paths are written against the vendors' documentation. Run `/status` Live check and `scripts/smoke.py --live` after adding keys.
- There is no login. Do not expose a keyed instance publicly without adding authentication.
- GST rates in the seed follow the post 22 Sept 2025 structure; verify against the CBIC notification before real use.

## Team

- Aadarsh Agarwal
- Piyush Mohapatra
