// Browser binding for the speech engine (lib/speechCore.js): one manager per page load, shared by the phone
// app and the Soundbox. Everything that speaks goes through it, so nothing can overlap or double-speak.

import { createSpeechEngine } from './speechCore'

const SILENT_WAV = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA='

/** Server URLs may be absolute (PUBLIC_BASE_URL): keep same-origin paths so the dev proxy and the hosted build work. */
export function localUrl(url) {
  if (!url || typeof url !== 'string') return url || null
  if (url.startsWith('/') || url.startsWith('data:') || url.startsWith('blob:')) return url
  try {
    const u = new URL(url, window.location.origin)
    if (/^\/(api|r|k|webhooks)\//.test(u.pathname)) return u.pathname + u.search
  } catch {
    // keep as is
  }
  return url
}

function userHasInteracted() {
  try {
    return !!navigator.userActivation?.hasBeenActive
  } catch {
    return false
  }
}

async function fetchPhrases() {
  const res = await fetch('/api/voice/phrases')
  if (!res.ok) {
    const e = new Error(`phrases ${res.status}`)
    e.status = res.status
    throw e
  }
  return res.json()
}

let manager = null

export function getSpeechManager() {
  if (manager) return manager
  const hasWindow = typeof window !== 'undefined'
  manager = createSpeechEngine({
    createAudio: (url) => {
      const a = new Audio(url)
      a.preload = 'auto'
      return a
    },
    synth: hasWindow && 'speechSynthesis' in window ? window.speechSynthesis : null,
    Utterance: hasWindow && 'SpeechSynthesisUtterance' in window ? window.SpeechSynthesisUtterance : null,
    resolveUrl: localUrl,
    fetchPhrases,
    unlocked: hasWindow && userHasInteracted(),
    onBlocked: () => manager?.setBlocked(),
    unlockHook: () => {
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
    },
  })

  if (hasWindow) {
    // The first touch / key press unlocks audio (the mic press on the phone) and starts warming the phrase cache.
    // Capture phase: MicOrb stops pointer events from bubbling in some paths.
    const onGesture = () => {
      if (!manager.getState().unlocked) manager.unlock()
      else manager.markInteracted()
    }
    window.addEventListener('pointerdown', onGesture, { capture: true })
    window.addEventListener('keydown', onGesture, { capture: true })
    window.addEventListener('touchstart', onGesture, { capture: true, passive: true })
    manager.init()
  }
  return manager
}
