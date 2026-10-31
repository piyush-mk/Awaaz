# Merge decisions and deployment handoff

**Read this before changing anything to fix a deployment problem.** It records what was merged, what was chosen and why. Many of these choices fix bugs that were found by testing real audio and real keys. If something looks wrong, first check section 5. Do not revert a decision here to make a symptom go away without telling the team.

## 1. What is on main

`main` is the merge of two branches, both built on the previous main (`42e0b42`):

| Branch | Author focus | Contents |
|---|---|---|
| `feat/ui-revamp` | Merchant UI and reliability | New UI (mic in every room, less text, English/Hindi), live update fixes, real speech fixes, latest Sarvam models |
| `feat/awaaz-v2` (2 new commits) | Voice speed and providers | Fast path that skips the LLM, non-blocking speech, instant acks, shopkeeper voice lines, OpenRouter as backup AI |

The branch `feat/awaaz-v2` added **no new screens**; its frontend changes were speech logic and small status page additions. Other old branches (`feat/inventory`, `feat/photo-inventory`, `feat/voice-agent`) were not merged. The v1 screens (`/sell`, `/stock-in`, `/photo`, `/dashboard`) remain reachable as before.

The pitch deck is **not** on main. It is uncommitted on `claude/design-presentation-pdf-e54b7f`.

## 2. Decisions: do not undo these

### Voice and AI

| Decision | Why | Do not |
|---|---|---|
| **A failed speech-to-text never invents an order.** With a key set, failure gives an empty transcript, source `failed`, and "Kuch sunai nahi diya". `services/sarvam.py` | `feat/awaaz-v2` and old main returned the canned "do maggi ek surf" order on any STT failure, so a real customer's speech silently billed items nobody said. This happened on every request while `keyterms` was failing | Restore the fixture fallback "to keep the demo alive". Fixtures remain for no key, `DEMO_MODE=on`, or an explicit `X-Demo-Phrase` |
| **`keyterms` are only sent to `saaras:v4`.** | The API returns HTTP 400 for them on v3 | Send them unconditionally |
| **Fast path from `feat/awaaz-v2`** (`fast_path_ok`, `quantity.ParseOutcome.explained`): plain orders skip the LLM. Words about money, khata or prices always go to the LLM | Spoken order dropped from about 2.4 s to about 0.7 s. This stricter rule replaced our broader one from `feat/ui-revamp` | Remove the intent word list; money phrases need the second look |
| **Rules outrank the LLM on quantities** (`counter.rules_outrank_llm`). When both name the same items with different quantities, the parser wins. Also applies when the LLM tries to edit lines of an empty cart | Seen live: rules read "ek Surf, chaar Colgate" correctly and sarvam-105b answered 4 Surf and 1 Colgate. A bill must show what was said | Let the LLM replace rules unconditionally |
| **Replies do not wait for TTS** (`services/speech.py`). A response carries `speech {text, pace, pending, key, audio_url, ack}`, and `speech_ready` arrives over SSE | Payments and carts must never block on audio | Make requests await TTS again |
| **Sarvam first, OpenRouter as backup** for chat and vision. Paytm inference and xAI are removed. OpenRouter credit is small (about $6), so it has low token limits and one retry | Decision from `feat/awaaz-v2` | Add loops or raise limits. `PAYTM_*` and `XAI_KEY` in an old `.env` are ignored and harmless |
| **`res.source in ("sarvam", "openrouter")`** in `counter.py` and `munim.py` | `feat/awaaz-v2` still checked `"paytm"` here, so every OpenRouter answer was discarded. Fixed during the merge | Revert |
| **`bulbul:v4-flash` with voice `simran_enhi_customer`** by default, 16 kHz mp3. `sarvam._tts_speaker` maps old voice names to a valid one | Latest model; its voices have a new name format and the API rejects a mismatch, so an old `.env` must not silence the app | Remove the mapping |
| **"डू" reads as 2** in `quantity.py` | Saaras can hear "do" as डू, which shifted every quantity along by one item | Remove it |
| **The word "munim" is gone from user-visible text and AI prompts.** `services/munim.py` and `/api/munim/*` remain as internal names. `/api/ask` and `/api/ask/examples` are what the app calls | Team decision | Bring it back in copy or prompts |

### Live updates

| Decision | Why | Do not |
|---|---|---|
| **`events.publish_after_commit(db, ...)`** for events fired before a commit | Screens refetch when an event arrives. Published early, they read the old balance | Change these back to `events.publish` |
| **`khata.add_credit` and `record_payment` publish `khata_updated`** | Voice udhaar and khata bills published nothing, so Khata stayed stale | Remove |
| **The SSE `hello` frame has no `id:` line**, and the phone app uses `useEvents(..., { skipHistory: true })` | `id: 0` reset the browser's Last-Event-ID, so any reconnect replayed 50 old events, including old payments | Add the id back |

### UI

| Decision | Why |
|---|---|
| The UI from `feat/ui-revamp` wins everywhere on the merchant screens | Team chose it. `feat/awaaz-v2` speech logic was moved into it |
| One microphone in `components/app/VoiceContext.jsx`, shared by all rooms. The room decides what speech means. `useVoiceHandler` lets the Counter handle its own | Replaces per-screen recorders. The ack, ducking and hands-free suspend from `feat/awaaz-v2` live here now |
| Everything speaks through `lib/speechManager.js` (`feat/awaaz-v2`) | One voice at a time, no double speech, and it handles `speech_ready`. Bypassing it means replies with `pending: true` are never heard |
| Paytm and Cash on the pay sheet complete on one tap | Team asked for fewer steps. The tile names the action, so the tap is the confirmation. **Khata asks whose first, and voice actions still wait for Haan** |
| `SourceChip` only shows `demo` | Team asked for less text. `/status` shows providers |
| All merchant text goes through `lib/i18n.js`. Default Hindi, English in the three-dot menu, stored per phone | Team decision. `format.js` imports `./i18n.js` with the extension because `scripts/check-speech.mjs` runs it under plain node |

## 3. Server environment

Edit `/opt/awaaz/backend/.env`, then `systemctl restart awaaz`.

| Variable | Action |
|---|---|
| `SARVAM_API_KEY` | Required for live AI |
| `SARVAM_STT_MODEL`, `SARVAM_TTS_MODEL`, `SARVAM_TTS_SPEAKER` | **Delete these lines if present.** The defaults are the latest. The team's local `.env` pins `saaras:v3` and `bulbul:v3`, which still work but lose product-name hints and the new voice |
| `OPENROUTER_API_KEY` | Add if available. Without it, `/status` shows `missing_key` for the two OpenRouter cards. That is fine; only the backup is absent |
| `PUBLIC_BASE_URL` | Must be the public https URL, or receipt links and WhatsApp audio point at localhost |
| `DEMO_MODE` | Keep `auto` |
| `PAYTM_API_KEY`, `XAI_KEY` | No longer used; delete or ignore |
| `FAST_PATH`, `VOICE_PRONUNCIATION_FIXES`, `SARVAM_TTS_SAMPLE_RATE` | Optional, leave unset. `FAST_PATH=off` is for debugging only |

## 4. Deploying

Follow `RUNBOOK.md`. Things specific to this merge:

- **One uvicorn worker only.** The event bus and speech tasks are in-process. Several workers break live updates and `speech_ready`.
- **Caddy needs `flush_interval -1`** on the API proxy, or events stall and replies go silent until the browser-voice fallback.
- **`scripts/deploy.sh` builds on the machine running it.** Run `npm ci` in `frontend/` first. `playwright-core` is a dev dependency used only by `check-ui.mjs`, and it does not download a browser.
- **No database schema changes.** The existing SQLite file works. Demo data is relative to today, so press **Reset demo data** on `/status` before rehearsal.
- **First start on keys generates 24 short clips** in the background (`phrases.start_warmup`), and clips regenerate because the voice changed. `backend/.cache` must be writable. The deploy script already keeps it between deploys.
- **HTTPS is required** for the microphone and camera.

### Verifying

```bash
cd backend && .venv/bin/pytest -q                      # no keys, no network
python scripts/smoke.py --base https://<domain>        # RESETS demo data
cd frontend && node scripts/check-speech.mjs https://<domain>    # always pass the URL
cd frontend && node scripts/check-ui.mjs --base https://<domain> # RESETS demo data; needs Chrome
```

`check-speech.mjs` defaults to `http://localhost:8000` and posts real utterances there, so always pass the URL. `check-ui.mjs` expects demo fixtures for its photo steps: on real keys, its blank test image correctly reads as nothing and that step fails. For real keys, use `docs/TEST-CHECKLIST.md`.

Results on the merged tree before pushing are in section 7.

## 5. If something looks wrong

| Symptom | Likely cause | Right fix |
|---|---|---|
| "Kuch sunai nahi diya" for clear speech | STT is failing. The log says `speech to text failed: ...` | Fix the key, model or network. **Do not restore the canned order** |
| No voice, but the bill appears | SSE blocked (`flush_interval`), or more than one worker. The browser voice should still read the reply after a timeout | Fix the proxy or worker count |
| Reply speaks in a robot browser voice | TTS failed or timed out (6 s) | Check `/status`. This is the designed fallback |
| HTTP 400 "Speaker is not recognized" | A voice name that doesn't exist for the model | Unset `SARVAM_TTS_SPEAKER` |
| Khata or Hisaab stale until refresh | Header dot red, or a proxy buffering SSE | Fix the proxy. Do not add polling |
| Old "paid" screen after reload | The `hello` frame or `skipHistory` was changed | Restore them |
| Replies show source `rules` with no LLM call | By design on the fast path | Nothing |
| Brief shows source `rules` | The LLM brief hit its time budget and the template was used. Facts are still correct | Nothing, unless it is every time |
| OpenRouter cards show `missing_key` | No key set | Optional. Add the key |
| Whole app appears in Hindi | The default | Three-dot menu, English |
| Text in English mode reads as Hinglish | Server-written text is not translated (section 6) | Known limit, not a deploy bug |

## 6. Known limits (not bugs)

- **Language:** server text stays Hinglish in English mode: spoken replies, written answers, the brief, bill scan messages. Soundbox, WhatsApp simulator and Status are not translated. Demo names with no Hindi version stay in English.
- **Speech recognition can mishear:** in one live run "दस" came back as "टास", which proposed 1 Maggi instead of 10. Stock waits for Haan and the card shows the quantity, so this is caught before it counts.
- **LLM answers can reword facts awkwardly.** Numbers come from data, but the phrasing is the model's.
- **Payment is simulated** (Payment received button). The UPI QR is real: **real money if scanned**, to `MERCHANT_UPI_VPA`.
- **Postpaid is simulated** and labelled so.

## 7. Verification status

Run on the merged tree before pushing to main:

| Check | Result |
|---|---|
| Backend tests, with and without a real local `.env` | 501 passed |
| `smoke.py` on demo data | 30 of 30 |
| `check-ui.mjs` on demo data, English and Hindi across phone, Soundbox and WhatsApp | 102 of 102 |
| `check-speech.mjs` against a merged backend | 35 of 35 |
| Real Sarvam: speech, LLM, TTS, vision on a rendered bill and parchi | Worked. Order to cart about 0.7 s |
| Real Chrome microphone (fed generated Hindi audio), real Sarvam, new UI | Hold-to-talk 0.8 s, correct bill. Audio clips fetched and played |

**Not verified anywhere yet:**
- OpenRouter with a real key (there is none locally; covered only by mocked tests)
- Real WhatsApp delivery
- iPhone Safari
- Real voices in a noisy shop
- Vision on real photos of cash, shelves and notebook pages
- The deployed site itself
- Hands-free timing: one run took 10.5 s against 4.4 s earlier. The test loops audio with gaps, so the time depends on where the mic starts. Watch it on a real phone

One unexplained event: during the merge a local test server exited once with code 1 after a smoke run, leaving no traceback in its log. It did not recur across a later smoke run, the full UI check and the speech check. If the API restarts unexpectedly on the server, check `journalctl -u awaaz` first.

`docs/TEST-CHECKLIST.md` is the manual test list for the deployed site.
