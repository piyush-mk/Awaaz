// Single source of truth for every API call in the app (merchant /app screens and the legacy pages).
// Every function returns the parsed JSON body or throws Error(message) with .status and .detail set.
// The Node check script (scripts/check-api.mjs) sets globalThis.__AWAAZ_API_BASE__ so these also run without a browser.

const BASE = `${globalThis.__AWAAZ_API_BASE__ || ''}/api`

function messageOf(detail, fallback) {
  if (Array.isArray(detail)) return detail.map((d) => d.msg || JSON.stringify(d)).join(', ')
  if (detail && typeof detail === 'object') {
    return detail.message_hi || detail.warning?.message_hi || detail.message || detail.error || JSON.stringify(detail)
  }
  return detail || fallback
}

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, options)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    const e = new Error(messageOf(err.detail, 'Request failed'))
    e.status = res.status
    e.detail = err.detail
    throw e
  }
  return res.json()
}

const JSON_HEADERS = { 'Content-Type': 'application/json' }

function post(path, body) {
  return request(path, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: body === undefined ? undefined : JSON.stringify(body),
  })
}

function send(method, path, body) {
  return request(path, {
    method,
    headers: JSON_HEADERS,
    body: body === undefined ? undefined : JSON.stringify(body),
  })
}

function qs(params) {
  const p = new URLSearchParams()
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') p.append(k, String(v))
  })
  const s = p.toString()
  return s ? `?${s}` : ''
}

function extFor(blob) {
  const t = (blob && blob.type) || ''
  if (t.includes('mp4')) return 'm4a'
  if (t.includes('ogg')) return 'ogg'
  if (t.includes('wav')) return 'wav'
  return 'webm'
}

function imageForm(field, file) {
  const form = new FormData()
  form.append(field, file, file.name || 'photo.jpg')
  return form
}

// Voice
export async function parseVoice(audioBlob, transcript) {
  const form = new FormData()
  if (audioBlob) form.append('audio', audioBlob, 'recording.webm')
  if (transcript) form.append('transcript', transcript)
  return request('/voice/parse', { method: 'POST', body: form })
}

export async function textToSpeech(text) {
  return request('/voice/tts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
}

// Inventory
export async function getInventory() {
  return request('/inventory')
}

export async function restockInventory(items) {
  return request('/inventory/restock', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items }),
  })
}

export async function editInventory(productId, quantity, reason = 'manual_correction') {
  return request(`/inventory/${productId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ quantity, reason }),
  })
}

// Billing
export async function generateBill(items) {
  return request('/bill/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(items),
  })
}

export async function confirmBill(items, grandTotal) {
  return request('/bill/confirm', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items, grand_total: grandTotal }),
  })
}

export async function addProduct(name, quantity, unit = 'unit', price = 0, gst_rate = 0) {
  return request('/inventory/add-product', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, quantity, unit, price, gst_rate }),
  })
}

// Photo Inventory
export async function parsePhoto(imageFile) {
  const form = new FormData()
  form.append('image', imageFile)
  return request('/photo/parse', { method: 'POST', body: form })
}

// Dashboard
export async function getDashboard() {
  return request('/dashboard')
}

export async function getAlerts() {
  return request('/alerts')
}

export async function getTransactions(limit = 20) {
  return request(`/transactions?limit=${limit}`)
}


// ---------------------------------------------------------------------------
// Merchant app (v2)
// ---------------------------------------------------------------------------

// Admin
export const getStatus = () => request('/admin/status')
export const getHealth = () => request('/admin/health')

// Counter agent: one spoken or typed utterance -> cart edits + proposed actions
export async function sendUtterance({ audio, text, context = 'counter', sessionId, customerId, speak = true, filename } = {}) {
  const form = new FormData()
  if (audio) form.append('audio', audio, filename || `utterance.${extFor(audio)}`)
  if (text) form.append('text', text)
  form.append('context', context)
  form.append('session_id', sessionId || 'default')
  if (customerId) form.append('customer_id', String(customerId))
  form.append('speak', speak ? 'true' : 'false')
  return request('/agent/utterance', { method: 'POST', body: form })
}

export const listActions = (params) => request(`/actions${qs(params)}`)
export const getAction = (id) => request(`/actions/${id}`)
export const confirmAction = (id, body) => post(`/actions/${id}/confirm`, body || {})
export const cancelAction = (id) => post(`/actions/${id}/cancel`, {})

// Cart
export const createCart = (body) => post('/cart', body || {})
export const getCart = (cartId) => request(`/cart/${encodeURIComponent(cartId)}`)
export const clearCart = (cartId) => send('DELETE', `/cart/${encodeURIComponent(cartId)}`)
export const addCartLines = (cartId, items, mode = 'add') =>
  post(`/cart/${encodeURIComponent(cartId)}/lines`, { items, mode })
export const setCartLineQty = (cartId, productId, qty, unit) =>
  send('PUT', `/cart/${encodeURIComponent(cartId)}/lines/${productId}`, unit ? { qty, unit } : { qty })
export const removeCartLine = (cartId, productId) =>
  send('DELETE', `/cart/${encodeURIComponent(cartId)}/lines/${productId}`)
export const attachCartCustomer = (cartId, body) => post(`/cart/${encodeURIComponent(cartId)}/customer`, body)
export const addUsualToCart = (cartId, body) => post(`/cart/${encodeURIComponent(cartId)}/usual`, body || {})
export const checkoutCart = (cartId, body) => post(`/cart/${encodeURIComponent(cartId)}/checkout`, body || {})
export const getUsual = (customerId) => request(`/cart/usual/${customerId}`)
export const lookupUsual = (params) => request(`/cart/usual${qs(params)}`)

// Payments and invoices
export const getPayment = (orderId) => request(`/payments/${encodeURIComponent(orderId)}`)
export const simulatePayment = (orderId) => post(`/payments/${encodeURIComponent(orderId)}/simulate`)
export const listInvoices = (params) => request(`/invoices${qs({ limit: 20, ...params })}`)
export const getInvoice = (id) => request(`/invoices/${id}`)
export const sendInvoice = (id, body) => post(`/invoices/${id}/send`, body || {})

// Khata
export const listKhataCustomers = (params) => request(`/khata/customers${qs(params)}`)
export const getKhataCustomer = (id) => request(`/khata/customers/${id}`)
export const createKhataCustomer = (body) => post('/khata/customers', body)
export const addKhataEntry = (body) => post('/khata/entries', body)
export const confirmKhataEntry = (id, body) => post(`/khata/entries/${id}/confirm`, body || {})
export const disputeKhataEntry = (id, body) => post(`/khata/entries/${id}/dispute`, body || {})
export const previewReminders = (body) => post('/khata/reminders/preview', body || {})
export const sendReminders = (body) => post('/khata/reminders/send', body || {})
export const offerPostpaid = (body) => post('/khata/postpaid/offer', body)
export const getPostpaid = (id) => request(`/khata/postpaid/${id}`)
export const approvePostpaid = (id) => post(`/khata/postpaid/${id}/approve`)
export const importKhataPhoto = (file) =>
  request('/khata/import-photo', { method: 'POST', body: imageForm('image', file) })
export const getKhataImport = (actionId) => request(`/khata/import/${actionId}`)
export const confirmKhataImport = (actionId, rows) => post(`/khata/import/${actionId}/confirm`, { rows: rows || [] })

// Purchases (distributor bill scan)
export const scanPurchase = (file) =>
  request('/purchases/scan', { method: 'POST', body: imageForm('image', file) })
export const confirmPurchase = (actionId, body) => post(`/purchases/${actionId}/confirm`, body || {})
export const cancelPurchase = (actionId) => post(`/purchases/${actionId}/cancel`)
export const listPurchases = (params) => request(`/purchases${qs(params)}`)
export const listSuppliers = () => request('/purchases/suppliers')

// Photos
export const parseParchi = (file) =>
  request('/photo/parchi', { method: 'POST', body: imageForm('image', file) })
export function shelfAudit(files) {
  const form = new FormData()
  Array.from(files).forEach((f, i) => form.append('images', f, f.name || `shelf-${i}.jpg`))
  return request('/photo/shelf-audit', { method: 'POST', body: form })
}
export const confirmShelfAudit = (actionId, body) => post(`/photo/shelf-audit/${actionId}/confirm`, body || {})
export const cancelShelfAudit = (actionId) => post(`/photo/shelf-audit/${actionId}/cancel`)

// Galla (cash closing)
export const getGallaExpected = (day) => request(`/galla/expected${qs({ day })}`)
export const scanGalla = (file) => request('/galla/scan', { method: 'POST', body: imageForm('image', file) })
export const closeGalla = (denominations, extra) => post('/galla/close', { denominations, ...(extra || {}) })
export const getGallaHistory = (limit = 30) => request(`/galla/history${qs({ limit })}`)

// Stock views
export const getStock = (params) => request(`/stock${qs(params)}`)
export const getStockCover = (params) => request(`/stock/cover${qs(params)}`)
export const getStockExpiry = (days = 7) => request(`/stock/expiry${qs({ days })}`)
export const getMissedSales = (days = 7) => request(`/stock/missed${qs({ days })}`)
export const addMissedSale = (productName, productId) =>
  post('/stock/missed', { product_name: productName, ...(productId ? { product_id: productId } : {}) })
export const getProductDetail = (id) => request(`/stock/product/${id}`)
export const setPrices = (items) => post('/stock/prices', { items })

// Hisaab
export const getDashboardV2 = () => request('/dashboard/v2')

// Salaah: brief, reorder, questions about the shop
export const getBrief = (params) => request(`/brief/today${qs(params)}`)
export const speakBrief = (text) => post('/brief/speak', text ? { text } : {})
export const playBrief = () => post('/brief/play')
export const draftReorder = (supplierId) => post('/reorder/draft', supplierId ? { supplier_id: supplierId } : {})
export const listReorders = (params) => request(`/reorder${qs(params)}`)
export const sendReorder = (orderId, edits, note) => post(`/reorder/${orderId}/send`, { edits: edits || [], note })
export const getAskExamples = () => request('/ask/examples')
export function askShop({ text, audio, speak = true } = {}) {
  if (audio) {
    const form = new FormData()
    form.append('audio', audio, `question.${extFor(audio)}`)
    return request(`/ask${qs({ speak })}`, { method: 'POST', body: form })
  }
  return post(`/ask${qs({ speak })}`, { text })
}

// WhatsApp orders placed by customers
export const listWaOrders = (status) => request(`/wa/orders${qs({ status })}`)
export const confirmWaOrder = (id) => post(`/wa/orders/${id}/confirm`)
export const cancelWaOrder = (id) => post(`/wa/orders/${id}/cancel`)
