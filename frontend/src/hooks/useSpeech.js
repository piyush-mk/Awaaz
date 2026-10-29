import { useCallback, useEffect, useRef, useState } from 'react'
import { speakWithFallback } from '../lib/audio'
import { localUrl } from '../api/sideClient'

/**
 * Queued speech for the Soundbox. Lines never overlap: each speak() is played after the previous one.
 *
 *   const { speak, cancel, enable, unlocked, speaking } = useSpeech()
 *   speak('Kul rupaye 249', { audioUrl: data.audio_url })
 *
 * An item with audioUrl / audioBase64 plays that audio (Bulbul); otherwise (or if playback fails)
 * the browser's hi-IN speechSynthesis reads `text`. Browsers block sound before a user gesture, so
 * `unlocked` is false until enable() is called (any tap/key press on the page does that); a
 * NotAllowedError flips it back to false so the page can show "Tap to enable sound" again.
 */

const SILENT_WAV =
  'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA='

function userHasInteracted() {
  try {
    return !!navigator.userActivation?.hasBeenActive
  } catch {
    return false
  }
}

function playUrl(url, handle, onBlocked) {
  return new Promise((resolve, reject) => {
    const audio = new Audio(url)
    audio.preload = 'auto'
    let done = false
    const finish = (err) => {
      if (done) return
      done = true
      clearTimeout(guard)
      handle.stop = null
      err ? reject(err) : resolve(true)
    }
    handle.stop = () => {
      try {
        audio.pause()
      } catch {
        /* ignore */
      }
      finish()
    }
    // never hang the queue on a stalled stream
    const guard = setTimeout(() => finish(new Error('audio timeout')), 45000)
    audio.onended = () => finish()
    audio.onerror = () => finish(new Error('audio error'))
    audio.play().catch((e) => {
      if (e && e.name === 'NotAllowedError') onBlocked()
      finish(e)
    })
  })
}

function withTimeout(promise, ms) {
  return Promise.race([promise, new Promise((resolve) => setTimeout(() => resolve(false), ms))])
}

export default function useSpeech() {
  const [unlocked, setUnlocked] = useState(userHasInteracted())
  const [speaking, setSpeaking] = useState(false)
  const [muted, setMutedState] = useState(false)
  const queue = useRef([])
  const running = useRef(false)
  const handle = useRef({ stop: null })
  const mutedRef = useRef(false)
  const unlockedRef = useRef(unlocked)
  unlockedRef.current = unlocked

  const pump = useCallback(async () => {
    if (running.current) return
    running.current = true
    setSpeaking(true)
    while (queue.current.length) {
      const item = queue.current.shift()
      if (mutedRef.current) continue
      try {
        let played = false
        if (item.audioUrl) {
          try {
            played = await playUrl(localUrl(item.audioUrl), handle.current, () => setUnlocked(false))
          } catch {
            played = false
          }
        }
        if (!played && item.text) {
          // base64 audio when given, else the browser voice. Guard against onvoiceschanged never firing.
          await withTimeout(speakWithFallback(item.text, item.audioBase64 || null, item.lang || 'hi'), 4000 + item.text.length * 110)
        }
      } catch {
        /* a failed line must not block the next one */
      }
    }
    running.current = false
    setSpeaking(false)
  }, [])

  const speak = useCallback(
    (text, { audioUrl, audioBase64, lang = 'hi', interrupt = false } = {}) => {
      if (!text && !audioUrl && !audioBase64) return
      if (interrupt) {
        queue.current = []
        handle.current.stop?.()
        try {
          window.speechSynthesis?.cancel()
        } catch {
          /* ignore */
        }
      }
      queue.current.push({ text: text || '', audioUrl, audioBase64, lang })
      pump()
    },
    [pump],
  )

  const cancel = useCallback(() => {
    queue.current = []
    handle.current.stop?.()
    try {
      window.speechSynthesis?.cancel()
    } catch {
      /* ignore */
    }
  }, [])

  const enable = useCallback(() => {
    try {
      const a = new Audio(SILENT_WAV)
      a.volume = 0
      a.play().catch(() => {})
    } catch {
      /* ignore */
    }
    try {
      if ('speechSynthesis' in window) {
        const u = new SpeechSynthesisUtterance(' ')
        u.volume = 0
        window.speechSynthesis.speak(u)
        window.speechSynthesis.resume()
      }
    } catch {
      /* ignore */
    }
    setUnlocked(true)
  }, [])

  const setMuted = useCallback(
    (m) => {
      mutedRef.current = m
      setMutedState(m)
      if (m) cancel()
    },
    [cancel],
  )

  // any gesture unlocks audio; the overlay only exists for browsers that need an explicit tap
  useEffect(() => {
    const onGesture = () => {
      if (!unlockedRef.current) enable()
    }
    window.addEventListener('pointerdown', onGesture)
    window.addEventListener('keydown', onGesture)
    return () => {
      window.removeEventListener('pointerdown', onGesture)
      window.removeEventListener('keydown', onGesture)
    }
  }, [enable])

  useEffect(() => () => cancel(), [cancel])

  return { speak, cancel, enable, unlocked, speaking, muted, setMuted }
}
