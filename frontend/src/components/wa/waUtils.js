// Pure helpers for the WhatsApp simulator.

/** "2026-10-29T23:42:22.87" -> "23:42" (server times are naive IST; no timezone maths). */
export const hhmm = (iso) => (iso && iso.length >= 16 ? iso.slice(11, 16) : '')

export const dayKey = (iso) => (iso ? iso.slice(0, 10) : '')

export function dayLabel(iso) {
  if (!iso) return ''
  const d = new Date(`${dayKey(iso)}T00:00:00`)
  if (Number.isNaN(d.getTime())) return dayKey(iso)
  const today = new Date()
  const diff = Math.round((new Date(today.getFullYear(), today.getMonth(), today.getDate()) - d) / 86400000)
  if (diff === 0) return 'Aaj'
  if (diff === 1) return 'Kal'
  return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}

const URL_RE = /(https?:\/\/[^\s]+|upi:\/\/[^\s]+)/g

/**
 * Split a message body into display text plus rich link cards.
 * Receipt (/r/), passbook (/k/) and UPI links become cards and are removed from the text.
 */
export function parseBody(body) {
  const text = body || ''
  const cards = []
  const seen = new Set()
  const stripped = text.replace(URL_RE, (url) => {
    const clean = url.replace(/[).,;]+$/, '')
    let kind = null
    if (/^upi:\/\//i.test(clean)) kind = 'upi'
    else if (/\/r\/[\w-]+/.test(clean)) kind = 'receipt'
    else if (/\/k\/[\w.-]+|\/passbook\//.test(clean)) kind = 'passbook'
    if (!kind) return url
    if (!seen.has(clean)) {
      seen.add(clean)
      cards.push({ kind, url: clean })
    }
    return ''
  })
  const cleaned = stripped
    .split('\n')
    .map((l) => l.replace(/\s+$/, ''))
    .filter((l, i, arr) => !(l === '' && (arr[i - 1] === '' || i === arr.length - 1)))
    // drop dangling labels left behind by a removed link ("Paise bhejein (UPI):")
    .filter((l) => !/^(.*:)\s*$/.test(l) || !cards.length || !/(UPI|receipt|passbook|link)/i.test(l))
    .join('\n')
    .trim()
  return { text: cleaned, cards }
}

export function upiDetails(url) {
  try {
    const q = new URL(url.replace(/^upi:\/\//i, 'https://upi.local/')).searchParams
    return { amount: q.get('am'), name: q.get('pn'), vpa: q.get('pa') }
  } catch {
    return {}
  }
}

export function previewOf(msg) {
  if (!msg) return ''
  if (msg.type === 'audio') return 'Voice note'
  if (msg.type === 'image') return msg.body ? `Photo: ${msg.body.split('\n')[0]}` : 'Photo'
  if (msg.type === 'doc' || msg.type === 'document') return 'Document'
  return (msg.body || '').replace(/\s+/g, ' ')
}

export const initials = (name) =>
  (name || '?')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join('')

/** Deterministic pseudo waveform for a voice note. */
export function waveHeights(seed, n = 30) {
  let s = (Number(seed) || 7) * 9301 + 49297
  return Array.from({ length: n }, () => {
    s = (s * 9301 + 49297) % 233280
    return 6 + Math.round((s / 233280) * 18)
  })
}
