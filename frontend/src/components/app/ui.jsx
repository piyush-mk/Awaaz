import { useEffect } from 'react'
import { AlertTriangle, Loader2, X } from 'lucide-react'
import SourceChip from './SourceChip'

export function Card({ className = '', children, ...rest }) {
  return (
    <div className={`bg-white rounded-2xl border border-line p-4 ${className}`} {...rest}>
      {children}
    </div>
  )
}

export function SectionTitle({ hi, en, right }) {
  return (
    <div className="flex items-end justify-between px-1 mb-2">
      <div>
        <h2 className="font-hindi text-xl font-bold leading-tight text-ink">{hi}</h2>
        {en && <div className="text-xs font-medium text-ink-3 tracking-wide">{en}</div>}
      </div>
      {right}
    </div>
  )
}

const TONES = {
  gray: 'bg-bg-app text-ink-3',
  blue: 'bg-sky-100 text-sky-800',
  green: 'bg-green-100 text-green-800',
  yellow: 'bg-yellow-100 text-yellow-900',
  red: 'bg-red-100 text-red-700',
  orange: 'bg-orange-100 text-orange-800',
  navy: 'bg-ink text-white',
}

export function Chip({ tone = 'gray', children, className = '' }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold ${TONES[tone]} ${className}`}>
      {children}
    </span>
  )
}

export function Skeleton({ className = 'h-16 w-full' }) {
  return <div className={`skeleton ${className}`} />
}

export function SkeletonList({ rows = 4, className = 'h-16' }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className={`w-full ${className}`} />
      ))}
    </div>
  )
}

export function Spinner({ size = 20, className = '' }) {
  return <Loader2 size={size} className={`animate-spin ${className}`} />
}

export function Empty({ icon: Icon, hi, en, children }) {
  return (
    <div className="flex flex-col items-center text-center py-10 px-6 text-ink-3">
      {Icon && <Icon size={36} className="mb-3 text-ink-3/60" strokeWidth={1.5} />}
      <div className="font-hindi text-xl font-bold text-ink">{hi}</div>
      {en && <div className="text-sm mt-0.5">{en}</div>}
      {children && <div className="mt-4">{children}</div>}
    </div>
  )
}

export function ErrorBox({ error, onRetry }) {
  if (!error) return null
  return (
    <div className="rounded-2xl border border-red-200 bg-red-50 p-4 flex gap-3 items-start">
      <AlertTriangle size={20} className="text-stock-red flex-shrink-0 mt-0.5" />
      <div className="flex-1 min-w-0">
        <div className="font-hindi font-bold text-ink">Kuch gadbad ho gayi</div>
        <div className="text-sm text-ink-3 break-words">{error.message || String(error)}</div>
        {onRetry && (
          <button onClick={() => onRetry()} className="mt-2 min-h-[44px] px-4 rounded-xl bg-ink text-white font-semibold text-sm">
            Dobara try karein
          </button>
        )}
      </div>
    </div>
  )
}

const BTN = {
  primary: 'bg-paytm-blue text-ink active:bg-paytm-blue-dark',
  navy: 'bg-ink text-white active:bg-ink-2',
  accent: 'bg-accent text-ink active:bg-paytm-orange-dark',
  ghost: 'bg-white text-ink border border-line active:bg-bg-app',
  danger: 'bg-red-50 text-red-700 border border-red-200 active:bg-red-100',
  green: 'bg-stock-green text-white active:opacity-90',
}

export function Btn({ variant = 'primary', size = 'md', busy, disabled, icon: Icon, children, className = '', ...rest }) {
  const sizes = size === 'lg' ? 'min-h-[56px] px-6 text-lg' : size === 'sm' ? 'min-h-[44px] px-4 text-sm' : 'min-h-[48px] px-5 text-base'
  return (
    <button
      disabled={disabled || busy}
      className={`inline-flex items-center justify-center gap-2 rounded-xl font-semibold transition-colors disabled:opacity-50 ${sizes} ${BTN[variant]} ${className}`}
      {...rest}
    >
      {busy ? <Spinner size={18} /> : Icon ? <Icon size={size === 'lg' ? 22 : 18} /> : null}
      {children}
    </button>
  )
}

export function Tabs({ items, value, onChange }) {
  return (
    <div className="flex gap-2 overflow-x-auto app-scroll px-4 py-2 -mx-4">
      {items.map((t) => {
        const active = t.id === value
        return (
          <button
            key={t.id}
            onClick={() => onChange(t.id)}
            className={`flex-shrink-0 min-h-[44px] px-4 rounded-full text-sm font-semibold border transition-colors ${
              active ? 'bg-ink text-white border-ink' : 'bg-white text-ink-3 border-line'
            }`}
          >
            <span className="font-hindi text-base">{t.hi}</span>
            <span className={`ml-1.5 text-xs ${active ? 'opacity-70' : 'opacity-60'}`}>{t.en}</span>
          </button>
        )
      })}
    </div>
  )
}

export function Stepper({ value, onChange, step = 1, min = 0, unit }) {
  const dec = () => onChange(Math.max(min, Math.round((Number(value) - step) * 1000) / 1000))
  const inc = () => onChange(Math.round((Number(value) + step) * 1000) / 1000)
  return (
    <div className="inline-flex items-center rounded-xl border border-line bg-white">
      <button onClick={dec} aria-label="kam" className="w-11 h-11 flex items-center justify-center text-xl font-bold text-ink active:bg-bg-app rounded-l-xl">
        &minus;
      </button>
      <div className="min-w-[44px] px-1 text-center font-semibold tabular text-ink">
        {value}
        {unit ? <span className="text-xs text-ink-3 ml-0.5">{unit}</span> : null}
      </div>
      <button onClick={inc} aria-label="zyada" className="w-11 h-11 flex items-center justify-center text-xl font-bold text-ink active:bg-bg-app rounded-r-xl">
        +
      </button>
    </div>
  )
}

/** Bottom sheet that stays inside the 430px phone frame. */
export function Sheet({ open, onClose, title, children }) {
  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => e.key === 'Escape' && onClose?.()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-ink/50" onClick={onClose}>
      <div
        className="sheet-up w-full max-w-[430px] max-h-[88vh] overflow-y-auto app-scroll bg-bg-app rounded-t-3xl p-4 pb-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-hindi text-xl font-bold text-ink">{title}</h3>
          <button onClick={onClose} aria-label="band karo" className="w-11 h-11 flex items-center justify-center rounded-full bg-white border border-line">
            <X size={20} />
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

export function Field({ label, children, hint }) {
  return (
    <label className="block">
      <span className="block text-sm font-semibold text-ink-3 mb-1">{label}</span>
      {children}
      {hint && <span className="block text-xs text-ink-3 mt-1">{hint}</span>}
    </label>
  )
}

export const inputCls =
  'w-full min-h-[48px] rounded-xl border border-line bg-white px-3 text-base text-ink placeholder:text-ink-3/60 focus:outline-none focus:ring-2 focus:ring-paytm-blue'

/** Result line under any AI output: spoken reply, then the source chip. */
export function ReplyLine({ text, source, latency, demo, className = '' }) {
  if (!text && !source) return null
  return (
    <div className={`flex items-start gap-2 ${className}`}>
      {text && <p className="flex-1 font-hindi text-base text-ink">{text}</p>}
      <SourceChip source={source} latency={latency} demo={demo} />
    </div>
  )
}
