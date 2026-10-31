# Merge decisions and deployment handoff

**Read this before changing anything to fix a deployment problem.** It records what was merged, what was chosen and why. Many of these choices fix bugs that were found by testing real audio and real keys. If something looks wrong, first check section 5. Do not revert a decision here to make a symptom go away without telling the team.

## 1. What is on main

`main` is the merge of two branches, both built on the previous main (`42e0b42`). `feat/awaaz-v2` is included up to `e884646`:

| Branch | Author focus | Contents |
|---|---|---|
| `feat/ui-revamp` | Merchant UI and reliability | New UI (mic in every room, less text, English/Hindi), live update fixes, real speech fixes, latest Sarvam models |
| `feat/awaaz-v2` | Voice speed, providers, hosting | Fast path that skips the LLM, non-blocking speech, instant acks, shopkeeper voice lines, OpenRouter as backup AI, Roman-letter speech recognition, Mumbai hosting, non-root deploy, live smoke test with real images |

The branch `feat/awaaz-v2` added **no new screens**; its frontend changes were speech logic and small status page additions. Other old branches (`feat/inventory`, `feat/photo-inventory`, `feat/voice-agent`) were not merged. The v1 screens (`/sell`, `/stock-in`, `/photo`, `/dashboard`) remain reachable as before.

The live server named in `README.md` is https://65-20-73-34.sslip.io (Mumbai). When this was written it still ran the `feat/awaaz-v2` build, not this merge. Nothing in this merge has been deployed.

The pitch deck is **not** on main. It is uncommitted on `claude/design-presentation-pdf-e54b7f`.

## 2. Decisions: do not undo these

### Voice and AI

| Decision | Why | Do not |
|---|---|---|
| **A failed speech-to-text never invents an order.** With a key set, failure gives an empty transcript, source `failed`, and "Kuch sunai nahi diya". `services/sarvam.py` | `feat/awaaz-v2` and old main returned the canned "do maggi ek surf" order on any STT failure, so a real customer's speech silently billed items nobody said. This happened on every request while `keyterms` was failing | Restore the fixture fallback "to keep the demo alive". Fixtures remain for no key, `DEMO_MODE=on`, or an explicit `X-Demo-Phrase` |
| **`keyterms` are only sent to `saaras:v4`.** | The API returns HTTP 400 for them on v3 | Send them unconditionally |
| **`SARVAM_STT_MODE=translit` is the default, on `saaras:v4` with `keyterms`.** Sarvam returns "Do Maggi, ek Surf Excel" in Roman letters | Decision from `feat/awaaz-v2`, then tested on the merged app: 20 orders, 2 voices, generated audio. `translit` 20 of 20 right and 18 without the LLM, `codemix` 20 of 20 and 18, default Devanagari 19 of 20 and 13. Sarvam's page says `mode` is for v3, but v4 accepts it and it changes the output | Remove it to fix a mishearing. If real phones show English misreads like "egg" for "ek", try `codemix` and compare; it writes Hindi words in Devanagari. A blank value means `translit`, so use `transcribe` for all Devanagari |
| **Fast path from `feat/awaaz-v2`** (`fast_path_ok`, `quantity.ParseOutcome.explained`): plain orders skip the LLM. Words about money, khata or prices always go to the LLM | Spoken order dropped from about 2.4 s to about 0.7 s. This stricter rule replaced our broader one from `feat/ui-revamp` | Remove the intent word list; money phrases need the second look |
| **Rules outrank the LLM on every quantity they heard** (`counter.rules_outrank_llm`). The LLM still fills an item the rules heard no number for, and decides alone if a number was left unplaced. It also cannot edit lines of an empty cart | Seen live: rules read "ek Surf, chaar Colgate" correctly and sarvam-105b answered 4 Surf and 1 Colgate. A bill must show what was said. An earlier all-or-nothing version kept a wrong rules answer over a right LLM answer, so it was narrowed | Let the LLM replace rules unconditionally, or make the rules win on numbers they did not hear |
| **A number stays with its own item** (`quantity.parse_order_full`). An unknown word before the first item no longer means "number comes after the item", and in a number-first sentence a number directly before the next item is that item's | Seen live: "Baarah Maggi, pandrah Colgate" billed 15 Maggi and 1 Colgate, and "Taas packet Maggi aur paanch Colgate" billed 5 and 1 | Revert. `tests/test_stt_translit.py` covers the sentence shapes |
| **Number spellings Sarvam really returns are in the tables**: baarah, tera, dus, taas, दास, टास and others, plus टू, थ्री and the rest from `feat/awaaz-v2` | Roman transcripts spell numbers in many ways, and an unknown spelling loses the quantity | Remove them. Add new ones you see in the logs |
| **`catalog.normalize` removes the Hindi full stop "।"** | It was kept as part of the last word, so "दो।" or "पाँच।" was an unknown word in every Devanagari transcript | Revert |
| **"de do" means give**, in both scripts, and one item heard in two pieces ("Tata नामक") counts once | "de" was an unknown word that sent a very common phrase to the LLM. Split items were added up, which billed 3 instead of 2 | Revert |
| **Spoken confirmations read items back only if the line fits 48 characters** (`compose_spoken`) | Decision from `feat/awaaz-v2`: TTS time grows with length, and the screen shows the items | Lengthen them |
| **Host in Mumbai** | Decision from `feat/awaaz-v2`, which measured it: speech 1.1 s to 0.25 s, LLM 0.7 s to 0.14 s, each request 330 ms closer than the US | Move the API out of India to fix something else |
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
| `SARVAM_STT_MODEL`, `SARVAM_STT_MODE`, `SARVAM_TTS_MODEL`, `SARVAM_TTS_SPEAKER` | **Delete these lines if present.** The defaults are the latest. Older `.env` files, including the `.env.example` on `feat/awaaz-v2`, pin `bulbul:v3` and `ritu`, or `saaras:v3`. Those still work but lose the new voice and, on v3, the product-name hints |
| `OPENROUTER_API_KEY` | Add if available. Without it, `/status` shows `missing_key` for the two OpenRouter cards. That is fine; only the backup is absent |
| `PUBLIC_BASE_URL` | Must be the public https URL, or receipt links and WhatsApp audio point at localhost |
| `DEMO_MODE` | Keep `auto` |
| `PAYTM_API_KEY`, `XAI_KEY` | No longer used; delete or ignore |
| `FAST_PATH`, `VOICE_PRONUNCIATION_FIXES`, `SARVAM_TTS_SAMPLE_RATE` | Optional, leave unset. `FAST_PATH=off` is for debugging only |

## 4. Deploying

Follow `RUNBOOK.md`. Things specific to this merge:

- **One uvicorn worker only.** The event bus and speech tasks are in-process. Several workers break live updates and `speech_ready`.
- **The proxy must not buffer events.** Caddy needs `flush_interval -1`. `RUNBOOK.md` also describes an nginx setup for a shared server; there, the `/api` location needs `proxy_buffering off`. Otherwise events stall and replies go silent until the browser-voice fallback. This is general nginx behaviour, not something tested on the Mumbai server, so check what that server has.
- **Non-root deploy:** `AWAAZ_HOST=deploy@<server> AWAAZ_RUN_AS=awaaz AWAAZ_URL=https://<domain> scripts/deploy.sh` writes files as the service user and restarts with sudo. Use this if the server shares another app. Do not edit the other app's config.
- **`scripts/deploy.sh` builds on the machine running it.** Run `npm ci` in `frontend/` first. `playwright-core` is a dev dependency used only by `check-ui.mjs`, and it does not download a browser.
- **No database schema changes.** The existing SQLite file works. Demo data is relative to today, so press **Reset demo data** on `/status` before rehearsal.
- **First start on keys generates 24 short clips** in the background (`phrases.start_warmup`), and clips regenerate because the voice changed. `backend/.cache` must be writable. The deploy script already keeps it between deploys.
- **HTTPS is required** for the microphone and camera.

### Verifying

```bash
cd backend && .venv/bin/pytest -q                      # no keys, no network
python scripts/smoke.py --base https://<domain>        # RESETS demo data; expects fixtures
python scripts/smoke.py --base https://<domain> --live # RESETS demo data; for a server with real keys, uses real images
cd frontend && node scripts/check-speech.mjs https://<domain>    # always pass the URL
cd frontend && node scripts/check-ui.mjs --base https://<domain> # RESETS demo data; needs Chrome
```

`check-speech.mjs` defaults to `http://localhost:8000` and posts real utterances there, so always pass the URL. `check-ui.mjs` expects demo fixtures for its photo steps: on real keys, its blank test image correctly reads as nothing and that step fails. For real keys, use `smoke.py --live` and `docs/TEST-CHECKLIST.md`. `smoke.py --live` logs one `speech to text failed` line because its WhatsApp step sends an empty voice note with a demo phrase. More than that during real use is a problem.

Results on the merged tree before pushing are in section 7.

## 5. If something looks wrong

| Symptom | Likely cause | Right fix |
|---|---|---|
| A number lands on the wrong item, or a spoken quantity is lost | A spelling the tables do not have. Check the `transcript` in the response | Add the spelling to `quantity.py` with a test. Do not switch the rules guard off |
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
- **Speech recognition can mishear:** "दस" has come back as "टास", "ek" as "egg", "कोलगेट" as "कोल्ड्रिंक", and "Vim" as "film". The parser now reads the first, but the rest can still reach the card. The card shows item and quantity, and stock waits for Haan.
- **LLM answers can reword facts awkwardly.** Numbers come from data, but the phrasing is the model's.
- **Payment is simulated** (Payment received button). The UPI QR is real: **real money if scanned**, to `MERCHANT_UPI_VPA`.
- **Postpaid is simulated** and labelled so.

## 7. Verification status

Run on the final merged code before pushing to main, locally, not on the server:

| Check | Result |
|---|---|
| Backend tests, no keys | 536 passed |
| `smoke.py` on demo data | 30 of 30 |
| `smoke.py --live` with real Sarvam, including real vision on the rendered bill and handwritten list in `scripts/testdata` | 35 of 35 |
| `check-ui.mjs` on demo data, English and Hindi across phone, Soundbox and WhatsApp | 102 of 102 |
| `check-speech.mjs` against a merged backend | 35 of 35 |
| 20 generated Hindi orders through real Sarvam speech recognition and the app, in `translit` mode | 20 of 20 correct, 18 without the LLM, speech recognition about 0.22 s |
| Real Chrome microphone fed generated Hindi audio, real Sarvam, new UI | Hold-to-talk 1.3 s, hands-free 5.6 s, correct items, audio clips played, no page errors. The test audio loops, so hold-to-talk caught "do Maggi" a second time and showed 4 Maggi. That comes from the test, not the app |

**Not verified anywhere yet:**
- This merged build on the deployed site
- OpenRouter with a real key on this merge (there is none locally; covered only by mocked tests)
- Real WhatsApp delivery
- iPhone Safari
- Real human voices. Every live speech test here used generated audio. Check `docs/TEST-CHECKLIST.md` rows 0h to 0m first, on a real phone in a shop
- Vision on real photos of cash, shelves and notebook pages
- Hands-free timing: 5.6 s in the last run and 10.5 s in an earlier one. The test loops audio with gaps, so the time depends on where the mic starts. Watch it on a real phone

One unexplained event: during the merge a local test server exited once with code 1 after a smoke run, leaving no traceback in its log. It did not recur in later runs. If the API restarts unexpectedly on the server, check `journalctl -u awaaz` first.

`docs/TEST-CHECKLIST.md` is the manual test list for the deployed site.
