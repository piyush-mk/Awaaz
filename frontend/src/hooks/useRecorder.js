import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Microphone recording for the merchant app.
 *
 *  - Push-to-talk:   startPTT() / stopPTT()  (the Mic orb calls these on press / release / tap)
 *  - Hands-free:     startHandsFree() / stopHandsFree()  ("Sun raha hai"): an energy-based voice activity
 *    detector on a Web Audio AnalyserNode cuts the stream into utterances. No WASM, no dependency.
 *
 * Every finished utterance is handed to `onAudio(blob, { filename, mode, durationMs })`.
 *
 * VAD rules (all overridable through `vad`):
 *   speech starts after ~100 ms above the threshold; threshold = max(minRms, noiseFloor * noiseMult)
 *   an utterance ends after 700 ms of trailing silence, or at 12 s
 *   utterances with less than 400 ms of actual speech are dropped (coughs, door slams)
 * A MediaRecorder runs continuously in hands-free mode and is recycled every ~2.5 s while idle, so the first
 * syllable is never clipped (pre-roll) and each blob is a complete, decodable file.
 */

const VAD_DEFAULTS = {
  minRms: 0.025,
  noiseMult: 3,
  onsetMs: 100,
  trailingSilenceMs: 700,
  minSpeechMs: 400,
  maxUtteranceMs: 12000,
  recycleMs: 2500,
  tickMs: 50,
}
const PTT_MAX_MS = 15000

function pickMime() {
  if (typeof window === 'undefined' || !window.MediaRecorder) return ''
  const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus']
  return candidates.find((m) => window.MediaRecorder.isTypeSupported?.(m)) || ''
}

function extFor(mime) {
  if (mime.includes('mp4')) return 'm4a'
  if (mime.includes('ogg')) return 'ogg'
  return 'webm'
}

export function recorderSupported() {
  return (
    typeof navigator !== 'undefined' &&
    !!navigator.mediaDevices?.getUserMedia &&
    typeof window !== 'undefined' &&
    !!window.MediaRecorder
  )
}

export default function useRecorder({ onAudio, vad } = {}) {
  const [mode, setMode] = useState('idle') // idle | ptt | handsfree
  const [phase, setPhase] = useState('idle') // idle | listening | speech | recording
  const [level, setLevel] = useState(0)
  const [error, setError] = useState(null)

  const onAudioRef = useRef(onAudio)
  onAudioRef.current = onAudio
  const cfg = useRef({ ...VAD_DEFAULTS, ...(vad || {}) })

  // mutable engine state (never rendered)
  const E = useRef({
    stream: null,
    ctx: null,
    analyser: null,
    buf: null,
    mime: '',
    rec: null,
    chunks: [],
    recStart: 0,
    timer: null,
    pttTimer: null,
    mode: 'idle',
    suspended: false,
    inSpeech: false,
    loudRun: 0,
    voicedMs: 0,
    speechStart: 0,
    lastVoice: 0,
    lastTick: 0,
    noise: 0.01,
    pttWanted: false,
    pttStart: 0,
  })

  const deliver = useCallback((blob, meta) => {
    if (blob && blob.size > 800 && onAudioRef.current) onAudioRef.current(blob, meta)
  }, [])

  const ensureStream = useCallback(async () => {
    const e = E.current
    if (e.stream && e.stream.getTracks().some((t) => t.readyState === 'live')) return e.stream
    e.stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    })
    e.mime = pickMime()
    const Ctx = window.AudioContext || window.webkitAudioContext
    if (Ctx) {
      e.ctx = new Ctx()
      const src = e.ctx.createMediaStreamSource(e.stream)
      e.analyser = e.ctx.createAnalyser()
      e.analyser.fftSize = 1024
      src.connect(e.analyser)
      e.buf = new Float32Array(e.analyser.fftSize)
    }
    return e.stream
  }, [])

  const releaseStream = useCallback(() => {
    const e = E.current
    if (e.stream) e.stream.getTracks().forEach((t) => t.stop())
    if (e.ctx) e.ctx.close().catch(() => {})
    e.stream = null
    e.ctx = null
    e.analyser = null
  }, [])

  const startRecorder = useCallback(() => {
    const e = E.current
    if (!e.stream) return
    const chunks = []
    const rec = e.mime ? new MediaRecorder(e.stream, { mimeType: e.mime }) : new MediaRecorder(e.stream)
    rec.ondataavailable = (ev) => {
      if (ev.data && ev.data.size) chunks.push(ev.data)
    }
    rec.start()
    e.rec = rec
    e.chunks = chunks
    e.recStart = performance.now()
  }, [])

  /** Stop the current recorder and resolve with its blob; the engine has no recorder afterwards. */
  const stopRecorder = useCallback(() => {
    const e = E.current
    const rec = e.rec
    const chunks = e.chunks
    e.rec = null
    e.chunks = []
    if (!rec || rec.state === 'inactive') return Promise.resolve(null)
    return new Promise((resolve) => {
      rec.onstop = () => resolve(new Blob(chunks, { type: e.mime || rec.mimeType || 'audio/webm' }))
      try {
        rec.stop()
      } catch {
        resolve(null)
      }
    })
  }, [])

  const readRms = useCallback(() => {
    const e = E.current
    if (!e.analyser) return 0
    e.analyser.getFloatTimeDomainData(e.buf)
    let sum = 0
    for (let i = 0; i < e.buf.length; i += 1) sum += e.buf[i] * e.buf[i]
    return Math.sqrt(sum / e.buf.length)
  }, [])

  // ----- push-to-talk ------------------------------------------------------------------------------------

  const stopPTT = useCallback(async () => {
    const e = E.current
    e.pttWanted = false
    clearTimeout(e.pttTimer)
    if (e.mode !== 'ptt') return
    e.mode = 'idle'
    clearInterval(e.timer)
    setMode('idle')
    setPhase('idle')
    setLevel(0)
    const durationMs = performance.now() - e.pttStart
    const blob = await stopRecorder()
    releaseStream()
    if (blob && durationMs > 300) deliver(blob, { filename: `utterance.${extFor(blob.type)}`, mode: 'ptt', durationMs })
  }, [deliver, releaseStream, stopRecorder])

  /** Abandon a push-to-talk recording: nothing is sent. */
  const cancelPTT = useCallback(async () => {
    const e = E.current
    e.pttWanted = false
    clearTimeout(e.pttTimer)
    if (e.mode !== 'ptt') return
    e.mode = 'idle'
    clearInterval(e.timer)
    setMode('idle')
    setPhase('idle')
    setLevel(0)
    await stopRecorder()
    releaseStream()
  }, [releaseStream, stopRecorder])

  const startPTT = useCallback(async () => {
    const e = E.current
    if (e.mode !== 'idle') return false
    setError(null)
    e.pttWanted = true
    try {
      await ensureStream()
    } catch (err) {
      e.pttWanted = false
      setError(err.name === 'NotAllowedError' ? 'Microphone ki permission chahiye' : 'Microphone nahi mila')
      return false
    }
    if (!e.pttWanted) {
      releaseStream()
      return false
    }
    e.mode = 'ptt'
    setMode('ptt')
    setPhase('recording')
    startRecorder()
    e.pttStart = performance.now()
    e.timer = setInterval(() => setLevel(readRms()), 60)
    e.pttTimer = setTimeout(() => stopPTT(), PTT_MAX_MS)
    return true
  }, [ensureStream, readRms, releaseStream, startRecorder, stopPTT])

  // ----- hands-free (voice activity detection) -------------------------------------------------------------

  const finishUtterance = useCallback(async () => {
    const e = E.current
    const c = cfg.current
    const voiced = e.voicedMs
    const durationMs = performance.now() - e.speechStart
    e.inSpeech = false
    e.loudRun = 0
    e.voicedMs = 0
    setPhase('listening')
    const pending = stopRecorder()
    if (e.mode === 'handsfree') startRecorder()
    const blob = await pending
    if (blob && voiced >= c.minSpeechMs) {
      deliver(blob, { filename: `utterance.${extFor(blob.type)}`, mode: 'handsfree', durationMs })
    }
  }, [deliver, startRecorder, stopRecorder])

  const tick = useCallback(() => {
    const e = E.current
    const c = cfg.current
    const now = performance.now()
    const dt = e.lastTick ? now - e.lastTick : c.tickMs
    e.lastTick = now
    const rms = readRms()
    setLevel(rms)
    if (e.mode !== 'handsfree') return

    if (e.suspended) {
      if (e.inSpeech) {
        e.inSpeech = false
        e.voicedMs = 0
        stopRecorder()
        startRecorder()
      }
      e.loudRun = 0
      return
    }

    const threshold = Math.max(c.minRms, e.noise * c.noiseMult)
    const loud = rms > threshold

    if (!e.inSpeech) {
      if (loud) {
        e.loudRun += dt
        if (e.loudRun >= c.onsetMs) {
          e.inSpeech = true
          e.speechStart = now - e.loudRun
          e.voicedMs = e.loudRun
          e.lastVoice = now
          setPhase('speech')
        }
      } else {
        e.loudRun = 0
        e.noise = Math.min(0.03, e.noise * 0.95 + rms * 0.05)
        if (now - e.recStart > c.recycleMs) {
          stopRecorder()
          startRecorder()
        }
      }
      return
    }

    if (loud) {
      e.voicedMs += dt
      e.lastVoice = now
    }
    if (now - e.lastVoice >= c.trailingSilenceMs || now - e.speechStart >= c.maxUtteranceMs) finishUtterance()
  }, [finishUtterance, readRms, startRecorder, stopRecorder])

  const stopHandsFree = useCallback(async () => {
    const e = E.current
    if (e.mode !== 'handsfree') return
    e.mode = 'idle'
    clearInterval(e.timer)
    e.inSpeech = false
    e.suspended = false
    await stopRecorder()
    releaseStream()
    setMode('idle')
    setPhase('idle')
    setLevel(0)
  }, [releaseStream, stopRecorder])

  const startHandsFree = useCallback(async () => {
    const e = E.current
    if (e.mode === 'handsfree') return true
    if (e.mode === 'ptt') await stopPTT()
    setError(null)
    try {
      await ensureStream()
    } catch (err) {
      setError(err.name === 'NotAllowedError' ? 'Microphone ki permission chahiye' : 'Microphone nahi mila')
      return false
    }
    e.mode = 'handsfree'
    e.inSpeech = false
    e.loudRun = 0
    e.voicedMs = 0
    e.lastTick = 0
    e.noise = 0.01
    startRecorder()
    setMode('handsfree')
    setPhase('listening')
    if (e.ctx && e.ctx.state === 'suspended') e.ctx.resume().catch(() => {})
    e.timer = setInterval(tick, cfg.current.tickMs)
    return true
  }, [ensureStream, startRecorder, stopPTT, tick])

  /** Pause hands-free detection while the app is speaking, so it never hears itself. */
  const setSuspended = useCallback((value) => {
    E.current.suspended = !!value
  }, [])

  useEffect(
    () => () => {
      const e = E.current
      clearInterval(e.timer)
      clearTimeout(e.pttTimer)
      e.mode = 'idle'
      try {
        if (e.rec && e.rec.state !== 'inactive') e.rec.stop()
      } catch {
        // already stopped
      }
      if (e.stream) e.stream.getTracks().forEach((t) => t.stop())
      if (e.ctx) e.ctx.close().catch(() => {})
    },
    [],
  )

  return {
    supported: recorderSupported(),
    mode,
    phase,
    level,
    error,
    recording: mode === 'ptt',
    handsFree: mode === 'handsfree',
    startPTT,
    stopPTT,
    cancelPTT,
    startHandsFree,
    stopHandsFree,
    setSuspended,
  }
}
