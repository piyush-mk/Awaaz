#!/usr/bin/env node
// Proves the event contract the /soundbox and /wa screens rely on, against a running backend.
//
//   node scripts/check-events.mjs [http://localhost:8000]
//
// Use a scratch database (DATABASE_URL=sqlite:///... DEMO_MODE=on uvicorn main:app --port 8000):
// it creates a bill and a simulated payment. Connects to /api/events?channel=store and ?channel=wa,
// then drives: text utterance -> checkout -> simulate payment, and a WhatsApp inbound text.
// Prints every received event in order and exits 1 if the contract is not met.

const BASE = (process.argv[2] || process.env.BASE || 'http://localhost:8000').replace(/\/$/, '')
const SESSION = `check-${Date.now().toString(36)}`
const PHONE = '919810000002' // Verma ji in the seed

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

function openStream(channel, sink) {
  const ctrl = new AbortController()
  const done = (async () => {
    const res = await fetch(`${BASE}/api/events?channel=${channel}`, { signal: ctrl.signal, headers: { Accept: 'text/event-stream' } })
    if (!res.ok) throw new Error(`SSE ${channel}: HTTP ${res.status}`)
    const reader = res.body.getReader()
    const dec = new TextDecoder()
    let buf = ''
    for (;;) {
      const { value, done: end } = await reader.read()
      if (end) break
      buf += dec.decode(value, { stream: true })
      let i
      while ((i = buf.indexOf('\n\n')) >= 0) {
        const frame = buf.slice(0, i)
        buf = buf.slice(i + 2)
        const ev = { channel, id: null, type: 'message', data: '' }
        for (const line of frame.split('\n')) {
          if (line.startsWith('id:')) ev.id = Number(line.slice(3).trim())
          else if (line.startsWith('event:')) ev.type = line.slice(6).trim()
          else if (line.startsWith('data:')) ev.data += line.slice(5).trim()
        }
        if (!ev.data) continue
        try {
          ev.data = JSON.parse(ev.data)
        } catch {
          /* keep string */
        }
        sink(ev)
      }
    }
  })().catch((e) => {
    if (e.name !== 'AbortError') console.error(`stream ${channel} error:`, e.message)
  })
  return { close: () => ctrl.abort(), done }
}

async function post(path, { json, form } = {}) {
  const init = { method: 'POST' }
  if (json !== undefined) {
    init.headers = { 'Content-Type': 'application/json' }
    init.body = JSON.stringify(json)
  } else if (form) init.body = form
  const res = await fetch(`${BASE}${path}`, init)
  const body = await res.json().catch(() => null)
  if (!res.ok) throw new Error(`${path} -> HTTP ${res.status} ${JSON.stringify(body)}`)
  return body
}

const all = []
let armed = false
const sink = (ev) => {
  if (ev.type === 'hello') return
  all.push({ ...ev, live: armed, at: Date.now() })
}

const store = openStream('store', sink)
const wa = openStream('wa', sink)
await sleep(900) // let the stream open and the replay of old events drain
armed = true
const t0 = Date.now()

const form = new FormData()
form.append('text', 'do maggi ek surf excel chaar colgate')
form.append('session_id', SESSION)
form.append('context', 'counter')
const utt = await post('/api/agent/utterance', { form })
const co = await post(`/api/cart/${SESSION}/checkout`, { json: {} })
const paid = await post(`/api/payments/${co.order_id}/simulate`)
const wf = new FormData()
wf.append('from_phone', PHONE)
wf.append('type', 'text')
wf.append('body', 'hi')
await post('/api/wa/simulate-inbound', { form: wf })

const want = ['cart_updated', 'utterance', 'checkout', 'payment_received']
for (let i = 0; i < 40; i++) {
  const seen = new Set(all.filter((e) => e.live && (e.channel === 'wa' || e.data?.session_id === SESSION || e.data?.order_id === co.order_id)).map((e) => e.type))
  if (want.every((w) => seen.has(w)) && all.some((e) => e.live && e.type === 'wa_message')) break
  await sleep(150)
}
store.close()
wa.close()

const mine = all.filter((e) => e.live && (e.channel === 'wa' || e.data?.session_id === SESSION || e.data?.order_id === co.order_id))
const brief = (e) => {
  const d = e.data || {}
  switch (e.type) {
    case 'cart_updated':
      return `cart ${d.cart?.lines?.length} lines, total ${d.cart?.total}, status ${d.cart?.status}, stage ${d.stage}`
    case 'utterance':
      return `transcript "${d.transcript}" | spoken "${d.spoken_text}" | audio_url ${d.audio_url}`
    case 'checkout':
      return `order ${d.order_id} total ${d.total} due ${d.amount_due} complete ${d.complete} | upi ${String(d.upi_string).slice(0, 56)}... | items ${d.items?.length}`
    case 'payment_received':
      return `order ${d.order_id} amount ${d.amount} mode ${d.mode} | spoken "${d.spoken_text}" | low_stock ${(d.low_stock || []).map((l) => l.text).join('; ')} | receipt ${d.receipt_url}`
    case 'wa_message':
      return `id ${d.id} ${d.direction || 'out'} ${d.type} to ${d.to || d.from} "${String(d.body).slice(0, 50).replace(/\n/g, ' ')}"`
    case 'wa_status':
      return `id ${d.id} status ${d.status}`
    default:
      return JSON.stringify(d).slice(0, 120)
  }
}

console.log(`Backend ${BASE}, session ${SESSION}\n`)
console.log('Events received (in order):')
for (const e of mine) console.log(`  +${String(e.at - t0).padStart(4)}ms  [${e.channel}] #${e.id} ${e.type.padEnd(17)} ${brief(e)}`)

const checks = []
const has = (type, pred = () => true) => mine.find((e) => e.type === type && pred(e.data))
checks.push(['store: cart_updated with cart.lines and total', has('cart_updated', (d) => d.cart?.lines?.length === 3 && d.cart.total === 249)])
checks.push(['store: utterance with transcript + spoken_text', has('utterance', (d) => d.transcript && d.spoken_text)])
checks.push(['store: checkout with upi_string, order_id, amount_due, items', has('checkout', (d) => d.upi_string?.startsWith('upi://pay') && d.order_id && d.amount_due === 249 && d.items?.length)])
checks.push(['store: payment_received with amount, spoken_text, low_stock, receipt_url', has('payment_received', (d) => d.amount === 249 && d.spoken_text && Array.isArray(d.low_stock) && d.receipt_url)])
checks.push(['wa: wa_message arrives (inbound + packing/greeting reply)', has('wa_message')])
const order = mine.filter((e) => want.includes(e.type)).map((e) => e.type)
const idx = (t) => order.indexOf(t)
checks.push(['order: cart_updated < utterance < checkout < payment_received', idx('cart_updated') < idx('utterance') && idx('utterance') < idx('checkout') && idx('checkout') < idx('payment_received')])

console.log('\nContract:')
let ok = true
for (const [label, pass] of checks) {
  console.log(`  ${pass ? 'PASS' : 'FAIL'}  ${label}`)
  ok = ok && !!pass
}
console.log(`\nHTTP: utterance spoken_text="${utt.spoken_text}", checkout order ${co.order_id}, simulate ok=${paid.ok}`)
process.exit(ok ? 0 : 1)
