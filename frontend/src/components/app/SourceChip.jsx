import { sourceText } from '../../lib/format'

/** Live results need no label. Only a result that came from demo data says so, because it is not real. */
export default function SourceChip({ source, latency, demo, className = '' }) {
  if (sourceText(source, latency, demo) !== 'demo data') return null
  return (
    <span className={`inline-flex items-center flex-shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium bg-orange-100 text-orange-800 ${className}`}>
      demo
    </span>
  )
}
