const BASE = '/api'

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, options)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }
  return res.json()
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
