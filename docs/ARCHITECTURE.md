# Architecture

## Overview

A single FastAPI process (one uvicorn worker) with a SQLite database, a React single page app, and Server-Sent Events for live updates.

```
 Merchant phone (/app)    Soundbox emulator (/soundbox)    WhatsApp simulator (/wa)
        | push-to-talk / hands-free / camera     | SSE            | SSE
        v                                        v                v
  +------------------------------- FastAPI -----------------------------------+
  | routers   agent  cart  payments  invoices  khata  purchases  galla  brief  |
  |           stock  whatsapp(webhook)  events(SSE)  admin  legacy voice/photo |
  | services  sarvam llm vision catalog quantity pricing invoicing stock_ops   |
  |           receipts whatsapp khata postpaid insights reorder munim health   |
  | SQLite via SQLAlchemy                                                      |
  +----------------------------------------------------------------------------+
        |                      |                       |
   Sarvam AI            Meta WhatsApp Cloud       UPI intent / (Paytm Dynamic QR adapter)
```

## The core pattern

Capture, understand, propose, confirm, commit, notify.

1. **Capture**: audio from the mic, a photo, or a WhatsApp message.
2. **Understand**: Sarvam speech to text (with the catalog as keyterms), an LLM with tool calling, or vision with a JSON schema.
3. **Propose**: cart edits apply at once; anything that moves money or stock is stored as a `PendingAction` with a plain-language summary.
4. **Confirm**: the merchant taps Haan or says "haan". "Galat hai" cancels or undoes.
5. **Commit** in one database transaction.
6. **Notify**: events on SSE channels (`store`, `wa`), spoken replies (Bulbul, with browser speech as fallback), and WhatsApp messages.

## Provider chain and demo mode

Each AI call returns a result envelope `{data, source, latency_ms}` where `source` is `sarvam`, `paytm`, `xai`, `rules` or `fixture`. The chain is Sarvam, then a secondary provider, then deterministic rules, then a fixture. `DEMO_MODE` controls fallback:

| Mode | Behaviour |
|---|---|
| `auto` | Fixtures only when a key is missing or a call fails (default; the demo always completes) |
| `on` | Never call external APIs |
| `off` | Never use fixtures; provider errors surface |

Voice utterances run two paths in parallel: the rules parser (milliseconds) updates the cart immediately, and the LLM tool-calling result (4 second budget) replaces it when it arrives.

## Data model (backend/models.py)

`StoreProfile`, `Product` (aliases, MRP, cost, GST rate, loose and pack-breaking fields), `StockBatch` (batch, expiry, cost), `StockMove` (the stock ledger), `Customer`, `Invoice` and `InvoiceItem`, `Payment`, `KhataEntry` (positive = credit given, negative = payment received), `Supplier`, `PurchaseBill` and `PurchaseItem`, `MissedSale`, `CashClosing`, `PendingAction`, `Message` (WhatsApp outbox and inbox), `Cart`.

Stock is the sum of batch quantities and is deducted first-in-first-out. Prices are MRP inclusive: GST is worked out of the MRP (`services/pricing.py`), split into CGST and SGST, or issued as a Bill of Supply for composition stores.

## API groups

| Prefix | What |
|---|---|
| `/api/agent` | `POST /utterance`: speech or text to cart edits and proposed actions |
| `/api/actions` | Confirm or cancel pending actions |
| `/api/cart` | Cart, lines, customer, usual basket, `POST /{id}/checkout` |
| `/api/payments` | Payment status, `POST /{order}/simulate`, payment webhook |
| `/api/invoices`, `/r/{token}` | Invoices and the public mobile receipt page |
| `/api/khata` | Customers, entries, reminders, Postpaid (simulated), notebook import |
| `/api/purchases`, `/api/suppliers` | Distributor bill scan, price and scheme guard, confirm |
| `/api/galla` | Cash count, expected cash, close |
| `/api/photo` | Shelf audit, parchi to cart, legacy shelf parse |
| `/api/brief`, `/api/reorder`, `/api/munim` | Morning brief, purchase order drafts, ask the munim |
| `/api/stock`, `/api/dashboard/v2` | Stock views, expiry, missed sales, dashboards |
| `/api/wa`, `/webhooks/whatsapp` | WhatsApp simulator API and the Meta webhook |
| `/api/events?channel=store\|wa` | Server-Sent Events |
| `/api/admin` | `health`, `status`, `demo-checklist`, `reset-demo` |

Legacy endpoints from the first prototype (`/api/voice`, `/api/inventory`, `/api/bill`, `/api/dashboard`) still work.

## Events

Channel `store`: `cart_updated`, `utterance`, `action_proposed`, `action_resolved`, `checkout`, `payment_received`, `brief_ready`, `khata_updated`, `khata_disputed`, `wa_order`, `postpaid_approved`, `galla_closed`, `stock_updated`, `reorder_sent`, `demo_reset`. Channel `wa`: `wa_message`, `wa_status`.

## Testing

- `backend/tests`: 359 tests covering the quantity parser (Hindi and Hinglish numerals, loose and amount-based quantities), GST maths, catalog matching, seed invariants, and every feature's API flow. They run with no keys and no network.
- `scripts/smoke.py`: plays the demo story over HTTP against any running server.
- `frontend/scripts/check-api.mjs` and `check-events.mjs`: exercise the client library and the event contract against a running backend.

## Known limitations

- Single process by design (in-process event bus and SQLite).
- No authentication.
- Paytm Dynamic QR, Postpaid and the Soundbox are emulated.
- Meta test numbers only deliver inside the 24 hour window after the customer messages the shop number; failed sends stay visible in the simulator with the reason.
