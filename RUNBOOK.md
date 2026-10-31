# Awaaz runbook

How to deploy, add keys, rehearse and troubleshoot. Replace `<server>` and `<domain>` with your own host.

## Deployment shape

- One Linux server, Python 3.12, one **uvicorn worker** under systemd bound to `127.0.0.1:8056` (live events use an in-process bus, so never run more than one worker).
- Caddy in front for HTTPS (HTTPS is required for microphone and camera in browsers, and for the WhatsApp webhook). It serves `frontend/dist` and proxies `/api/*`, `/r/*`, `/k/*`, `/webhooks/*`, `/docs` and `/openapi.json` to the API with `flush_interval -1` so streaming works.
- Secrets live only in `/opt/awaaz/backend/.env` on the server. Never commit `.env`; deploys never copy it.

Example Caddyfile:

```
<domain> {
	encode gzip
	@api path /api/* /r/* /k/* /webhooks/* /docs /openapi.json /health
	handle @api {
		reverse_proxy 127.0.0.1:8056 {
			flush_interval -1
		}
	}
	handle {
		root * /opt/awaaz/frontend/dist
		try_files {path} /index.html
		file_server
	}
}
```

Redeploy after code changes (builds the frontend locally, syncs, restarts):

```bash
AWAAZ_HOST=root@<server> AWAAZ_URL=https://<domain> scripts/deploy.sh
```

Set `PUBLIC_BASE_URL=https://<domain>` in the server `.env`, otherwise receipt links point at `localhost`.

## Adding keys

Edit `/opt/awaaz/backend/.env`, then `systemctl restart awaaz`.

| Key | Effect if missing |
|---|---|
| `SARVAM_API_KEY` | Speech, LLM, spoken replies and vision fall back to fixtures and browser voice |
| `OPENROUTER_API_KEY` | Backup AI only (chat and vision after Sarvam fails). Optional `OPENROUTER_MODEL` and `OPENROUTER_VISION_MODEL`. The account has little credit (about $6): `/status` shows what is left after a Live check |
| `WA_TOKEN`, `WA_PHONE_NUMBER_ID`, `WA_APP_SECRET` | In-app WhatsApp simulator only (nothing breaks) |
| `MERCHANT_UPI_VPA` | QR pays the placeholder id, not yours. **Real money if scanned** |

Keep `DEMO_MODE=auto`. `off` surfaces raw provider errors; use it only to diagnose a failing live call.

### WhatsApp (Meta) setup

1. In your Meta developer app, WhatsApp, API setup: copy the token and phone number id, and add the recipient phones (up to 5 on a test number).
2. Webhook: callback URL `https://<domain>/webhooks/whatsapp`, verify token equal to `WA_VERIFY_TOKEN` in the server `.env`; subscribe to `messages`.
3. Each phone must send "hi" to the test number first (24 hour window). Otherwise Meta rejects the shop's messages; they stay visible in `/wa` marked failed with the reason.
4. Receipt audio arrives as an audio-file attachment, not a voice-note bubble.

## Before every rehearsal and the demo

1. Press **Reset demo data** on `/status`, or `POST /api/admin/reset-demo`. Required after midnight: the seed is relative to "today", so galla and "yesterday" numbers drift otherwise.
2. `/status`: every checklist item green; providers `live` for the keys you set; press **Live check**.
3. `python scripts/smoke.py --base https://<domain> --live` (it resets the demo data first, so only point it at a demo server).
4. On the phone allow microphone and camera once. On the Soundbox laptop click once to enable sound.

See [docs/DEMO.md](docs/DEMO.md) for the script. The bill-scan sample also restocks Colgate: sell the Colgate before scanning the bill if you want "Colgate 8 left".

## Security

There is no login. Anyone who can reach the server can read data, reset the demo and spend your API credits once keys are set. Do not publish the URL; add authentication (for example Caddy basic auth in front of the API) before sharing a keyed instance.

## Troubleshooting

- Logs: `journalctl -u awaaz -f` and `journalctl -u caddy -f`.
- Live events not updating: confirm a single worker and that Caddy proxies with `flush_interval -1`.
- Receipts or links show `localhost`: set `PUBLIC_BASE_URL`.
- Small servers: build the frontend on your own machine, not on the server.
- Local development: `cd backend && .venv/bin/uvicorn main:app --port 8000` and `cd frontend && npm run dev` (http://localhost:5173 proxies the API).
- Tests: `cd backend && .venv/bin/pytest -q` (no keys needed).
