import { useCallback, useEffect, useMemo, useState } from 'react'
import { getSpeechManager } from '../lib/speechManager'

/** Live {unlocked, speaking, muted, phrasesReady} of the shared manager, without owning it. */
export function useSpeechState() {
  const manager = useMemo(() => getSpeechManager(), [])
  const [snap, setSnap] = useState(() => manager.getState())
  useEffect(() => {
    setSnap(manager.getState())
    return manager.subscribe(setSnap)
  }, [manager])
  return snap
}

/**
 * React view of the one speech manager (lib/speechManager.js, engine in lib/speechCore.js), shared by the
 * phone app and the Soundbox.
 *
 *   const { speak, playPhrase, ack, speechReady, newTurn, cancel, enable, unlocked, speaking } = useSpeech()
 *
 *   speak(reply)                       // an API reply, a speech object {text, pace, pending, key, audio_url}, or text
 *   speak('Kul rupaye 249', { audioUrl })   // legacy form still works
 *   speak(data, { kind: 'money', key: 'pay:ORD1' })   // payment announcements are never dropped
 *   const token = ack(); ...request...; token.settle()   // instant "ji" when the mic stops
 *   speechReady(sseData)               // the SSE `speech_ready` event
 *
 * Lines never overlap. A newer reply fades out an older one (120 ms). Same key = spoken once, and the server
 * audio and the browser voice are never both used for one reply. A pending reply that has not produced
 * `speech_ready` after 3.5 s is read by the browser voice, so there is never silence.
 * Browsers block sound before a gesture: the first touch unlocks it; `unlocked` stays false until then
 * (the Soundbox shows its "Tap to enable sound" overlay from it).
 */
export default function useSpeech() {
  const manager = useMemo(() => getSpeechManager(), [])
  const snap = useSpeechState()

  // Leaving the screen silences it (the manager outlives the screens).
  useEffect(() => () => manager.cancel(), [manager])

  const speak = useCallback(
    (input, opts) => manager.speak(input, opts),
    [manager],
  )

  return {
    manager,
    speak,
    playPhrase: manager.playPhrase,
    ack: manager.ack,
    speechReady: manager.speechReady,
    hasPending: manager.hasPending,
    newTurn: manager.newTurn,
    duck: manager.duck,
    cancel: manager.cancel,
    enable: manager.unlock,
    setMuted: manager.setMuted,
    unlocked: snap.unlocked,
    speaking: snap.speaking,
    muted: snap.muted,
    phrasesReady: snap.phrasesReady,
  }
}
