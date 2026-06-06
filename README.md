# Awaaz

Voice-first billing + inventory assistant for kirana stores.

## Run

```bash
cd backend
pip install -r requirements.txt
copy .env.example .env
# set SARVAM_API_KEY and PAYTM_API_KEY in .env
python seed.py
uvicorn main:app --reload --port 8000

cd ../frontend
npm install
npm run dev
```

## Voice

- `/api/voice/parse` accepts transcript text or audio and returns parsed items.
- The parser uses Sarvam STT plus Paytm Inference for item extraction.
- Custom items are allowed in stock-in and get created on confirm.
- `/api/voice/tts` returns Sarvam TTS audio when `SARVAM_API_KEY` is set.
- If TTS audio is silent or fails to play, the frontend falls back to browser speech synthesis.
- Confirming stock-in always speaks a generic success message.

## Notes

- Seed the database before testing voice flows.
- `PAYTM_API_KEY` is required for parsing.
- `SARVAM_API_KEY` is required for STT and TTS.