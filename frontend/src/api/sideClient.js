// Small fetch helpers for the side screens (/soundbox, /wa, /status, /test).
// The merchant phone app has its own api/client.js; this file is deliberately separate.

export class ApiError extends Error {
  constructor(message, status, body) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

function errorText(body, fallback) {
  if (!body) return fallback
  const d = body.detail ?? body.error ?? body
  if (typeof d === 'string') return d
  if (Array.isArray(d)) return d.map((x) => x.msg || JSON.stringify(x)).join(', ')
  try {
    return JSON.stringify(d)
  } catch {
    return fallback
  }
}

export async function api(path, { method = 'GET', json, form, headers = {}, signal } = {}) {
  const init = { method, headers: { ...headers }, signal }
  if (json !== undefined) {
    init.headers['Content-Type'] = 'application/json'
    init.body = JSON.stringify(json)
  } else if (form) {
    init.body = form
  }
  let res
  try {
    res = await fetch(path, init)
  } catch (e) {
    throw new ApiError(e.message === 'Failed to fetch' ? 'Backend se connect nahi ho paya' : e.message, 0, null)
  }
  const text = await res.text()
  let body = null
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    body = text
  }
  if (!res.ok) throw new ApiError(errorText(body, res.statusText || 'Request failed'), res.status, body)
  return body
}

/** Like api() but never throws: returns {ok, status, ms, body, headers} for the test console. */
export async function rawRequest(method, path, { json, form, headers = {} } = {}) {
  const started = performance.now()
  const init = { method, headers: { ...headers } }
  if (json !== undefined) {
    init.headers['Content-Type'] = 'application/json'
    init.body = typeof json === 'string' ? json : JSON.stringify(json)
  } else if (form) {
    init.body = form
  }
  try {
    const res = await fetch(path, init)
    const ct = res.headers.get('content-type') || ''
    const text = await res.text()
    let body = text
    if (ct.includes('json')) {
      try {
        body = JSON.parse(text)
      } catch {
        /* keep text */
      }
    }
    return { ok: res.ok, status: res.status, ms: Math.round(performance.now() - started), body, contentType: ct }
  } catch (e) {
    return { ok: false, status: 0, ms: Math.round(performance.now() - started), body: { error: e.message }, contentType: '' }
  }
}

/** Server URLs may be absolute (PUBLIC_BASE_URL). Keep same-origin paths so the dev proxy works. */
export function localUrl(u) {
  if (!u || typeof u !== 'string') return u || null
  if (u.startsWith('/')) return u
  try {
    const parsed = new URL(u)
    if (/^\/(api|r|k|webhooks)\//.test(parsed.pathname)) return parsed.pathname + parsed.search
  } catch {
    /* not a URL */
  }
  return u
}

// --- shared bits -----------------------------------------------------------------------------

export const sessionFromUrl = () => {
  try {
    return new URLSearchParams(window.location.search).get('session') || ''
  } catch {
    return ''
  }
}

export const inr = (n) => {
  const v = Number(n)
  if (!Number.isFinite(v)) return '0'
  return v.toLocaleString('en-IN', { maximumFractionDigits: 2, minimumFractionDigits: v % 1 ? 2 : 0 })
}

// --- agent / counter -------------------------------------------------------------------------

/** One spoken (audio Blob) or typed (text) utterance. Cart/QR changes arrive over SSE. */
export function sendUtterance({ text, audio, filename, sessionId = 'default', context = 'counter', phrase, speak = true }) {
  const form = new FormData()
  if (audio) form.append('audio', audio, filename || 'speech.webm')
  if (text) form.append('text', text)
  form.append('context', context)
  form.append('session_id', sessionId)
  form.append('speak', speak ? 'true' : 'false')
  return api('/api/agent/utterance', { method: 'POST', form, headers: phrase ? { 'X-Demo-Phrase': String(phrase) } : {} })
}

export const simulatePayment = (orderId) =>
  api(`/api/payments/${encodeURIComponent(orderId)}/simulate`, { method: 'POST' })

export const getDashboard = () => api('/api/dashboard')

// --- whatsapp --------------------------------------------------------------------------------

export const getWaStatus = () => api('/api/wa/status')
export const getConversations = () => api('/api/wa/conversations')
export const getWaOrders = (status = 'proposed') => api(`/api/wa/orders?status=${encodeURIComponent(status)}`)
export const confirmWaOrder = (id) => api(`/api/wa/orders/${id}/confirm`, { method: 'POST' })
export const cancelWaOrder = (id) => api(`/api/wa/orders/${id}/cancel`, { method: 'POST' })

export function getMessages({ customerId, supplierId, phone, limit = 300 } = {}) {
  const q = new URLSearchParams()
  if (customerId) q.set('customer_id', customerId)
  else if (supplierId) q.set('supplier_id', supplierId)
  else if (phone) q.set('phone', phone)
  q.set('limit', String(limit))
  return api(`/api/wa/messages?${q.toString()}`)
}

/** Merchant sends a manual message. */
export const waSend = ({ to, customerId, supplierId, body }) =>
  api('/api/wa/send', { method: 'POST', json: { to, customer_id: customerId || null, supplier_id: supplierId || null, body } })

/** Play the customer. type = text | audio | image. */
export function simulateInbound({ phone, customerId, type = 'text', body = '', file, filename, demoPhrase }) {
  const form = new FormData()
  if (phone) form.append('from_phone', phone)
  else if (customerId) form.append('customer_id', String(customerId))
  form.append('type', type)
  if (body) form.append('body', body)
  if (demoPhrase) form.append('demo_phrase', String(demoPhrase))
  if (file) form.append('file', file, filename || file.name || 'upload')
  return api('/api/wa/simulate-inbound', { method: 'POST', form })
}

export const getKhataCustomers = () => api('/api/khata/customers')
export const getSuppliers = () => api('/api/suppliers')

// --- admin -----------------------------------------------------------------------------------

export const getAdminStatus = () => api('/api/admin/status')
export const getAdminHealth = (live = false) => api(`/api/admin/health${live ? '?live=1' : ''}`)
export const getChecklist = () => api('/api/admin/demo-checklist')
export const resetDemo = () => api('/api/admin/reset-demo', { method: 'POST' })
