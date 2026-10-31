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

Each AI call returns a result envelope `{data, source, latency_ms}` where `source` is `sarvam`, `openrouter`, `rules` or `fixture`. Sarvam is the primary provider for everything it does (speech to text, text to speech, chat with tool calling, vision). The chains are:

- Chat and tool calling: Sarvam `sarvam-105b`, then OpenRouter (`anthropic/claude-haiku-5.5`), then the rules parser, then a fixture.
- Vision: Sarvam `gemma4`, then OpenRouter (`google/gemini-3.1-flash-lite`), then a fixture.

OpenRouter is a backup with limited credit: temperature 0, small `max_tokens`, one retry only on HTTP 429 or 503, and the dollar cost of each call is kept in the result metadata. `/status` shows the remaining credit after a live check. `DEMO_MODE` controls fallback:

| Mode | Behaviour |
|---|---|
| `auto` | Fixtures only when a key is missing or a call fails (default; the demo always completes) |
| `on` | Never call external APIs |
| `off` | Never use fixtures; provider errors surface |

Voice utterances: the rules parser (milliseconds) updates the cart immediately. When it fully explains the utterance (every word is a known item, quantity, unit, filler or command, no udhaar/payment/price/undo words) the LLM is skipped (`source: "rules"`, switch `FAST_PATH=off` restores the old behaviour); otherwise the LLM tool-calling result (4 second budget) replaces the rules result when it arrives.

### Speech without waiting

Replies are worded by `services/voice_style.py` (short warm Hinglish, several variants per situation, never the same line twice in a row, light humour about one reply in five and never on money or errors) and normalised for Bulbul by `prepare_for_tts` (amounts as "249 rupaye", units and symbols as words). Responses never wait for TTS: `POST /api/agent/utterance`, checkout and payment carry `speech {text, pace, pending, key, audio_url, ack}`. A cached clip comes back with `pending: false`; otherwise one background task per key generates it (6 second bound, duplicates coalesce) and publishes `speech_ready {session_id, key, audio_url|null, text, source}` on the `store` channel (`audio_url: null` means speak `text` with browser speech). `GET /api/voice/phrases` serves a warmed bank of about 25 short acknowledgements ("Ji.", "Ho gaya.") that `speech.ack` points at; the response also has `timings {stt_ms, parse_ms, llm_ms, total_ms}`.

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

Channel `store`: `cart_updated`, `utterance`, `action_proposed`, `action_resolved`, `checkout`, `payment_received`, `brief_ready`, `speech_ready`, `khata_updated`, `khata_disputed`, `wa_order`, `wa_question`, `postpaid_approved`, `galla_closed`, `stock_updated`, `reorder_sent`, `demo_reset`. Channel `wa`: `wa_message`, `wa_status`.

## WhatsApp conversation

A customer who messages the shop number is answered like a shopkeeper would answer. `services/wa_orders.py` routes every inbound text (and the text of a voice note) in this order: a khata reply (sahi or galat) first, then an order ("2 maggi", "ek surf aur dal"), then a plain greeting, then the conversation handler `services/wa_chat.py`. A question with no quantity ("Parle-G ka rate kya hai", "kurkure hai?", "do you have atta?") goes to the conversation even if it names a product. A failed or empty transcription never reaches it.

`wa_chat.reply(db, message, customer, history)` returns the text to send plus which path made it. With an LLM it uses Sarvam `sarvam-105b` (OpenRouter as backup) with seven customer-facing tools: `search_products`, `list_category`, `my_khata`, `my_last_order`, `store_info`, `note_request` and `ask_owner`. The model also sees the last 6 messages of that conversation so follow-ups work. Without an LLM (demo mode, no keys, or a failure) a rules path finds products and categories by keyword and answers in the same words; anything it cannot answer is passed to the owner with a `wa_question` event on the `store` channel.

What it will and will not say:

- Prices are always the MRP with GST included. Availability is a word only (available, kam bacha hai, abhi nahi hai); no stock count, cost price, margin, supplier or other customer is ever returned by a tool.
- Khata and order status come only from the sender's own phone number. The tools take no customer argument, and an unknown number is refused.
- An item the shop does not stock is saved as a missed sale, so the owner sees the demand. Timing, delivery, discounts and anything else that is not in the store profile go to the owner instead of being guessed.
- Every reply is checked before it is sent: no emoji or em-dashes, no internal words, and every number must come from a tool result or from the conversation, otherwise the plain wording of the tool result is sent instead.
- Inbound text is trimmed to 500 characters and treated as data, never as instructions. Limits: 20 conversational replies per phone per hour and 400 per day, counted in memory; past a limit nothing is sent and a line is logged. Replies go out through `services.whatsapp.notify`, so the simulator and the live allowlist behave as for every other message.

## Testing

- `backend/tests`: 359 tests covering the quantity parser (Hindi and Hinglish numerals, loose and amount-based quantities), GST maths, catalog matching, seed invariants, and every feature's API flow. They run with no keys and no network.
- `scripts/smoke.py`: plays the demo story over HTTP against any running server.
- `frontend/scripts/check-api.mjs` and `check-events.mjs`: exercise the client library and the event contract against a running backend.

## Known limitations

- Single process by design (in-process event bus and SQLite).
- No authentication.
- Paytm Dynamic QR, Postpaid and the Soundbox are emulated.
- Meta test numbers only deliver inside the 24 hour window after the customer messages the shop number; failed sends stay visible in the simulator with the reason.
