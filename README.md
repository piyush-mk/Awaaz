# Awaaz — Voice Business Suite for Kirana Stores

> Paytm AI Hackathon — Theme 2: AI for Small Businesses

Voice-first billing and inventory management for India's 12 million kirana store owners. Merchants speak in Hinglish → AI understands → stock updates or bill is generated → Paytm QR for payment.

## The Problem

80% of kirana store owners have limited English literacy. Existing billing and inventory apps require typing in English. Awaaz removes that barrier entirely — owners just speak naturally in Hindi/Hinglish.

## Features

### 🎙️ Voice Stock In
Speak item names and quantities in Hinglish. Sarvam AI (saaras:v3) transcribes the audio, Paytm AI (Llama 3.3 70B via tool calling) parses it into structured inventory items. Unrecognized products are automatically added to your catalog.

> "Das packet Maggi, paanch kilo chawal, do litre tel"

### 📸 Photo Inventory (Shelf Scan)
Take a photo of your shelf. Grok Vision (xAI) detects all visible products and quantities. Catalog items get restocked instantly. New products are auto-added to your catalog — no manual entry needed.

### 🧾 Voice Billing (Sell)
Speak what a customer is buying. AI generates a GST-compliant bill with itemized breakdown. Paytm QR code generated for UPI payment. Stock is automatically deducted on confirmation.

### 📊 Dashboard
Real-time stats: total stock value, today's sales, low stock alerts, top-selling products, recent transactions. Low stock items flagged immediately.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + SQLAlchemy + SQLite |
| Frontend | React 18 + Vite + Tailwind CSS |
| Speech-to-Text | Sarvam AI — Saaras v3 (`hi-IN`) |
| Text-to-Speech | Sarvam AI — Bulbul v3 |
| LLM Parse | Paytm AI Gateway — Llama 3.3 70B Versatile |
| Vision | xAI — Grok Vision |
| Payments | Paytm UPI QR (UPI deep link) |

## Running Locally

```bash
# Backend
cd backend
pip install -r requirements.txt
cp .env.example .env   # add your API keys
python seed.py         # seed 10 products + demo data
uvicorn main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev            # http://localhost:5173
```

### Required API Keys (in `backend/.env`)

```env
SARVAM_API_KEY=your_key          # sarvam.ai — STT + TTS
PAYTM_API_KEY=your_key           # api.inference.paytm.com — LLM
XAI_KEY=your_key                 # x.ai — vision/shelf scan
```

Without keys, voice parsing falls back to demo mode (5 hardcoded Hinglish phrases always work).

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/voice/parse` | Audio/text → structured items (STT + LLM) |
| POST | `/api/voice/tts` | Text → Hindi audio (Bulbul TTS) |
| POST | `/api/photo/parse` | Shelf photo → detected products (Grok Vision) |
| GET | `/api/inventory` | All products with stock levels |
| POST | `/api/inventory/restock` | Add stock |
| POST | `/api/inventory/add-product` | Add new product to catalog |
| POST | `/api/bill/generate` | Items → GST bill |
| POST | `/api/bill/confirm` | Confirm sale → deduct stock |
| GET | `/api/dashboard` | Sales stats + low stock alerts |
| GET | `/api/alerts` | Low stock items |
| GET | `/api/transactions` | Recent 20 transactions |

## Demo Script (2 min 40 sec)

1. **Stock In by Voice** — "Das packet Maggi, paanch kilo chawal" → items appear as cards → Confirm → stock updated
2. **Stock In by Photo** — Take shelf photo → AI detects all products → new items auto-added to catalog → stock updated
3. **Sell** — "Do Maggi, ek Surf Excel, chaar Colgate" → ₹294 bill → Paytm QR → confirm → stock deducted
4. **Dashboard** — ₹3,247 today's sales · 3 low stock alerts · top products

## Key Numbers

- 12 million kirana stores in India
- 80% owners have limited English literacy
- 30 million Paytm merchants (zero CAC for distribution)
- 50–100 transactions per merchant per day

## Team

- **Aadarsh** — Photo Inventory (shelf scan via Grok Vision), backend integration, deployment
- **Piyush** — Voice pipeline (STT + LLM parse + TTS), billing flow, dashboard
