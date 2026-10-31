import { useEffect, useState } from 'react'
import { AlertTriangle, Loader2, Search, X } from 'lucide-react'
import SourceChip from './SourceChip'
import { tr } from '../../lib/i18n'

/** A quiet grouped block. Lists use `Rows` instead, so the screen is not a stack of boxes. */
export function Card({ className = '', children, ...rest }) {
  return (
    <div className={`bg-bg-app rounded-2xl p-4 ${className}`} {...rest}>
      {children}
    </div>
  )
}

/** Full-width rows split by hairlines. */
export function Rows({ className = '', children }) {
  return <ul className={`divide-y divide-line border-y border-line -mx-4 ${className}`}>{children}</ul>
}

/** The one number a screen leads with. */
export function Hero({ value, sub, tone = '', className = '' }) {
  return (
    <div className={className}>
      <div className={`text-[44px] font-semibold tabular tracking-tight leading-none ${tone}`}>{value}</div>
      {sub && <div className="mt-2 text-[15px] text-ink-3">{sub}</div>}
    </div>
  )
}

export function SectionTitle({ hi, en, right }) {
  return (
    <div className="flex items-end justify-between mb-2">
      <div>
        <h2 className="font-hindi text-lg font-semibold leading-tight text-ink">{hi}</h2>
        {en && <div className="text-sm text-ink-3">{en}</div>}
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
      {Icon && <Icon size={32} className="mb-3 text-ink-3/60" strokeWidth={1.5} />}
      <div className="font-hindi text-lg font-semibold text-ink">{hi}</div>
      {en && <div className="text-sm mt-0.5">{en}</div>}
      {children && <div className="mt-4">{children}</div>}
    </div>
  )
}

export function ErrorBox({ error, onRetry }) {
  if (!error) return null
  return (
    <div className="rounded-2xl bg-red-50 p-4 flex gap-3 items-start">
      <AlertTriangle size={20} className="text-stock-red flex-shrink-0 mt-0.5" />
      <div className="flex-1 min-w-0">
        <div className="font-hindi font-semibold text-ink">{tr('Kuch gadbad ho gayi')}</div>
        <div className="text-sm text-ink-3 break-words">{error.message || String(error)}</div>
        {onRetry && (
          <button onClick={() => onRetry()} className="mt-2 min-h-[44px] px-4 rounded-xl bg-ink text-white font-semibold text-sm">
            {tr('Dobara try karein')}
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
  ghost: 'bg-bg-app text-ink active:bg-line',
  danger: 'bg-red-50 text-red-700 active:bg-red-100',
  green: 'bg-green-700 text-white active:bg-green-800',
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

/** Sections inside a room: underlined text, not pills. */
export function Tabs({ items, value, onChange }) {
  return (
    <div className="flex gap-5 overflow-x-auto app-scroll px-4 -mx-4 border-b border-line" role="tablist">
      {items.map((t) => {
        const active = t.id === value
        return (
          <button
            key={t.id}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(t.id)}
            className={`flex-shrink-0 min-h-[44px] text-base whitespace-nowrap transition-colors ${
              active ? 'text-ink font-semibold shadow-[inset_0_-2px_0_#0E1B33]' : 'text-ink-3 font-medium'
            }`}
          >
            {t.label}
          </button>
        )
      })}
    </div>
  )
}

/** A search that stays out of the way until it is wanted. */
export function SearchToggle({ value, onChange, placeholder }) {
  const [open, setOpen] = useState(false)
  if (!open) {
    return (
      <button onClick={() => setOpen(true)} aria-label={placeholder} className="w-11 h-11 flex-shrink-0 rounded-full flex items-center justify-center text-ink-3">
        <Search size={20} />
      </button>
    )
  }
  return (
    <div className="relative flex-1 min-w-0">
      <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-3" />
      <input autoFocus className={`${inputCls} pl-10 pr-10`} placeholder={placeholder} value={value} onChange={(e) => onChange(e.target.value)} />
      <button onClick={() => { onChange(''); setOpen(false) }} aria-label={tr('Search band karein')} className="absolute right-0 top-0 w-11 h-12 flex items-center justify-center text-ink-3">
        <X size={18} />
      </button>
    </div>
  )
}

/** Sort and filter choices: plain text, clearly lighter than Tabs. */
export function Filters({ items, value, onChange }) {
  return (
    <div className="flex gap-1 overflow-x-auto app-scroll -mx-4 px-3">
      {items.map((s) => (
        <button
          key={s.id}
          onClick={() => onChange(s.id)}
          aria-pressed={value === s.id}
          className={`flex-shrink-0 min-h-[44px] px-2.5 text-sm whitespace-nowrap ${value === s.id ? 'text-ink font-semibold underline underline-offset-4' : 'text-ink-3 font-medium'}`}
        >
          {s.label}
        </button>
      ))}
    </div>
  )
}

export function Stepper({ value, onChange, step = 1, min = 0, unit }) {
  const dec = () => onChange(Math.max(min, Math.round((Number(value) - step) * 1000) / 1000))
  const inc = () => onChange(Math.round((Number(value) + step) * 1000) / 1000)
  return (
    <div className="inline-flex items-center rounded-xl bg-bg-app">
      <button onClick={dec} aria-label={tr('kam')} className="w-11 h-11 flex items-center justify-center text-xl font-semibold text-ink active:bg-line rounded-l-xl">
        &minus;
      </button>
      <div className="min-w-[44px] px-1 text-center font-semibold tabular text-ink">
        {value}
        {unit ? <span className="text-xs text-ink-3 ml-0.5">{unit}</span> : null}
      </div>
      <button onClick={inc} aria-label={tr('zyada')} className="w-11 h-11 flex items-center justify-center text-xl font-semibold text-ink active:bg-line rounded-r-xl">
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
        role="dialog"
        aria-label={typeof title === 'string' ? title : undefined}
        className="sheet-up w-full max-w-[430px] max-h-[88vh] overflow-y-auto app-scroll bg-white rounded-t-3xl p-4 pb-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-hindi text-xl font-semibold text-ink">{title}</h3>
          <button onClick={onClose} aria-label={tr('band karo')} className="w-11 h-11 flex items-center justify-center rounded-full bg-bg-app">
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
  'w-full min-h-[48px] rounded-xl border border-line bg-white px-3 text-base text-ink placeholder:text-ink-3/70 focus:outline-none focus:ring-2 focus:ring-paytm-blue'

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
