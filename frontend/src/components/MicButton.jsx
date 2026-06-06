import { useState, useRef } from 'react'
import { Mic, MicOff, Square } from 'lucide-react'

export default function MicButton({ onResult, color = 'blue', label = 'बोलो', disabled = false }) {
  const [state, setState] = useState('idle') // idle | recording | loading
  const mediaRef = useRef(null)
  const chunksRef = useRef([])

  const start = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const recorder = new MediaRecorder(stream)
      chunksRef.current = []
      recorder.ondataavailable = (e) => chunksRef.current.push(e.data)
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
        setState('loading')
        await onResult(blob)
        setState('idle')
      }
      recorder.start()
      mediaRef.current = recorder
      setState('recording')
      setTimeout(() => recorder.state === 'recording' && recorder.stop(), 6000)
    } catch {
      alert('Microphone permission required')
    }
  }

  const stop = () => {
    if (mediaRef.current?.state === 'recording') mediaRef.current.stop()
  }

  const isBlue = color === 'blue'
  const baseClass = isBlue
    ? 'bg-paytm-blue active:bg-paytm-blue-dark'
    : 'bg-paytm-orange active:bg-paytm-orange-dark'
  const pulseClass = state === 'recording'
    ? isBlue ? 'mic-pulse-blue' : 'mic-pulse-orange'
    : ''

  return (
    <div className="flex flex-col items-center gap-3">
      <button
        onClick={state === 'recording' ? stop : start}
        disabled={disabled || state === 'loading'}
        className={`w-20 h-20 rounded-full text-white flex items-center justify-center transition-all ${baseClass} ${pulseClass} disabled:opacity-50`}
      >
        {state === 'recording' ? <Square size={32} /> : <Mic size={32} />}
      </button>

      {state === 'recording' && (
        <div className="flex gap-1 items-end h-8">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="wave-bar" style={{ animationDelay: `${i * 0.1}s` }} />
          ))}
        </div>
      )}

      <span className="text-sm font-medium text-gray-600">
        {state === 'idle' && label}
        {state === 'recording' && 'रोकने के लिए टैप करें...'}
        {state === 'loading' && 'AI समझ रहा है...'}
      </span>
    </div>
  )
}
