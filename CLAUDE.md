# Paytm Voice Business Suite — CLAUDE.md

## What This Is
Hackathon project for Paytm AI Hackathon (Theme 2: AI for Small Businesses).
Voice-first billing + inventory management for kirana store owners using Sarvam AI (Hinglish STT/LLM/TTS).
The merchant speaks in Hinglish → AI generates bill or updates stock → Paytm QR for payment.

## Running the App

```bash
# Backend (Python 3.10+)
cd backend
pip install -r requirements.txt
cp .env.example .env          # add SARVAM_API_KEY if you have it
python seed.py                # initialize DB + seed 10 products + demo data
uvicorn main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev                   # starts on http://localhost:5173
```

API docs at http://localhost:8000/docs

## Architecture

```
awaaz/
├── backend/
│   ├── main.py               # FastAPI app, CORS, router registration
│   ├── database.py           # SQLite + SQLAlchemy engine/session
│   ├── models.py             # Product, Inventory, Transaction, Customer
│   ├── schemas.py            # Pydantic request/response models
│   ├── seed.py               # 10 products + demo inventory + mock transactions
│   └── routers/
│       ├── voice.py          # STT + Sarvam 30B parsing (+ demo mode fallback)
│       ├── inventory.py      # GET /api/inventory, POST /api/inventory/restock
│       ├── billing.py        # POST /api/bill/generate, confirm, QR, TTS
│       └── dashboard.py      # GET /api/dashboard, /api/alerts, /api/transactions
└── frontend/
    └── src/
        ├── App.jsx           # Router + bottom nav layout
        ├── api/client.js     # All API calls (single source of truth)
        ├── components/
        │   ├── BottomNav.jsx
        │   ├── MicButton.jsx # Reusable voice recording button (WebRTC)
        │   ├── Toast.jsx
        │   └── ItemCard.jsx
        └── pages/
            ├── StockIn.jsx   # PERSON 1 owns this
            ├── Sell.jsx      # PERSON 2 owns this
            └── Dashboard.jsx # PERSON 2 owns this
```

## Branches
- `main` — shared base: working backend, scaffold frontend, seed data
- `feat/voice-pipeline` — **Person 1**: Voice recording + STT + Sarvam 30B parsing + Stock In UI + TTS
- `feat/billing-dashboard` — **Person 2**: Bill UI + QR + payment simulation + Dashboard + charts

**API contracts are frozen on main. Do not change endpoint signatures without telling each other.**

## API Endpoints (All implemented in main)

| Method | Path | Description |
|--------|------|-------------|
| POST | /api/voice/parse | Audio → STT → LLM parse → [{product_id, name, quantity, price}] |
| POST | /api/voice/tts | Text → Bulbul TTS → audio base64 |
| GET | /api/inventory | All products with current stock levels |
| POST | /api/inventory/restock | Add stock from parsed voice items |
| POST | /api/bill/generate | Parsed items → bill with GST breakdown |
| POST | /api/bill/confirm | Confirm bill → deduct inventory → create transaction |
| GET | /api/dashboard | Stats: total_stock_value, today_sales, low_stock_count, top_selling |
| GET | /api/alerts | Items below threshold (low stock) |
| GET | /api/transactions | Recent 20 transactions |

## Sarvam AI Integration

```python
# STT (Saaras)
POST https://api.sarvam.ai/speech-to-text
Headers: api-subscription-key: <KEY>
Body (multipart): file=<audio>, language_code="hi-IN", model="saaras:v2"
Response: { "transcript": "do maggi ek surf excel" }

# TTS (Bulbul V3)
POST https://api.sarvam.ai/text-to-speech
Headers: api-subscription-key: <KEY>
Body: { "inputs": ["Bill ban gaya. 294 rupee."], "target_language_code": "hi-IN", "speaker": "meera" }
Response: { "audios": ["<base64 mp3>"] }

# LLM (Sarvam-M / 30B) - OpenAI-compatible
POST https://api.sarvam.ai/v1/chat/completions
Headers: Authorization: Bearer <KEY>
Body: { "model": "sarvam-m", "messages": [...] }
```

Set `SARVAM_API_KEY` in `backend/.env`. Without it, demo mode activates automatically.

## Demo Mode (CRITICAL — never let the demo fail)

Voice parsing has 5 hardcoded Hinglish phrases that always return perfect results:

| Phrase | Returns |
|--------|---------|
| "do maggi ek surf excel chaar colgate" | Maggi:2, Surf:1, Colgate:4 |
| "das packet maggi paanch kilo chawal do litre tel" | Maggi:10, Rice:5, Oil:2 |
| "aashirvaad atta teen bag tata namak chaar packet" | Atta:3, Salt:4 |
| "paanch dettol sabun teen vim bar do parle g" | Dettol:5, Vim:3, ParleG:2 |
| "ek patanjali shahad do colgate" | Honey:1, Colgate:2 |

If no API key → demo mode. If API fails → fall back to demo mode. Always works.

## Product Catalog (Seeded in DB)

| ID | Name | Hindi | Price | Unit | GST |
|----|------|-------|-------|------|-----|
| 1 | Maggi | मैगी | ₹12 | packet | 12% |
| 2 | Rice 5kg | चावल | ₹350 | bag | 0% |
| 3 | Surf Excel | सर्फ एक्सेल | ₹45 | packet | 18% |
| 4 | Tata Salt | टाटा नमक | ₹28 | packet | 0% |
| 5 | Colgate | कोलगेट | ₹45 | packet | 12% |
| 6 | Aashirvaad Atta 5kg | आशीर्वाद आटा | ₹320 | bag | 0% |
| 7 | Patanjali Honey | पतंजलि शहद | ₹180 | bottle | 12% |
| 8 | Vim Bar | विम बार | ₹15 | bar | 18% |
| 9 | Parle-G | पारले-जी | ₹10 | packet | 12% |
| 10 | Dettol Soap | डेटॉल साबुन | ₹35 | soap | 18% |

Initial inventory has 3 low-stock items (Salt, Atta, Vim) → alerts show immediately on dashboard.

## UI Theme
- Primary (Paytm Blue): `#00B9F5` → `paytm-blue` in Tailwind
- Accent (Orange): `#FF6F00` → `paytm-orange`
- Background: `#F5F7FA`
- Green (in-stock): `#34C759`
- Yellow (medium): `#FFCC00`
- Red (low-stock): `#FF3B30`
- Mobile-first: target 375px width
- Touch targets: minimum 44px height
- Hindi text: `text-xl font-bold` minimum

## Key Demo Numbers
- Demo bill: Maggi×2 + Surf Excel×1 + Colgate×4 → Total ₹294 (incl. GST)
- Today's sales pre-seeded: ₹3,247
- 12 million kirana stores in India
- 80% owners have limited English literacy
- 30 million Paytm merchants (zero CAC)
- 50-100 transactions per merchant per day

## Pitch Script (2 min 40 sec)
1. **Open (20s)**: "India has 12 million kirana stores. 80% owners can't type English..."
2. **Demo 1 - Stock In (30s)**: Speak "Das packet Maggi, paanch kilo chawal, do litre tel" → stock updated
3. **Demo 2 - Sell (40s)**: Speak "Do Maggi, ek Surf Excel, chaar Colgate" → ₹294 QR → payment → stock deducted
4. **Dashboard (15s)**: "Total stock value, today's sales, low stock alerts..."
5. **Close (15s)**: "Voice layer inside Paytm for Business that 30M merchants already have."
