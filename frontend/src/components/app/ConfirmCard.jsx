import { Check, X } from 'lucide-react'
import SourceChip from './SourceChip'

/**
 * Anything that moves money or stock waits behind this card: big Haan / Nahi.
 * `children` shows the detail (lines, amounts); `speak` text is shown as the question.
 */
export default function ConfirmCard({
  title,
  question,
  children,
  onYes,
  onNo,
  busy,
  yesLabel = 'Haan',
  noLabel = 'Nahi',
  warn,
  source,
  latency,
  demo,
  tone = 'blue',
}) {
  const ring = tone === 'orange' ? 'border-accent' : 'border-paytm-blue'
  return (
    <div className={`bg-white rounded-2xl border-2 ${ring} p-4`}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          {title && <div className="text-sm text-ink-3">{title}</div>}
          {question && <div className="font-hindi text-xl font-semibold text-ink leading-snug">{question}</div>}
        </div>
        <SourceChip source={source} latency={latency} demo={demo} />
      </div>
      {warn && (
        <div className="mt-2 rounded-xl bg-orange-50 px-3 py-2 text-sm font-medium text-orange-900">
          {warn}
        </div>
      )}
      {children && <div className="mt-3">{children}</div>}
      <div className="mt-4 grid grid-cols-2 gap-3">
        <button
          onClick={onNo}
          disabled={busy}
          className="min-h-[56px] rounded-xl bg-bg-app text-ink font-hindi text-xl font-semibold flex items-center justify-center gap-2 active:bg-line disabled:opacity-50"
        >
          <X size={22} /> {noLabel}
        </button>
        <button
          onClick={onYes}
          disabled={busy}
          className="min-h-[56px] rounded-xl bg-ink text-white font-hindi text-xl font-semibold flex items-center justify-center gap-2 active:bg-ink-2 disabled:opacity-50"
        >
          <Check size={22} /> {busy ? '...' : yesLabel}
        </button>
      </div>
    </div>
  )
}
