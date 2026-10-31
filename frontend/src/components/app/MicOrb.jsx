import { useRef } from 'react'
import { Mic, Square, Ear } from 'lucide-react'
import { tr } from '../../lib/i18n'

/**
 * The big Paytm-style mic. Hold to talk (release sends), or tap once to start and tap again to send.
 * In hands-free mode it becomes an indicator that shows when speech is heard.
 */
export default function MicOrb({ rec, busy, size = 84, onUnsupported }) {
  const downAt = useRef(0)
  const wasRecording = useRef(false)

  const onDown = (e) => {
    e.preventDefault()
    if (!rec.supported) {
      onUnsupported?.()
      return
    }
    try {
      e.currentTarget.setPointerCapture(e.pointerId)
    } catch {
      // not supported
    }
    if (busy || rec.handsFree) return
    downAt.current = performance.now()
    wasRecording.current = rec.recording
    if (!rec.recording) rec.startPTT()
  }
  const onUp = (e) => {
    e.preventDefault()
    if (!rec.supported) return
    if (busy || rec.handsFree) return
    const held = performance.now() - downAt.current
    if (wasRecording.current) rec.stopPTT() // second tap ends a tap-started recording
    else if (held > 450) rec.stopPTT() // press and hold: release sends
    // short tap on an idle orb: keep recording until the next tap
  }
  const onCancel = () => {
    if (rec.recording && performance.now() - downAt.current > 450) rec.stopPTT()
  }

  const active = rec.recording || rec.phase === 'speech'
  const scale = 1 + Math.min(rec.level * 4, 0.35)

  return (
    <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
      {(active || rec.handsFree) && (
        <span
          className="orb-ring absolute inset-0 rounded-full bg-paytm-blue"
          style={{ animationDuration: rec.phase === 'speech' ? '0.9s' : '1.6s' }}
        />
      )}
      <button
        type="button"
        aria-label={rec.recording ? tr('Bhejne ke liye chhodein') : tr('Bolne ke liye dabayein')}
        className={`orb relative rounded-full flex items-center justify-center text-white transition-colors ${
          active ? 'bg-accent' : rec.handsFree ? 'bg-ink' : 'bg-paytm-blue'
        } ${busy ? 'opacity-60' : ''}`}
        style={{ width: size, height: size, transform: `scale(${active ? scale : 1})` }}
        onPointerDown={onDown}
        onPointerUp={onUp}
        onPointerCancel={onCancel}
        onContextMenu={(e) => e.preventDefault()}
      >
        {rec.recording ? <Square size={size * 0.34} fill="currentColor" /> : rec.handsFree ? <Ear size={size * 0.4} /> : <Mic size={size * 0.44} />}
      </button>
    </div>
  )
}
