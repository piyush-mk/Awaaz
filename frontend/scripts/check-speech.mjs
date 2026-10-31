// Speech manager checks. Part 1 drives the engine (src/lib/speechCore.js) with a fake Audio, a fake
// speechSynthesis and a fake clock: queue, ducking, de-duplication, the 3.5 s pending timeout, acks, money.
// Part 2 (only when a backend answers) checks that the real /api/agent/utterance and /api/voice/phrases replies
// are understood whether or not the new `speech` / `timings` fields are present.
//
//   node frontend/scripts/check-speech.mjs [http://localhost:8000]
//   # part 2 against a scratch database:
//   cd backend && DATABASE_URL=sqlite:////tmp/speech-check.sqlite DEMO_MODE=on .venv/bin/uvicorn main:app --port 8000
//
// Real audio output cannot be heard here; this proves the logic, not the loudspeaker.

import { ACK_IDS, createSpeechEngine, normalizeSpeech, pickAck } from '../src/lib/speechCore.js'
import { timingsText } from '../src/lib/format.js'

let passed = 0
let failed = 0
const failures = []
async function test(name, fn) {
  try {
    await fn()
    passed += 1
    console.log(`PASS  ${name}`)
  } catch (e) {
    failed += 1
    failures.push(name)
    console.log(`FAIL  ${name}\n      ${e.message}`)
  }
}
const ok = (c, m) => {
  if (!c) throw new Error(m || 'assertion failed')
}
const eq = (a, b, m) => {
  if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error(`${m || 'not equal'}: got ${JSON.stringify(a)}, want ${JSON.stringify(b)}`)
}
const tick = async (n = 6) => {
  for (let i = 0; i < n; i += 1) await Promise.resolve()
}

// ----- fakes ---------------------------------------------------------------------------------------------------

function makeWorld(opts = {}) {
  let t = 0
  let seq = 0
  const timers = new Map()
  const log = []
  const audios = []
  let playingNow = 0
  let maxOverlap = 0
  const clock = {
    setTimeout: (fn, ms) => {
      seq += 1
      timers.set(seq, { at: t + ms, fn, seq })
      return seq
    },
    clearTimeout: (id) => timers.delete(id),
    now: () => t,
  }
  async function advance(ms) {
    const end = t + ms
    await tick()
    for (;;) {
      const due = [...timers.values()].filter((x) => x.at <= end).sort((a, b) => a.at - b.at || a.seq - b.seq)[0]
      if (!due) break
      timers.delete(due.seq)
      t = due.at
      due.fn()
      await tick()
    }
    t = end
    await tick()
  }

  class FakeAudio {
    constructor(url) {
      this.url = url
      this._volume = 1
      this.currentTime = 0
      this.onended = null
      this.onerror = null
      this.playing = false
      this.timer = null
      audios.push(this)
    }
    get volume() {
      return this._volume
    }
    set volume(v) {
      this._volume = v
      if (this.playing) log.push(`vol ${this.url} ${v.toFixed(2)}`)
    }
    load() {
      log.push(`load ${this.url}`)
    }
    play() {
      if (opts.blockAudio) {
        const e = new Error('blocked')
        e.name = 'NotAllowedError'
        return Promise.reject(e)
      }
      if (opts.failAudio && opts.failAudio(this.url)) return Promise.reject(new Error('decode error'))
      log.push(`play ${this.url}`)
      this.playing = true
      playingNow += 1
      maxOverlap = Math.max(maxOverlap, playingNow)
      const dur = (opts.durations && opts.durations[this.url]) || 1000
      this.timer = clock.setTimeout(() => {
        this.stopPlaying()
        log.push(`end ${this.url}`)
        this.onended?.()
      }, dur)
      return Promise.resolve()
    }
    stopPlaying() {
      if (this.playing) {
        this.playing = false
        playingNow -= 1
      }
      clock.clearTimeout(this.timer)
    }
    pause() {
      if (this.playing) log.push(`pause ${this.url}`)
      this.stopPlaying()
    }
  }

  const synthLog = []
  const synth = {
    cancel: () => {
      synthLog.push('cancel')
      if (synth.current) {
        const u = synth.current
        synth.current = null
        clock.clearTimeout(synth.timer)
        playingNow -= 1
        u.onend?.()
      }
    },
    getVoices: () => [{ lang: 'hi-IN', name: 'hi' }],
    speak: (u) => {
      log.push(`synth ${u.text}`)
      synthLog.push(u.text)
      synth.current = u
      playingNow += 1
      maxOverlap = Math.max(maxOverlap, playingNow)
      synth.timer = clock.setTimeout(() => {
        if (synth.current === u) {
          synth.current = null
          playingNow -= 1
          u.onend?.()
        }
      }, 800)
    },
  }
  class FakeUtterance {
    constructor(text) {
      this.text = text
    }
  }

  let blocked = 0
  const fetchCalls = []
  const engine = createSpeechEngine({
    createAudio: (url) => new FakeAudio(url),
    synth,
    Utterance: FakeUtterance,
    ...clock,
    random: opts.random || Math.random,
    unlocked: opts.unlocked ?? true,
    onBlocked: () => {
      blocked += 1
    },
    fetchPhrases: opts.fetchPhrases ? () => (fetchCalls.push(clock.now()), opts.fetchPhrases(fetchCalls.length)) : null,
    ...(opts.engine || {}),
  })
  return {
    engine,
    log,
    audios,
    synthLog,
    advance,
    clock,
    fetchCalls,
    get maxOverlap() {
      return maxOverlap
    },
    get blocked() {
      return blocked
    },
    plays: () => log.filter((l) => l.startsWith('play ')).map((l) => l.slice(5)),
    voices: () => log.filter((l) => l.startsWith('play ') || l.startsWith('synth ')),
  }
}

const PHRASES = {
  ack_ji: { text: 'Ji', audio_url: '/api/voice/phrase/ack_ji.mp3', kind: 'ack' },
  ack_haan_ji: { text: 'Haan ji', audio_url: '/api/voice/phrase/ack_haan_ji.mp3', kind: 'ack' },
  ack_ek_second: { text: 'Ek second', audio_url: '/api/voice/phrase/ack_ek_second.mp3', kind: 'ack' },
  done_ho_gaya: { text: 'Ho gaya', audio_url: '/api/voice/phrase/done_ho_gaya.mp3', kind: 'done' },
  unclear_dobara: { text: 'Dobara bolein', audio_url: null, kind: 'error' },
}

// ----- part 1: engine ------------------------------------------------------------------------------------------

await test('normalizeSpeech: string, speech object, legacy reply, absent fields', () => {
  eq(normalizeSpeech('namaste').text, 'namaste')
  const withSpeech = normalizeSpeech({ spoken_text: 'old', audio_url: '/old.mp3', speech: { text: 'new', pending: true, key: 7, audio_url: null, ack: 'ack_ji' } })
  eq([withSpeech.text, withSpeech.url, withSpeech.pending, withSpeech.key], ['new', null, true, '7'], 'speech wins; explicit null audio_url is respected')
  const ready = normalizeSpeech({ speech: { text: 'x', pending: false, audio_url: '/a.mp3', key: 'k' } })
  eq([ready.url, ready.pending], ['/a.mp3', false])
  const legacy = normalizeSpeech({ spoken_text: 'Kul 294', audio_url: '/l.mp3' })
  eq([legacy.text, legacy.url, legacy.pending, legacy.key], ['Kul 294', '/l.mp3', false, null], 'no speech field at all')
  const nullable = normalizeSpeech({ speech: { text: 't', pending: null, key: null, audio_url: null, ack: null }, timings: null })
  eq([nullable.pending, nullable.key, nullable.url], [false, null, null], 'null fields')
  eq(normalizeSpeech({}).text, '')
  eq(normalizeSpeech({ message_hi: 'Brief' }).text, 'Brief')
  eq(normalizeSpeech('x', { audioUrl: '/o.mp3' }).url, '/o.mp3', 'legacy opts.audioUrl')
})

await test('timingsText: present, partial, null, missing', () => {
  eq(timingsText({ stt_ms: 900, parse_ms: 20, llm_ms: null, total_ms: 1100 }), 'stt 0.9 s, parse 0.02 s, total 1.1 s')
  eq(timingsText(null), '')
  eq(timingsText(undefined), '')
  eq(timingsText({ stt_ms: null, parse_ms: null }), '')
})

await test('pickAck never repeats the previous ack', () => {
  let last = null
  for (let i = 0; i < 300; i += 1) {
    const next = pickAck(last)
    ok(ACK_IDS.includes(next), 'known id')
    ok(next !== last, `repeated ${next}`)
    last = next
  }
  eq(pickAck(null, () => 0), ACK_IDS[0])
  eq(pickAck('ack_ji', () => 0.999), ACK_IDS[2])
})

await test('plays audio_url when not pending, resolves true, one voice only', async () => {
  const w = makeWorld()
  const p = w.engine.speak({ spoken_text: 'Kul 294', speech: { text: 'Kul 294', key: 'k1', pending: false, audio_url: '/a1.mp3' } })
  await w.advance(10)
  eq(w.voices(), ['play /a1.mp3'], 'audio, not browser voice')
  await w.advance(1000)
  eq(await p, true)
  eq(w.synthLog, [], 'browser voice never used when server audio plays')
})

await test('audio_url null and not pending -> browser voice speaks the text', async () => {
  const w = makeWorld()
  w.engine.speak({ speech: { text: 'Theek hai', key: 'k2', pending: false, audio_url: null } })
  await w.advance(10)
  eq(w.voices(), ['synth Theek hai'])
})

await test('no speech field at all (old backend): spoken_text + audio_url still play', async () => {
  const w = makeWorld()
  w.engine.speak({ spoken_text: 'Ho gaya', audio_url: '/old.mp3' })
  await w.advance(10)
  eq(w.voices(), ['play /old.mp3'])
  const w2 = makeWorld()
  w2.engine.speak({ spoken_text: 'Sirf text' })
  await w2.advance(10)
  eq(w2.voices(), ['synth Sirf text'])
})

await test('lines queue and never overlap; a newer reply ducks the older one with a fade', async () => {
  const w = makeWorld()
  w.engine.speak({ speech: { text: 'A', key: 'A', audio_url: '/a.mp3' } })
  await w.advance(200)
  w.engine.speak({ speech: { text: 'B', key: 'B', audio_url: '/b.mp3' } })
  await w.advance(500)
  eq(w.voices(), ['play /a.mp3', 'play /b.mp3'])
  const iA = w.log.indexOf('play /a.mp3')
  const iPause = w.log.indexOf('pause /a.mp3')
  const iB = w.log.indexOf('play /b.mp3')
  ok(iA < iPause && iPause < iB, `A must be paused before B starts: ${w.log.join(' | ')}`)
  const fades = w.log.filter((l) => l.startsWith('vol /a.mp3')).map((l) => Number(l.split(' ')[2]))
  ok(fades.length >= 3, 'volume ramp, not an abrupt cut')
  ok(fades.every((v, i) => i === 0 || v <= fades[i - 1]) && fades.at(-1) === 0, 'volume ramps down to 0')
  eq(w.maxOverlap, 1, 'never two voices at once')
})

await test('a reply that arrives while an older reply is only queued drops the older one', async () => {
  const w = makeWorld()
  w.engine.speak({ speech: { text: 'first', key: 'q1', audio_url: '/q1.mp3' } })
  w.engine.speak({ speech: { text: 'second', key: 'q2', audio_url: '/q2.mp3' } })
  w.engine.speak({ speech: { text: 'third', key: 'q3', audio_url: '/q3.mp3' } })
  await w.advance(2000)
  ok(!w.plays().includes('/q2.mp3'), 'superseded reply is never spoken')
  ok(w.plays().at(-1) === '/q3.mp3', 'newest reply is spoken last')
  eq(w.maxOverlap, 1)
})

await test('same key is spoken once (replayed speak, HTTP + SSE)', async () => {
  const w = makeWorld()
  const input = { speech: { text: 'Kul 249', key: 'dup', audio_url: '/d.mp3' } }
  w.engine.speak(input)
  await w.advance(3000)
  const again = await w.engine.speak(input)
  eq(again, false)
  eq(await w.engine.speechReady({ key: 'dup', audio_url: '/d.mp3', text: 'Kul 249' }), false)
  await w.advance(3000)
  eq(w.plays(), ['/d.mp3'])
})

await test('HTTP keyed reply + SSE utterance without a key (same words) are spoken once', async () => {
  const w = makeWorld()
  w.engine.speak({ speech: { text: 'Do maggi, kul 24', key: 'u9', pending: true, audio_url: null } })
  w.engine.speak({ spoken_text: 'Do maggi, kul 24', audio_url: null }) // SSE `utterance` without speech
  await w.advance(100)
  eq(w.voices(), [], 'still waiting for the audio; the keyless duplicate did not speak')
  w.engine.speechReady({ key: 'u9', audio_url: '/u9.mp3', text: 'Do maggi, kul 24' })
  await w.advance(1500)
  eq(w.voices(), ['play /u9.mp3'])
})

await test('different keys with the same words are two replies', async () => {
  const w = makeWorld()
  w.engine.speak({ speech: { text: 'Samajh nahi aaya', key: 'e1', audio_url: '/e.mp3' } })
  await w.advance(2000)
  w.engine.speak({ speech: { text: 'Samajh nahi aaya', key: 'e2', audio_url: '/e.mp3' } })
  await w.advance(2000)
  eq(w.plays().length, 2)
})

await test('pending: silent until speech_ready, then the server audio (not the browser voice)', async () => {
  const w = makeWorld()
  w.engine.speak({ speech: { text: 'Kul 294', key: 'p1', pending: true, audio_url: null } })
  await w.advance(2000)
  eq(w.voices(), [], 'nothing spoken yet')
  ok(w.engine.hasPending('p1'))
  w.engine.speechReady({ session_id: 's', key: 'p1', audio_url: '/p1.mp3', text: 'Kul 294', source: 'sarvam' })
  await w.advance(1500)
  eq(w.voices(), ['play /p1.mp3'])
  eq(w.synthLog, [])
  ok(!w.engine.hasPending('p1'))
})

await test('pending: speech_ready with audio_url null -> browser voice of the event text', async () => {
  const w = makeWorld()
  w.engine.speak({ speech: { text: 'old text', key: 'p2', pending: true, audio_url: null } })
  w.engine.speechReady({ key: 'p2', audio_url: null, text: 'Kul 100', source: 'browser' })
  await w.advance(900)
  eq(w.voices(), ['synth Kul 100'])
})

await test('pending: 3.5 s timeout -> browser voice speaks once; a late speech_ready is ignored', async () => {
  const w = makeWorld()
  w.engine.speak({ speech: { text: 'Kul 294 rupaye', key: 'p3', pending: true, audio_url: null } })
  await w.advance(3499)
  eq(w.voices(), [], 'not before 3.5 s')
  await w.advance(2)
  eq(w.voices(), ['synth Kul 294 rupaye'], 'fallback exactly at the timeout')
  await w.advance(2000)
  const late = await w.engine.speechReady({ key: 'p3', audio_url: '/late.mp3', text: 'Kul 294 rupaye' })
  eq(late, false)
  await w.advance(2000)
  eq(w.voices(), ['synth Kul 294 rupaye'], 'server audio and browser voice are never both used')
})

await test('speech_ready before the HTTP reply (event beat the response): spoken once', async () => {
  const w = makeWorld()
  w.engine.speechReady({ session_id: 's', key: 'early', audio_url: '/early.mp3', text: 'Ho gaya' })
  w.engine.speak({ speech: { text: 'Ho gaya', key: 'early', pending: true, audio_url: null } })
  await w.advance(4500)
  eq(w.voices(), ['play /early.mp3'])
})

await test('speech_ready for a stale key (superseded by a new turn) is ignored', async () => {
  const w = makeWorld()
  w.engine.speak({ speech: { text: 'old reply', key: 'old', pending: true, audio_url: null } })
  w.engine.newTurn() // the merchant started talking again
  await w.advance(100)
  eq(await w.engine.speechReady({ key: 'old', audio_url: '/old.mp3', text: 'old reply' }), false)
  await w.advance(4000)
  eq(w.voices(), [], 'no stale reply, and no timeout fallback for it')
})

await test('an older pending reply is dropped when a newer reply is already waiting', async () => {
  const w = makeWorld()
  w.engine.speak({ speech: { text: 'one', key: 'n1', pending: true, audio_url: null } })
  w.engine.speak({ speech: { text: 'two', key: 'n2', pending: true, audio_url: null } })
  w.engine.speechReady({ key: 'n1', audio_url: '/n1.mp3', text: 'one' })
  w.engine.speechReady({ key: 'n2', audio_url: '/n2.mp3', text: 'two' })
  await w.advance(3000)
  eq(w.plays(), ['/n2.mp3'])
})

await test('money (payment_received) is never dropped or cut by a newer reply', async () => {
  const w = makeWorld({ durations: { '/pay.mp3': 2000 } })
  w.engine.speak({ speech: { text: 'reply', key: 'r', audio_url: '/r.mp3' } })
  await w.advance(100)
  const pay = w.engine.speak({ spoken_text: '249 rupaye mile', audio_url: '/pay.mp3' }, { kind: 'money', key: 'pay:1' })
  await w.advance(100)
  w.engine.speak({ speech: { text: 'next reply', key: 'r2', audio_url: '/r2.mp3' } })
  w.engine.newTurn() // the mic is pressed while money plays
  await w.advance(100)
  ok(!w.log.includes('pause /pay.mp3'), 'money was not paused')
  await w.advance(5000)
  eq(await pay, true)
  ok(w.plays().includes('/pay.mp3'), 'payment announced')
  ok(w.log.indexOf('pause /r.mp3') < w.log.indexOf('play /pay.mp3'), 'older reply faded before money')
  eq(w.maxOverlap, 1)
  // the same payment delivered twice (HTTP + SSE) is spoken once, but a different order is spoken
  eq(await w.engine.speak({ spoken_text: '249 rupaye mile', audio_url: '/pay.mp3' }, { kind: 'money', key: 'pay:1' }), false)
  w.engine.speak({ spoken_text: '100 rupaye mile', audio_url: '/pay2.mp3' }, { kind: 'money', key: 'pay:2' })
  await w.advance(1500)
  ok(w.plays().includes('/pay2.mp3'))
})

await test('money waits its turn behind other money (queue, no overlap)', async () => {
  const w = makeWorld({ durations: { '/m1.mp3': 1500, '/m2.mp3': 1500 } })
  w.engine.speak({ spoken_text: 'm1', audio_url: '/m1.mp3' }, { kind: 'money', key: 'm1' })
  w.engine.speak({ spoken_text: 'm2', audio_url: '/m2.mp3' }, { kind: 'money', key: 'm2' })
  await w.advance(5000)
  eq(w.plays(), ['/m1.mp3', '/m2.mp3'])
  eq(w.maxOverlap, 1)
})

await test('audio that cannot start falls back to the browser voice once; blocked autoplay is reported', async () => {
  const w = makeWorld({ failAudio: (u) => u === '/bad.mp3' })
  w.engine.speak({ speech: { text: 'Bad file', key: 'b1', audio_url: '/bad.mp3' } })
  await w.advance(1000)
  eq(w.voices(), ['synth Bad file'])
  const blocked = makeWorld({ blockAudio: true })
  blocked.engine.speak({ speech: { text: 'Sound off', key: 'b2', audio_url: '/x.mp3' } })
  await blocked.advance(1000)
  eq(blocked.blocked, 1, 'onBlocked called so the page can show Tap to enable sound')
})

await test('muted engine speaks nothing; setMuted(true) cuts what is playing', async () => {
  const w = makeWorld()
  w.engine.speak({ speech: { text: 'x', key: 'mu1', audio_url: '/mu1.mp3' } })
  await w.advance(100)
  w.engine.setMuted(true)
  await w.advance(100)
  ok(w.log.includes('pause /mu1.mp3'))
  eq(await w.engine.speak('anything'), false)
  eq(w.synthLog, [])
})

await test('speaking state flips true while something plays and false 0 ms after the queue drains', async () => {
  const w = makeWorld()
  const states = []
  w.engine.subscribe((s) => states.push(s.speaking))
  w.engine.speak({ speech: { text: 'a', key: 'sp1', audio_url: '/sp1.mp3' } })
  await w.advance(100)
  eq(w.engine.getState().speaking, true)
  await w.advance(1500)
  eq(w.engine.getState().speaking, false)
  eq(states, [true, false])
})

await test('phrases: fetched once, retried every 10 s up to 6 times while not ready, then stop', async () => {
  const w = makeWorld({ fetchPhrases: async () => ({ ready: false, phrases: {} }) })
  const done = w.engine.init()
  await w.advance(10000 * 8)
  eq(await done, false)
  eq(w.fetchCalls.length, 7, 'first fetch + 6 retries')
  eq(w.fetchCalls.slice(1).map((t, i) => t - w.fetchCalls[i]), [10000, 10000, 10000, 10000, 10000, 10000])
})

await test('phrases: retry stops as soon as ready; a backend without the route is tried once', async () => {
  const w = makeWorld({ fetchPhrases: async (n) => (n < 3 ? { ready: false, phrases: { ack_ji: { text: 'Ji', audio_url: null, kind: 'ack' } } } : { ready: true, phrases: PHRASES }) })
  const done = w.engine.init()
  await w.advance(40000)
  eq(await done, true)
  eq(w.fetchCalls.length, 3)
  eq(w.engine.getState().phrasesReady, true)
  const old = makeWorld({ fetchPhrases: async () => Promise.reject(Object.assign(new Error('nope'), { status: 404 })) })
  await old.engine.init()
  await old.advance(80000)
  eq(old.fetchCalls.length, 1, '404 = old backend: no retry storm')
})

await test('phrases are preloaded after the first interaction, not before', async () => {
  const w = makeWorld({ unlocked: false })
  w.engine.setPhrases(PHRASES)
  eq(w.audios.length, 0, 'no audio elements before a user gesture')
  w.engine.markInteracted()
  eq(w.audios.length, 4, 'one element per phrase that has an audio_url')
  ok(w.log.filter((l) => l.startsWith('load ')).length === 4)
  w.engine.setPhrases(PHRASES) // a refetch does not duplicate elements
  eq(w.audios.length, 4)
})

await test('ack: plays a preloaded phrase instantly, never the same one twice running', async () => {
  const w = makeWorld({ durations: { '/api/voice/phrase/ack_ji.mp3': 500, '/api/voice/phrase/ack_haan_ji.mp3': 500, '/api/voice/phrase/ack_ek_second.mp3': 500 } })
  w.engine.setPhrases(PHRASES)
  const seq = []
  for (let i = 0; i < 12; i += 1) {
    const token = w.engine.ack()
    seq.push(token.id)
    await w.advance(700)
  }
  ok(seq.every((id, i) => id && (i === 0 || id !== seq[i - 1])), `ack repeated: ${seq.join(',')}`)
  eq(w.audios.length, 4, 'ack audio elements are reused, never recreated per play')
  ok(w.plays().length === 12)
})

await test('ack: a reply that returns in under 250 ms cuts the ack; a slower one lets it finish', async () => {
  const w = makeWorld({ durations: { '/api/voice/phrase/ack_ji.mp3': 600, '/api/voice/phrase/ack_haan_ji.mp3': 600, '/api/voice/phrase/ack_ek_second.mp3': 600 }, random: () => 0 })
  w.engine.setPhrases(PHRASES)
  const fast = w.engine.ack()
  await w.advance(100)
  fast.settle() // request answered after 100 ms
  await w.advance(300)
  ok(w.log.some((l) => l.startsWith('pause ')), 'fast reply: ack faded out')
  const w2 = makeWorld({ durations: { '/api/voice/phrase/ack_ji.mp3': 600 }, random: () => 0 })
  w2.engine.setPhrases(PHRASES)
  const slow = w2.engine.ack()
  await w2.advance(400)
  slow.settle() // request answered after 400 ms
  await w2.advance(400)
  ok(!w2.log.some((l) => l.startsWith('pause ')), 'slow reply: ack plays to its end')
  ok(w2.log.some((l) => l.startsWith('end ')))
})

await test('ack: the reply that follows waits for the ack (no overlap); ack is skipped over money', async () => {
  const w = makeWorld({ durations: { '/api/voice/phrase/ack_ji.mp3': 500, '/r.mp3': 800 }, random: () => 0 })
  w.engine.setPhrases(PHRASES)
  w.engine.ack()
  await w.advance(200)
  w.engine.speak({ speech: { text: 'reply', key: 'ar', audio_url: '/r.mp3' } })
  await w.advance(3000)
  eq(w.plays(), ['/api/voice/phrase/ack_ji.mp3', '/r.mp3'])
  eq(w.maxOverlap, 1)
  const m = makeWorld({ durations: { '/pay.mp3': 2000 } })
  m.engine.setPhrases(PHRASES)
  m.engine.speak({ spoken_text: 'paid', audio_url: '/pay.mp3' }, { kind: 'money', key: 'pm' })
  await m.advance(100)
  const t = m.engine.ack()
  eq(t.id, null, 'no ack over a payment announcement')
})

await test('ack: new utterance fades the older reply out first (short ducking), then the ack plays', async () => {
  const w = makeWorld({ random: () => 0 })
  w.engine.setPhrases(PHRASES)
  w.engine.speak({ speech: { text: 'long reply', key: 'lr', audio_url: '/lr.mp3' } }, { })
  await w.advance(300)
  w.engine.ack()
  await w.advance(600)
  const i1 = w.log.indexOf('pause /lr.mp3')
  const i2 = w.log.indexOf('play /api/voice/phrase/ack_ji.mp3')
  ok(i1 > 0 && i2 > i1, `older reply faded before the ack: ${w.log.join(' | ')}`)
  eq(w.maxOverlap, 1)
})

await test('ack without phrases (old backend / not ready): harmless no-op token', async () => {
  const w = makeWorld()
  const t = w.engine.ack()
  eq(t.id, null)
  t.settle()
  t.cancel()
  eq(w.voices(), [])
})

await test('playPhrase: preloaded id plays; unknown id and audio-less ack are skipped silently', async () => {
  const w = makeWorld()
  w.engine.setPhrases(PHRASES)
  eq(await w.engine.playPhrase('nope'), false)
  const p = w.engine.playPhrase('done_ho_gaya')
  await w.advance(1500)
  eq(await p, true)
  const noAudio = w.engine.playPhrase('unclear_dobara') // kind error, no audio_url: browser voice reads the text
  await w.advance(1000)
  eq(w.synthLog, ['Dobara bolein'])
  void noAudio
})

await test('legacy interrupt option and keyless dedupe window (4 s)', async () => {
  const w = makeWorld()
  w.engine.speak('Pehli baat')
  await w.advance(100)
  eq(await w.engine.speak('Pehli baat'), false, 'same words within 4 s')
  await w.advance(5000)
  w.engine.speak('Pehli baat')
  await w.advance(100)
  eq(w.synthLog.length, 2, 'after 4 s the same words are a new line')
  w.engine.speak('Doosri baat', { interrupt: true })
  await w.advance(100)
  eq(w.maxOverlap, 1)
})

// ----- part 2: live backend --------------------------------------------------------------------------------------

const BASE = process.argv[2] || process.env.API_BASE || 'http://localhost:8000'
let live = false
try {
  const r = await fetch(`${BASE}/api/admin/status`, { signal: AbortSignal.timeout(2000) })
  live = r.ok
} catch {
  live = false
}

if (!live) {
  console.log(`SKIP  live backend checks (nothing answering on ${BASE})`)
} else {
  globalThis.__AWAAZ_API_BASE__ = BASE
  const { sendUtterance, getStatus } = await import('../src/api/client.js')
  const sid = `speech-${Math.random().toString(36).slice(2, 8)}`
  const status = await getStatus()
  console.log(`      backend up, demo_mode=${status.demo_mode?.effective ?? '?'}`)

  await test('live: /api/voice/phrases either serves the contract or is absent (404)', async () => {
    const r = await fetch(`${BASE}/api/voice/phrases`)
    if (r.status === 404) return console.log('      (route absent: client treats as old backend)')
    ok(r.ok, `status ${r.status}`)
    const body = await r.json()
    ok(typeof body.ready === 'boolean', 'ready is boolean')
    ok(body.phrases && typeof body.phrases === 'object', 'phrases object')
    for (const [id, ph] of Object.entries(body.phrases)) {
      ok(typeof ph.text === 'string' && ph.text, `${id}.text`)
      ok(ph.audio_url === null || typeof ph.audio_url === 'string', `${id}.audio_url null|string`)
      ok(typeof ph.kind === 'string', `${id}.kind`)
    }
    for (const id of ACK_IDS) if (body.ready) ok(body.phrases[id], `ready phrases include ${id}`)
    const w = makeWorld()
    w.engine.setPhrases(body.phrases)
    w.engine.markInteracted()
    console.log(`      ${Object.keys(body.phrases).length} phrases, ready=${body.ready}`)
  })

  await test('live: utterance reply is understood with or without speech/timings', async () => {
    const t0 = Date.now()
    const res = await sendUtterance({ text: 'do maggi ek surf excel chaar colgate', sessionId: sid })
    const ms = Date.now() - t0
    ok(res.cart && Array.isArray(res.cart.lines) && res.cart.lines.length >= 3, 'cart in the HTTP reply (rendered immediately)')
    const hasSpeech = res.speech && typeof res.speech === 'object'
    const hasTimings = res.timings && typeof res.timings === 'object'
    console.log(`      http ${ms} ms, speech: ${hasSpeech ? JSON.stringify(res.speech) : 'absent'}, timings: ${hasTimings ? JSON.stringify(res.timings) : 'absent'}`)
    const norm = normalizeSpeech(res)
    ok(norm.text, 'there is always text to speak')
    if (hasSpeech) {
      ok(typeof res.speech.text === 'string', 'speech.text')
      ok(res.speech.pending === undefined || res.speech.pending === null || typeof res.speech.pending === 'boolean', 'speech.pending boolean')
      if (res.speech.pending) {
        ok(res.speech.key, 'a pending reply carries a key so speech_ready can find it')
        ok(!res.speech.audio_url, 'pending means no audio yet')
      }
    }
    if (hasTimings) {
      for (const k of ['stt_ms', 'parse_ms', 'llm_ms', 'total_ms']) ok(res.timings[k] === null || res.timings[k] === undefined || typeof res.timings[k] === 'number', `timings.${k}`)
      ok(timingsText(res.timings) !== '' || Object.values(res.timings).every((v) => v == null), 'tooltip text')
    }
    // drive the real reply through the engine: it must produce exactly one voice
    const w = makeWorld()
    const p = w.engine.speak(res)
    await w.advance(res.speech?.pending ? 3600 : 100)
    await w.advance(2000)
    eq(w.voices().length, 1, `exactly one voice for one reply: ${w.voices().join(' ; ')}`)
    void p
  })

  await test('live: a pending reply is finished by the SSE speech_ready event (if the backend emits it)', async () => {
    const events = []
    const ac = new AbortController()
    ;(async () => {
      try {
        const res = await fetch(`${BASE}/api/events?channel=store`, { signal: ac.signal })
        const dec = new TextDecoder()
        let buf = ''
        for await (const chunk of res.body) {
          buf += dec.decode(chunk, { stream: true })
          let i
          while ((i = buf.indexOf('\n\n')) >= 0) {
            const block = buf.slice(0, i)
            buf = buf.slice(i + 2)
            const ev = /event: (.*)/.exec(block)?.[1]
            const data = /data: (.*)/.exec(block)?.[1]
            if (ev && data) events.push({ ev, data: JSON.parse(data) })
          }
        }
      } catch {
        /* aborted */
      }
    })()
    await new Promise((r) => setTimeout(r, 400))
    const res = await sendUtterance({ text: 'ek patanjali shahad do colgate', sessionId: `${sid}-2` })
    const w = makeWorld()
    w.engine.speak(res)
    if (res.speech?.pending) {
      let ev = null
      for (let i = 0; i < 40 && !ev; i += 1) {
        ev = events.find((e) => e.ev === 'speech_ready' && e.data.key === res.speech.key)
        if (!ev) await new Promise((r) => setTimeout(r, 100))
      }
      ac.abort()
      ok(ev, 'speech_ready arrived for the pending key within 4 s')
      ok(ev.data.audio_url === null || typeof ev.data.audio_url === 'string', 'audio_url null|string')
      w.engine.speechReady(ev.data)
      await w.advance(2000)
      eq(w.voices().length, 1)
      console.log(`      speech_ready: ${JSON.stringify(ev.data)}`)
    } else {
      ac.abort()
      console.log('      (reply was not pending: nothing to wait for)')
    }
  })
}

console.log(`\n${passed} passed, ${failed} failed${failures.length ? `: ${failures.join('; ')}` : ''}`)
process.exit(failed ? 1 : 0)
