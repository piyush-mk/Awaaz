import { sourceText } from '../../lib/format'

/** "Sarvam . 1.2 s" or "demo data": proves where an AI result came from. */
export default function SourceChip({ source, latency, demo, className = '' }) {
  const text = sourceText(source, latency, demo)
  if (!text) return null
  const isDemo = text === 'demo data'
  return (
    <span
      className={`inline-flex items-center flex-shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium font-mono ${
        isDemo ? 'bg-orange-100 text-orange-800' : 'bg-ink text-paytm-blue'
      } ${className}`}
      title="AI source and latency"
    >
      {text}
    </span>
  )
}
