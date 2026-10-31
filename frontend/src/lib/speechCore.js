// Speech engine: pure JavaScript, no React, no DOM globals. Everything environmental (Audio, speechSynthesis,
// timers, clock) is injected, so scripts/check-speech.mjs can drive it with fakes under plain node.
// The browser binding lives in lib/speechManager.js.
//
// What it guarantees
//   * One voice at a time. Items wait in a queue and never overlap.
//   * Three kinds of item:  'ack'    a short pre-recorded "ji" played the instant the mic stops
//                           'reply'  a spoken answer; a newer reply ducks and replaces an older one
//                           'money'  payment announcements; never dropped, never ducked
//   * speak(reply) understands the backend speech object { text, pace, pending, key, audio_url, ack }:
//        audio_url set            -> play it now
//        pending: true            -> hold until speak() / speechReady() delivers the audio, but never longer
//                                    than pendingTimeoutMs; then the browser voice reads `text` (no silence)
//        audio_url null, !pending -> browser voice reads `text`
//   * A key is spoken once. Server audio and the browser voice are never both used for one reply:
//     the browser voice is only a fallback when the audio could not START.
//   * Ducking is a short volume ramp (fadeMs), not a cut.

export const ACK_IDS = ['ack_ji', 'ack_haan_ji', 'ack_ek_second']

/** Random ack id that differs from `last` (when there is a choice). */
export function pickAck(last, rnd = Math.random, ids = ACK_IDS) {
  const pool = ids.length > 1 ? ids.filter((id) => id !== last) : ids
  return pool[Math.min(pool.length - 1, Math.floor(rnd() * pool.length))]
}

/**
 * Normalise anything speakable into { key, text, url, b64, pending, lang }.
 * Accepts a string, a speech object, or a whole API reply that has `speech` and/or the legacy
 * spoken_text / audio_url / audio_base64 fields.
 */
export function normalizeSpeech(input, opts = {}) {
  let text = ''
  let url = null
  let b64 = null
  let pending = false
  let key = null
  if (typeof input === 'string') {
    text = input
  } else if (input && typeof input === 'object') {
    const sp = input.speech && typeof input.speech === 'object' ? input.speech : null
    const top = sp ? input : {}
    const src = sp || input
    text = src.text || src.spoken_text || top.spoken_text || top.text || input.message_hi || input.answer || ''
    url = sp && 'audio_url' in sp ? sp.audio_url : input.audio_url ?? input.url ?? null
    b64 = src.audio_base64 || top.audio_base64 || null
    pending = src.pending === true
    key = src.key ?? null
  }
  if (opts.key !== undefined && opts.key !== null) key = opts.key
  if (opts.audioUrl) url = opts.audioUrl
  if (opts.audioBase64) b64 = opts.audioBase64
  if (opts.text) text = opts.text
  if (url || b64) pending = false
  return { key: key === null ? null : String(key), text: String(text || '').trim(), url: url || null, b64, pending, lang: opts.lang || 'hi' }
}

export function createSpeechEngine(env) {
  const {
    createAudio, // (url) -> audio-like { play(), pause(), volume, currentTime, onended, onerror }
    synth = null, // speechSynthesis-like { speak, cancel, getVoices }
    Utterance = null, // SpeechSynthesisUtterance-like constructor
    setTimeout: setT = globalThis.setTimeout,
    clearTimeout: clearT = globalThis.clearTimeout,
    now = () => Date.now(),
    resolveUrl = (u) => u,
    fetchPhrases = null, // () -> Promise<{ready, phrases}>
    unlockHook = null, // () => void: silent audio / synth poke inside a user gesture
    pendingTimeoutMs = 3500,
    fadeMs = 120,
    fadeSteps = 6,
    ackFastMs = 250,
    autoDedupMs = 4000,
    audioGuardMs = 45000,
    phraseRetryMs = 10000,
    phraseRetries = 6,
    random = Math.random,
  } = env

  const state = { unlocked: !!env.unlocked, speaking: false, muted: false, phrasesReady: false }
  const listeners = new Set()
  let version = 0
  const emit = () => {
    version += 1
    listeners.forEach((fn) => {
      try {
        fn({ ...state })
      } catch {
        /* a bad listener must not stop speech */
      }
    })
  }
  const setState = (patch) => {
    let changed = false
    Object.entries(patch).forEach(([k, v]) => {
      if (state[k] !== v) {
        state[k] = v
        changed = true
      }
    })
    if (changed) emit()
  }

  let queue = []
  let current = null // { item, stop(ms) }
  let pumping = false
  const pending = new Map() // key -> { item, timer }
  const seen = new Map() // key -> time
  const phrases = new Map() // id -> { id, text, audio_url, kind, audio }
  let lastAck = null
  let interacted = !!env.unlocked
  let nextId = 1

  // ----- dedup --------------------------------------------------------------------------------------------

  // Two layers. A key is spoken once, ever. The same words (when either side has no key, e.g. the HTTP reply
  // and the SSE `utterance` event describing one reply) are spoken once per autoDedupMs.
  const contentSeen = new Map() // text -> { at, explicit }
  function remember(norm, explicit) {
    seen.set(norm.key, now())
    if (seen.size > 400) seen.delete(seen.keys().next().value)
    const ck = norm.text || norm.url
    if (ck) {
      contentSeen.set(ck, { at: now(), explicit })
      if (contentSeen.size > 200) contentSeen.delete(contentSeen.keys().next().value)
    }
  }
  function isDuplicate(norm, explicit) {
    if (explicit && seen.has(norm.key)) return true
    const prev = contentSeen.get(norm.text || norm.url)
    return !!prev && now() - prev.at < autoDedupMs && (!explicit || !prev.explicit)
  }

  // ----- item lifecycle -----------------------------------------------------------------------------------

  function makeItem(kind, norm, extra = {}) {
    let resolve
    const done = new Promise((r) => {
      resolve = r
    })
    return { id: nextId++, kind, key: norm.key, text: norm.text, url: norm.url, b64: norm.b64, lang: norm.lang, done, resolve, ...extra }
  }
  const settle = (item, value) => {
    if (item.settled) return
    item.settled = true
    item.resolve(value)
  }

  // ----- playback ------------------------------------------------------------------------------------------

  function rampDown(audio, ms) {
    return new Promise((resolve) => {
      const start = audio.volume ?? 1
      let step = 0
      if (ms <= 0) {
        resolve()
        return
      }
      const tick = () => {
        step += 1
        try {
          audio.volume = Math.max(0, start * (1 - step / fadeSteps))
        } catch {
          /* ignore */
        }
        if (step >= fadeSteps) resolve()
        else setT(tick, ms / fadeSteps)
      }
      setT(tick, ms / fadeSteps)
    })
  }

  function playAudio(item) {
    return new Promise((resolve) => {
      let audio
      try {
        audio = item.audioEl || createAudio(resolveUrl(item.url) || item.b64Url)
      } catch {
        resolve({ started: false })
        return
      }
      let started = false
      let finished = false
      let guard = null
      const finish = (result) => {
        if (finished) return
        finished = true
        clearT(guard)
        audio.onended = null
        audio.onerror = null
        resolve({ started, ...result })
      }
      current = {
        item,
        stop: async (ms) => {
          if (finished) return
          if (started) await rampDown(audio, ms)
          try {
            audio.pause()
          } catch {
            /* ignore */
          }
          finish({ stopped: true })
        },
      }
      try {
        audio.volume = 1
        audio.currentTime = 0
      } catch {
        /* element not seekable yet */
      }
      audio.onended = () => finish({})
      audio.onerror = () => finish({ error: true })
      guard = setT(() => {
        try {
          audio.pause()
        } catch {
          /* ignore */
        }
        finish({ error: true })
      }, audioGuardMs)
      let p
      try {
        p = audio.play()
      } catch (e) {
        finish({ error: true, blocked: e && e.name === 'NotAllowedError' })
        return
      }
      Promise.resolve(p).then(
        () => {
          started = true
        },
        (e) => finish({ error: true, blocked: !!e && e.name === 'NotAllowedError' }),
      )
    })
  }

  function playSynth(item) {
    return new Promise((resolve) => {
      if (!synth || !Utterance || !item.text) {
        resolve({ started: false })
        return
      }
      let finished = false
      let guard = null
      const finish = (result) => {
        if (finished) return
        finished = true
        clearT(guard)
        resolve({ started: true, ...result })
      }
      current = {
        item,
        stop: async () => {
          try {
            synth.cancel()
          } catch {
            /* ignore */
          }
          finish({ stopped: true })
        },
      }
      try {
        const u = new Utterance(item.text)
        const lang = item.lang === 'en' ? 'en-IN' : 'hi-IN'
        u.lang = lang
        u.rate = item.rate || 0.95
        const voices = (synth.getVoices && synth.getVoices()) || []
        const match = voices.find((v) => v.lang && v.lang.toLowerCase().startsWith(lang.slice(0, 2).toLowerCase()))
        if (match) u.voice = match
        u.onend = () => finish({})
        u.onerror = () => finish({ error: true })
        guard = setT(() => {
          try {
            synth.cancel()
          } catch {
            /* ignore */
          }
          finish({ error: true })
        }, 4000 + item.text.length * 110)
        synth.speak(u)
      } catch {
        finish({ error: true })
      }
    })
  }

  async function run(item) {
    let outcome = { started: false }
    if (item.url || item.b64 || item.audioEl) {
      outcome = await playAudio(item)
      if (outcome.blocked) env.onBlocked?.()
      // The browser voice is only a fallback when the audio never started: never both for one reply.
      if (!outcome.started && !outcome.stopped && item.text && item.kind !== 'ack') outcome = await playSynth(item)
    } else if (item.text && item.kind !== 'ack') {
      outcome = await playSynth(item)
    }
    return outcome
  }

  async function pump() {
    if (pumping) return
    pumping = true
    while (queue.length) {
      const item = queue.shift()
      if (state.muted) {
        settle(item, false)
        continue
      }
      setState({ speaking: true })
      let outcome
      try {
        outcome = await run(item)
      } catch {
        outcome = { started: false }
      }
      current = null
      settle(item, !!outcome.started && !outcome.stopped)
    }
    pumping = false
    setState({ speaking: false })
  }

  const duckCurrent = (predicate) => {
    if (current && predicate(current.item)) return current.stop(fadeMs)
    return Promise.resolve()
  }
  const dropQueued = (predicate) => {
    queue = queue.filter((it) => {
      if (!predicate(it)) return true
      settle(it, false)
      return false
    })
  }
  function killPending(predicate) {
    for (const [key, p] of pending) {
      if (predicate(p.item)) {
        clearT(p.timer)
        pending.delete(key)
        settle(p.item, false) // the key stays in `seen`: a late speech_ready is ignored
      }
    }
  }

  function enqueue(item) {
    if (item.kind === 'reply') {
      // a newer reply is already on its way: this one is stale
      for (const p of pending.values()) {
        if (p.item.kind === 'reply' && p.item.id > item.id) {
          settle(item, false)
          return item
        }
      }
      dropQueued((it) => it.kind !== 'money')
      killPending((it) => it.kind !== 'money' && it.id < item.id)
      duckCurrent((it) => it.kind === 'reply')
      queue.push(item)
    } else if (item.kind === 'money') {
      let at = queue.findIndex((it) => it.kind !== 'money')
      if (at < 0) at = queue.length
      queue.splice(at, 0, item)
      duckCurrent((it) => it.kind !== 'money')
    } else {
      queue.push(item)
    }
    pump()
    return item
  }

  // ----- public: speak / speechReady ---------------------------------------------------------------------------

  function startPending(item) {
    const timer = setT(() => {
      const p = pending.get(item.key)
      if (!p || p.item !== item) return
      pending.delete(item.key)
      // no speech_ready in time: the browser voice reads the text so there is never silence
      item.url = null
      item.timedOut = true
      enqueue(item)
    }, pendingTimeoutMs)
    pending.set(item.key, { item, timer })
  }

  /**
   * speak('text' | speechObject | apiReply, { kind: 'reply'|'money', key, lang }) -> Promise<boolean>
   * Resolves true when something was actually played, false when dropped / deduped / muted / superseded.
   */
  function speak(input, opts = {}) {
    const norm = normalizeSpeech(input, opts)
    const kind = opts.kind === 'money' ? 'money' : 'reply'
    if (!norm.text && !norm.url && !norm.b64) return Promise.resolve(false)
    const explicit = !!norm.key
    if (!explicit) norm.key = `auto:${nextId}:${norm.text || norm.url}`

    // a pending reply gets its audio (or its death) through here too
    const p = pending.get(norm.key)
    if (p) {
      if (norm.url || norm.b64) return resolvePending(norm.key, { audio_url: norm.url, audio_base64: norm.b64, text: norm.text })
      return p.item.done
    }
    if (!opts.replay && isDuplicate(norm, explicit)) return Promise.resolve(false)
    remember(norm, explicit)
    if (state.muted) return Promise.resolve(false)

    if (opts.interrupt) newTurn()
    const item = makeItem(kind, norm, { rate: opts.rate })
    if (norm.b64 && !norm.url) item.b64Url = `data:audio/mpeg;base64,${norm.b64}`
    if (norm.pending) {
      startPending(item)
      return item.done
    }
    enqueue(item)
    return item.done
  }

  function resolvePending(key, data) {
    const p = pending.get(key)
    if (!p) return Promise.resolve(false)
    clearT(p.timer)
    pending.delete(key)
    const item = p.item
    if (data.text) item.text = data.text
    item.url = data.audio_url || null
    if (!item.url && data.audio_base64) {
      item.b64 = data.audio_base64
      item.b64Url = `data:audio/mpeg;base64,${data.audio_base64}`
    }
    enqueue(item)
    return item.done
  }

  /**
   * SSE `speech_ready` {session_id, key, audio_url|null, text, source}. Resolves a pending reply; when nothing
   * is waiting for the key (the event beat the HTTP response, or another device asked) it is spoken as new.
   */
  function speechReady(d, opts = {}) {
    if (!d || typeof d !== 'object') return Promise.resolve(false)
    const key = d.key === undefined || d.key === null ? null : String(d.key)
    if (key && pending.has(key)) return resolvePending(key, d)
    if (key && seen.has(key)) return Promise.resolve(false) // already spoken, timed out, or superseded
    return speak({ text: d.text, audio_url: d.audio_url, audio_base64: d.audio_base64, key, pending: false }, opts)
  }

  const hasPending = (key) => key !== undefined && key !== null && pending.has(String(key))

  // ----- public: turns and cancelling ---------------------------------------------------------------------------

  /** A new utterance starts: older replies stop (short fade); money announcements are untouched. */
  function newTurn() {
    dropQueued((it) => it.kind !== 'money')
    killPending((it) => it.kind !== 'money')
    return duckCurrent((it) => it.kind !== 'money')
  }

  /** Stop everything now (also money). Used for mute and demo reset. */
  function cancel() {
    dropQueued(() => true)
    killPending(() => true)
    if (current) current.stop(0)
  }

  function setMuted(m) {
    setState({ muted: !!m })
    if (m) cancel()
  }

  // ----- phrases and acknowledgements ---------------------------------------------------------------------------

  function preloadAll() {
    if (!interacted) return
    phrases.forEach((ph) => {
      if (ph.audio || !ph.audio_url) return
      try {
        const a = createAudio(resolveUrl(ph.audio_url))
        a.preload = 'auto'
        a.load?.()
        ph.audio = a
      } catch {
        /* preload is an optimisation */
      }
    })
  }

  function setPhrases(map) {
    Object.entries(map || {}).forEach(([id, ph]) => {
      if (!ph || typeof ph !== 'object') return
      const old = phrases.get(id)
      const same = old && old.audio_url === (ph.audio_url || null)
      phrases.set(id, { id, text: ph.text || '', audio_url: ph.audio_url || null, kind: ph.kind || 'phrase', audio: same ? old.audio : null })
    })
    preloadAll()
  }

  let phraseLoad = null
  /** Fetch /api/voice/phrases once; retry every phraseRetryMs (up to phraseRetries times) while ready is false. */
  function init() {
    if (phraseLoad || !fetchPhrases) return phraseLoad
    let tries = 0
    const attempt = async () => {
      let res = null
      let giveUp = false
      try {
        res = await fetchPhrases()
      } catch (e) {
        giveUp = !!e && (e.status === 404 || e.status === 405) // backend without the route
      }
      if (res && res.phrases) setPhrases(res.phrases)
      if (res && res.ready) {
        setState({ phrasesReady: true })
        return true
      }
      tries += 1
      if (giveUp || tries > phraseRetries) return false
      await new Promise((r) => setT(r, phraseRetryMs))
      return attempt()
    }
    phraseLoad = attempt()
    return phraseLoad
  }

  const getPhrase = (id) => phrases.get(id) || null

  /** Play a preloaded phrase by id. Resolves false when unknown. Acks never fall back to the browser voice. */
  function playPhrase(id, opts = {}) {
    const ph = phrases.get(id)
    if (!ph || state.muted) return Promise.resolve(false)
    const kind = opts.kind || (ph.kind === 'ack' ? 'ack' : 'reply')
    if (kind === 'ack' && !ph.audio_url) return Promise.resolve(false)
    if (!ph.audio_url && !ph.text) return Promise.resolve(false)
    const norm = { key: null, text: ph.text, url: ph.audio_url, b64: null, lang: 'hi' }
    const item = makeItem(kind, norm, { audioEl: ph.audio || null, phraseId: id })
    enqueue(item)
    return item.done
  }

  /**
   * The instant acknowledgement. Call it the moment recording stops:
   *   const ack = engine.ack()      // plays "ji" / "haan ji" / "ek second" now
   *   ... await request ...
   *   ack.settle()                  // request answered; a very fast answer cuts the ack short
   * Never repeats the previous ack. Returns a token (always safe to call methods on).
   */
  function ack() {
    const startedAt = now()
    const token = { id: null, startedAt, item: null, settle: () => {}, cancel: () => {} }
    if (state.muted) return token
    newTurn() // a new utterance began: the old reply stops here, in a short fade (even if no ack can be played)
    const id = pickAck(lastAck, random, ACK_IDS.filter((a) => phrases.get(a)?.audio_url))
    const ph = id && phrases.get(id)
    if (!ph || !ph.audio_url) return token
    lastAck = id
    if (current?.item.kind === 'money' || queue.some((it) => it.kind === 'money')) return token // never talk over money
    const item = makeItem('ack', { key: null, text: ph.text, url: ph.audio_url, b64: null, lang: 'hi' }, { audioEl: ph.audio || null, phraseId: id })
    token.id = id
    token.item = item
    const cancelAck = () => {
      if (current && current.item === item) current.stop(fadeMs)
      else {
        const at = queue.indexOf(item)
        if (at >= 0) {
          queue.splice(at, 1)
          settle(item, false)
        }
      }
    }
    token.cancel = cancelAck
    // A reply that comes back in under ackFastMs is not talked over: the short ack is dropped / faded out.
    token.settle = () => {
      if (now() - startedAt < ackFastMs) cancelAck()
    }
    enqueue(item)
    return token
  }

  // ----- public: unlock -------------------------------------------------------------------------------------

  function unlock() {
    interacted = true
    try {
      unlockHook?.()
    } catch {
      /* ignore */
    }
    setState({ unlocked: true })
    preloadAll()
  }
  /** First user gesture seen (no sound needed): start warming the audio cache. */
  function markInteracted() {
    interacted = true
    preloadAll()
  }

  return {
    speak,
    speechReady,
    hasPending,
    newTurn,
    duck: newTurn,
    cancel,
    setMuted,
    init,
    setPhrases,
    getPhrase,
    playPhrase,
    ack,
    unlock,
    markInteracted,
    setBlocked: () => setState({ unlocked: false }),
    getState: () => ({ ...state }),
    subscribe: (fn) => {
      listeners.add(fn)
      return () => listeners.delete(fn)
    },
    _debug: () => ({ queue: queue.length, pending: [...pending.keys()], current: current?.item?.kind || null, version }),
  }
}
