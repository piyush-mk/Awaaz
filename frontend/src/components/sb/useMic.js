import { useCallback, useEffect, useRef, useState } from 'react'

const MIME_CANDIDATES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus']

function pickMime() {
  if (typeof MediaRecorder === 'undefined') return ''
  return MIME_CANDIDATES.find((m) => MediaRecorder.isTypeSupported?.(m)) || ''
}

const extFor = (mime) => (mime.includes('mp4') ? 'm4a' : mime.includes('ogg') ? 'ogg' : 'webm')

/**
 * Push-to-talk recorder (MediaRecorder).
 *   const mic = useMic({ onRecorded: (blob, filename) => ... })
 *   <button onPointerDown={mic.pressStart} onPointerUp={mic.pressEnd} onPointerLeave={mic.pressEnd}
 *           onClick={mic.keyboardToggle}>
 * `onStop()` fires the moment a recording that will be sent stops (before the blob is ready).
 * Hold (>= 350 ms) = release to send. A short tap = toggle (tap again to send). Recordings under
 * 300 ms are dropped. The microphone is released as soon as recording stops.
 */
export default function useMic({ onRecorded, onStop } = {}) {
  const [recording, setRecording] = useState(false)
  const [seconds, setSeconds] = useState(0)
  const [error, setError] = useState('')
  const supported = typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== 'undefined'

  const recRef = useRef(null)
  const streamRef = useRef(null)
  const chunks = useRef([])
  const startedAt = useRef(0)
  const pressAt = useRef(0)
  const starting = useRef(false)
  const wantStop = useRef(false)
  const swallowRelease = useRef(false)
  const timer = useRef(null)
  const cb = useRef(onRecorded)
  cb.current = onRecorded
  const stopCb = useRef(onStop)
  stopCb.current = onStop

  const cleanup = useCallback(() => {
    clearInterval(timer.current)
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    recRef.current = null
    setRecording(false)
    setSeconds(0)
  }, [])

  const stop = useCallback(() => {
    if (starting.current) {
      wantStop.current = true
      return
    }
    const rec = recRef.current
    if (rec && rec.state !== 'inactive') {
      if (Date.now() - startedAt.current >= 300) stopCb.current?.()
      rec.stop()
    }
  }, [])

  const start = useCallback(async () => {
    if (recRef.current || starting.current) return
    setError('')
    if (!supported) {
      setError('Is browser mein mic recording available nahi hai (HTTPS ya localhost chahiye)')
      return
    }
    starting.current = true
    wantStop.current = false
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      const mime = pickMime()
      const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined)
      chunks.current = []
      rec.ondataavailable = (e) => e.data && e.data.size > 0 && chunks.current.push(e.data)
      rec.onstop = () => {
        const type = rec.mimeType || mime || 'audio/webm'
        const blob = new Blob(chunks.current, { type })
        const ms = Date.now() - startedAt.current
        cleanup()
        if (ms >= 300 && blob.size > 0) cb.current?.(blob, `speech.${extFor(type)}`)
      }
      rec.start()
      recRef.current = rec
      startedAt.current = Date.now()
      setRecording(true)
      setSeconds(0)
      timer.current = setInterval(() => setSeconds(Math.floor((Date.now() - startedAt.current) / 1000)), 250)
    } catch (e) {
      cleanup()
      setError(e && e.name === 'NotAllowedError' ? 'Mic ki permission nahi mili' : 'Mic shuru nahi ho paya')
    } finally {
      starting.current = false
      if (wantStop.current) {
        wantStop.current = false
        stop()
      }
    }
  }, [supported, cleanup, stop])

  const pressStart = useCallback(
    (e) => {
      e?.preventDefault?.()
      if (recRef.current || starting.current) {
        // tapped while recording in toggle mode -> send
        swallowRelease.current = true
        stop()
        return
      }
      pressAt.current = Date.now()
      swallowRelease.current = false
      start()
    },
    [start, stop],
  )

  const pressEnd = useCallback(() => {
    if (swallowRelease.current) {
      swallowRelease.current = false
      return
    }
    if (!pressAt.current) return
    const held = Date.now() - pressAt.current
    pressAt.current = 0
    if (held >= 350) stop() // hold-to-talk; a short tap leaves it recording (toggle)
  }, [stop])

  const keyboardToggle = useCallback(
    (e) => {
      if (e.detail !== 0) return // pointer clicks are handled by pressStart/pressEnd
      if (recRef.current || starting.current) stop()
      else start()
    },
    [start, stop],
  )

  useEffect(
    () => () => {
      clearInterval(timer.current)
      try {
        if (recRef.current && recRef.current.state !== 'inactive') {
          recRef.current.onstop = null
          recRef.current.stop()
        }
      } catch {
        /* ignore */
      }
      streamRef.current?.getTracks().forEach((t) => t.stop())
    },
    [],
  )

  return { recording, seconds, error, supported, start, stop, pressStart, pressEnd, keyboardToggle }
}
