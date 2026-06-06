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