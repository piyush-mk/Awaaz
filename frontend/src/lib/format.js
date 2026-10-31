import { lang, tr, unitOf } from './i18n.js'

// Small formatting helpers shared by the merchant app screens.

export function inr(value, decimals) {
  const n = Number(value || 0)
  const d = decimals ?? (Number.isInteger(Math.round(n * 100) / 100) ? 0 : 2)
  const abs = Math.abs(n).toLocaleString('en-IN', { minimumFractionDigits: d, maximumFractionDigits: d })
  return `${n < 0 ? '-' : ''}₹${abs}`
}

export function num(value, max = 2) {
  const n = Number(value || 0)
  return n.toLocaleString('en-IN', { maximumFractionDigits: max })
}

/** 0.45 kg -> "450 g", 2 packet -> "2 packet" */
export function qtyLabel(qty, unit) {
  const q = Number(qty || 0)
  if (unit === 'kg' && q > 0 && q < 1) return `${Math.round(q * 1000)} ${unitOf('g')}`
  if (unit === 'l' && q > 0 && q < 1) return `${Math.round(q * 1000)} ${unitOf('ml')}`
  return `${num(q, 3)} ${unitOf(unit)}`.trim()
}

export function shortDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return String(iso).slice(0, 10)
  return d.toLocaleDateString(lang === 'hi' ? 'hi-IN' : 'en-IN', { day: 'numeric', month: 'short' })
}

export function shortTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })
}

const SOURCE_LABELS = {
  sarvam: 'Sarvam',
  openrouter: 'OpenRouter',
  rules: 'Rules',
  fixture: 'demo data',
}

/** Text for the small "source . latency" chip. Returns '' when there is nothing to show. */
export function sourceText(source, latencyMs, demo) {
  if (!source && !demo) return ''
  if (demo || source === 'fixture') return 'demo data'
  const label = SOURCE_LABELS[source] || String(source)
  const ms = Number(latencyMs || 0)
  if (!ms) return label
  return ms >= 1000 ? `${label} · ${(ms / 1000).toFixed(1)} s` : `${label} · ${Math.round(ms)} ms`
}

function seconds(ms) {
  const v = Number(ms) / 1000
  return `${v < 0.095 ? v.toFixed(2) : v.toFixed(1)} s`
}

/** "stt 0.9 s, parse 0.02 s, total 1.1 s" from the response `timings` (any value may be null / missing). */
export function timingsText(timings) {
  if (!timings || typeof timings !== 'object') return ''
  const parts = [['stt', timings.stt_ms], ['parse', timings.parse_ms], ['llm', timings.llm_ms], ['total', timings.total_ms]]
    .filter(([, v]) => v !== null && v !== undefined && Number.isFinite(Number(v)))
    .map(([label, v]) => `${label} ${seconds(v)}`)
  return parts.join(', ')
}

/** Backend URLs are absolute (PUBLIC_BASE_URL). Turn them into same-origin paths so the dev proxy and the
 *  hosted build both work. Anything that is not one of our own paths is returned untouched. */
export function toPath(url) {
  if (!url) return url
  try {
    const u = new URL(url, 'http://local.invalid')
    if (/^\/(api|r|k|webhooks)\//.test(u.pathname)) return u.pathname + u.search
  } catch {
    // not a URL
  }
  return url
}

export function clamp(n, lo, hi) {
  return Math.min(hi, Math.max(lo, n))
}

export function errMessage(e, fallback = tr('Kuch gadbad ho gayi, dobara try karein')) {
  if (!e) return fallback
  const m = typeof e === 'string' ? e : e.message
  if (!m || m === 'Failed to fetch' || /NetworkError/i.test(m)) return tr('Server se connect nahi ho paya. Internet check karein.')
  return m
}
