export async function playBase64Audio(audioBase64, mimeType = 'audio/mpeg') {
  if (!audioBase64) return false

  const binary = atob(audioBase64)
  const bytes = new Uint8Array(binary.length)

  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i)
  }

  const blob = new Blob([bytes], { type: mimeType })
  const url = URL.createObjectURL(blob)

  try {
    const audio = new Audio(url)
    audio.preload = 'auto'
    audio.autoplay = true

    const playbackStarted = new Promise((resolve, reject) => {
      audio.onplaying = () => resolve(true)
      audio.onerror = () => reject(new Error('Audio playback failed'))
    })

    await audio.play()
    await Promise.race([
      playbackStarted,
      new Promise((_, reject) => setTimeout(() => reject(new Error('Audio did not start')), 2500)),
    ])

    await new Promise((resolve) => {
      audio.onended = resolve
      audio.onerror = resolve
    })
    return true
  } finally {
    URL.revokeObjectURL(url)
  }
}

function speakWithBrowserVoice(text, language = 'hi') {
  if (typeof window === 'undefined' || !('speechSynthesis' in window)) {
    return false
  }

  return new Promise((resolve) => {
    const utterance = new SpeechSynthesisUtterance(text)
    const lang = language === 'en' ? 'en-IN' : 'hi-IN'
    utterance.lang = lang
    utterance.rate = 0.95
    utterance.onend = () => resolve(true)
    utterance.onerror = () => resolve(false)

    const pickVoice = () => {
      const voices = window.speechSynthesis.getVoices()
      const match = voices.find((voice) => voice.lang && voice.lang.toLowerCase().startsWith(lang.toLowerCase().slice(0, 2)))
      if (match) {
        utterance.voice = match
      } else if (voices.length > 0) {
        utterance.voice = voices[0]
      }

      window.speechSynthesis.cancel()
      window.speechSynthesis.speak(utterance)
    }

    if (window.speechSynthesis.getVoices().length > 0) {
      pickVoice()
    } else {
      window.speechSynthesis.onvoiceschanged = pickVoice
    }
  })
}

export async function speakWithFallback(text, audioBase64, language = 'hi') {
  if (audioBase64) {
    try {
      const played = await playBase64Audio(audioBase64)
      if (played) {
        return true
      }
    } catch (_) {
      // fall through to browser voice
    }
  }

  return speakWithBrowserVoice(text, language)
}

// ---------------------------------------------------------------------------
// Added for the merchant app: play a hosted mp3 (audio_url) and one speak() entry point.
// ---------------------------------------------------------------------------

let currentAudio = null

function localUrl(url) {
  try {
    const u = new URL(url, window.location.origin)
    if (/^\/(api|r|k)\//.test(u.pathname)) return u.pathname + u.search
  } catch (_) {
    // keep as is
  }
  return url
}

export async function playUrl(url) {
  if (!url) return false
  stopSpeaking()
  const audio = new Audio(localUrl(url))
  currentAudio = audio
  audio.preload = 'auto'
  await audio.play()
  await new Promise((resolve) => {
    audio.onended = resolve
    audio.onerror = resolve
    audio.onpause = resolve
  })
  if (currentAudio === audio) currentAudio = null
  return true
}

export function stopSpeaking() {
  try {
    if (currentAudio) {
      currentAudio.pause()
      currentAudio = null
    }
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) window.speechSynthesis.cancel()
  } catch (_) {
    // ignore
  }
}

/**
 * Speak a server reply. Prefers the Bulbul mp3 (audio_url, or audio_base64), falls back to the browser voice.
 * `reply` is any API response: { spoken_text | text | message_hi, audio_url, audio_base64 }.
 * Never throws; resolves when playback ends.
 */
export async function speak(reply, language = 'hi') {
  if (!reply) return false
  const text = typeof reply === 'string' ? reply : reply.spoken_text || reply.text || reply.message_hi || ''
  const url = typeof reply === 'string' ? null : reply.audio_url || reply.url
  const b64 = typeof reply === 'string' ? null : reply.audio_base64
  try {
    if (url) {
      try {
        if (await playUrl(url)) return true
      } catch (_) {
        // fall through
      }
    }
    if (!text && !b64) return false
    return await speakWithFallback(text, b64, language)
  } catch (_) {
    return false
  }
}
