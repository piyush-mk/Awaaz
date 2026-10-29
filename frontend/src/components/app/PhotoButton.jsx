import { useRef } from 'react'
import { Camera } from 'lucide-react'
import { Spinner } from './ui'

/** Opens the phone camera (or the file picker on desktop). Calls onFiles(File[]). */
export default function PhotoButton({
  onFiles,
  multiple = false,
  busy = false,
  label = 'Photo lein',
  icon: Icon = Camera,
  variant = 'navy',
  className = '',
  compact = false,
}) {
  const ref = useRef(null)
  const styles =
    variant === 'navy'
      ? 'bg-ink text-white active:bg-ink-2'
      : variant === 'blue'
        ? 'bg-paytm-blue text-ink active:bg-paytm-blue-dark'
        : 'bg-white text-ink border border-line active:bg-bg-app'
  return (
    <>
      <input
        ref={ref}
        type="file"
        accept="image/*"
        capture="environment"
        multiple={multiple}
        className="hidden"
        onChange={(e) => {
          const files = Array.from(e.target.files || [])
          e.target.value = ''
          if (files.length) onFiles(files)
        }}
      />
      <button
        type="button"
        disabled={busy}
        onClick={() => ref.current?.click()}
        aria-label={label}
        className={`inline-flex items-center justify-center gap-2 rounded-xl font-semibold transition-colors disabled:opacity-60 ${
          compact ? 'w-12 h-12' : 'min-h-[48px] px-5'
        } ${styles} ${className}`}
      >
        {busy ? <Spinner size={20} /> : <Icon size={20} />}
        {!compact && label}
      </button>
    </>
  )
}
