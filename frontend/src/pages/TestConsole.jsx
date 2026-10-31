import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronDown, ChevronRight, Copy, Pause, Play, Trash2, Zap } from 'lucide-react'
import FullPage, { CYAN, INK } from '../components/sb/FullPage'
import { getAdminHealth, rawRequest } from '../api/sideClient'

/* Engineering console for every v2 endpoint group. Pick a recipe, tweak the path / JSON / form,
   press Run, read the raw response. Ids returned by one call ({order_id}, {action_id}, ...) are
   remembered in the context strip and substituted into later paths. Dense on purpose. */

const J = (o) => JSON.stringify(o, null, 2)
const PHRASES = {
  1: 'do maggi ek surf excel chaar colgate',
  2: 'das packet maggi paanch kilo chawal do litre tel',
  3: 'aashirvaad atta teen bag tata namak chaar packet',
  4: 'paanch dettol sabun teen vim bar do parle g',
  5: 'ek patanjali shahad do colgate',
  6: 'bhaiya do maggi ek surf aur bees rupaye ki cheeni',
  7: 'verma ji ke khate mein paanch sau',
  8: 'teen sau cash diya do sau paytm baaki khate mein',
  9: 'kurkure nahi hai',
  10: 'bas kitna hua',
}
const VERMA = '919810000002'

// kind of body: json (string), form ([[key, default]]), none. file: {name, accept, dummy?}
const RECIPES = [
  { g: 'Agent', id: 'utt-text', label: 'Utterance: text', m: 'POST', p: '/api/agent/utterance', form: [['text', PHRASES[1]], ['session_id', '{session}'], ['context', 'counter'], ['speak', 'true']] },
  { g: 'Agent', id: 'utt-audio', label: 'Utterance: audio + X-Demo-Phrase', m: 'POST', p: '/api/agent/utterance', form: [['session_id', '{session}'], ['context', 'counter'], ['speak', 'true']], file: { name: 'audio', accept: 'audio/*', dummy: true }, phrase: '1', note: 'No file chosen: a dummy blob is sent. In DEMO_MODE the header picks the transcript (1..10).' },
  { g: 'Agent', id: 'act-list', label: 'Actions: proposed', m: 'GET', p: '/api/actions?status=proposed' },
  { g: 'Agent', id: 'act-confirm', label: 'Action: confirm', m: 'POST', p: '/api/actions/{action_id}/confirm', json: '{}' },
  { g: 'Agent', id: 'act-cancel', label: 'Action: cancel', m: 'POST', p: '/api/actions/{action_id}/cancel', json: '{}' },

  { g: 'Cart', id: 'cart-get', label: 'Get cart', m: 'GET', p: '/api/cart/{session}' },
  { g: 'Cart', id: 'cart-add', label: 'Add lines', m: 'POST', p: '/api/cart/{session}/lines', json: J({ items: [{ name: 'maggi', qty: 2 }, { name: 'surf excel', qty: 1 }, { name: 'colgate', qty: 4 }], mode: 'add' }) },
  { g: 'Cart', id: 'cart-loose', label: 'Add by amount (cheeni 20)', m: 'POST', p: '/api/cart/{session}/lines', json: J({ items: [{ name: 'cheeni', amount_rupees: 20 }], mode: 'add' }) },
  { g: 'Cart', id: 'cart-qty', label: 'Set quantity', m: 'PUT', p: '/api/cart/{session}/lines/1', json: J({ qty: 3 }) },
  { g: 'Cart', id: 'cart-rm', label: 'Remove line', m: 'DELETE', p: '/api/cart/{session}/lines/1' },
  { g: 'Cart', id: 'cart-clear', label: 'Clear cart', m: 'DELETE', p: '/api/cart/{session}' },
  { g: 'Cart', id: 'cart-cust', label: 'Attach customer', m: 'POST', p: '/api/cart/{session}/customer', json: J({ name: 'sharma' }) },
  { g: 'Cart', id: 'cart-usual', label: 'Add usual basket', m: 'POST', p: '/api/cart/{session}/usual', json: '{}' },
  { g: 'Cart', id: 'cart-checkout', label: 'Checkout (UPI QR)', m: 'POST', p: '/api/cart/{session}/checkout', json: J({ speak: true }) },
  { g: 'Cart', id: 'cart-split', label: 'Checkout: split cash + khata', m: 'POST', p: '/api/cart/{session}/checkout', json: J({ splits: { cash: 100, khata: null, customer_id: 2 } }) },

  { g: 'Payments', id: 'pay-get', label: 'Payment status', m: 'GET', p: '/api/payments/{order_id}' },
  { g: 'Payments', id: 'pay-sim', label: 'Simulate "payment aa gaya"', m: 'POST', p: '/api/payments/{order_id}/simulate' },
  { g: 'Payments', id: 'pay-hook', label: 'Webhook SUCCESS', m: 'POST', p: '/api/payments/webhook', json: J({ order_id: '{order_id}', status: 'SUCCESS' }) },
  { g: 'Payments', id: 'inv-list', label: 'Invoices', m: 'GET', p: '/api/invoices?limit=10' },
  { g: 'Payments', id: 'inv-get', label: 'Invoice', m: 'GET', p: '/api/invoices/{invoice_id}' },
  { g: 'Payments', id: 'inv-send', label: 'Resend receipt (text + voice)', m: 'POST', p: '/api/invoices/{invoice_id}/send', json: J({ to: VERMA, voice: true }) },

  { g: 'Khata', id: 'k-list', label: 'Customers', m: 'GET', p: '/api/khata/customers' },
  { g: 'Khata', id: 'k-one', label: 'Customer 2 (Verma ji)', m: 'GET', p: '/api/khata/customers/2' },
  { g: 'Khata', id: 'k-credit', label: 'Give udhaar', m: 'POST', p: '/api/khata/entries', json: J({ customer_id: 2, kind: 'credit', amount: 500, note: 'test', send_whatsapp: true }) },
  { g: 'Khata', id: 'k-pay', label: 'Receive payment', m: 'POST', p: '/api/khata/entries', json: J({ customer_id: 2, kind: 'payment', amount: 200, send_whatsapp: true }) },
  { g: 'Khata', id: 'k-confirm', label: 'Entry: confirm', m: 'POST', p: '/api/khata/entries/{entry_id}/confirm', json: J({ confirmed: true }) },
  { g: 'Khata', id: 'k-dispute', label: 'Entry: dispute', m: 'POST', p: '/api/khata/entries/{entry_id}/dispute', json: J({ note: 'galat' }) },
  { g: 'Khata', id: 'k-rem-prev', label: 'Reminders: preview', m: 'POST', p: '/api/khata/reminders/preview', json: '{}' },
  { g: 'Khata', id: 'k-rem-send', label: 'Reminders: send', m: 'POST', p: '/api/khata/reminders/send', json: '{}' },
  { g: 'Khata', id: 'k-pp-offer', label: 'Postpaid: offer (simulated)', m: 'POST', p: '/api/khata/postpaid/offer', json: J({ customer_id: 2, amount: 500, send_whatsapp: true }) },
  { g: 'Khata', id: 'k-pp-get', label: 'Postpaid: get', m: 'GET', p: '/api/khata/postpaid/{offer_id}' },
  { g: 'Khata', id: 'k-pp-ok', label: 'Postpaid: approve', m: 'POST', p: '/api/khata/postpaid/{offer_id}/approve' },
  { g: 'Khata', id: 'k-import', label: 'Notebook photo import', m: 'POST', p: '/api/khata/import-photo', form: [], file: { name: 'image', accept: 'image/*', dummy: 'image' } },
  { g: 'Khata', id: 'k-import-ok', label: 'Import: confirm', m: 'POST', p: '/api/khata/import/{action_id}/confirm', json: '{}' },

  { g: 'Purchases', id: 'pu-scan', label: 'Scan distributor bill', m: 'POST', p: '/api/purchases/scan', form: [], file: { name: 'image', accept: 'image/*', dummy: 'image' }, note: 'DEMO_MODE returns the Rajesh Distributors fixture whatever the image is.' },
  { g: 'Purchases', id: 'pu-ok', label: 'Bill: confirm', m: 'POST', p: '/api/purchases/{action_id}/confirm', json: '{}' },
  { g: 'Purchases', id: 'pu-no', label: 'Bill: cancel', m: 'POST', p: '/api/purchases/{action_id}/cancel', json: '{}' },
  { g: 'Purchases', id: 'pu-list', label: 'Purchase bills', m: 'GET', p: '/api/purchases' },
  { g: 'Purchases', id: 'pu-sup', label: 'Suppliers', m: 'GET', p: '/api/suppliers' },

  { g: 'Galla', id: 'g-exp', label: 'Expected cash', m: 'GET', p: '/api/galla/expected' },
  { g: 'Galla', id: 'g-scan', label: 'Scan cash photo', m: 'POST', p: '/api/galla/scan', form: [], file: { name: 'image', accept: 'image/*', dummy: 'image' } },
  { g: 'Galla', id: 'g-close', label: 'Close day', m: 'POST', p: '/api/galla/close', json: J({ denominations: { 500: 10, 100: 10, 50: 10, 20: 10, 10: 10 }, speak: true }) },
  { g: 'Galla', id: 'g-hist', label: 'History', m: 'GET', p: '/api/galla/history' },

  { g: 'Stock', id: 's-all', label: 'Stock list', m: 'GET', p: '/api/stock' },
  { g: 'Stock', id: 's-cover', label: 'Days of cover', m: 'GET', p: '/api/stock/cover' },
  { g: 'Stock', id: 's-exp', label: 'Expiry', m: 'GET', p: '/api/stock/expiry' },
  { g: 'Stock', id: 's-miss', label: 'Missed sales', m: 'GET', p: '/api/stock/missed' },
  { g: 'Stock', id: 's-miss-add', label: 'Record missed sale', m: 'POST', p: '/api/stock/missed', json: J({ product_name: 'Kurkure' }) },
  { g: 'Stock', id: 's-price', label: 'Set today prices', m: 'POST', p: '/api/stock/prices', json: J({ items: [{ name: 'ande', price: 7 }] }) },
  { g: 'Stock', id: 's-prod', label: 'Product 1 detail', m: 'GET', p: '/api/stock/product/1' },

  { g: 'Brief', id: 'b-today', label: 'Brief today', m: 'GET', p: '/api/brief/today' },
  { g: 'Brief', id: 'b-play', label: 'Brief: play on Soundbox', m: 'POST', p: '/api/brief/play' },
  { g: 'Brief', id: 'b-speak', label: 'Brief: speak text', m: 'POST', p: '/api/brief/speak', json: J({ text: 'Namaste Ramesh ji. Aaj Dhanteras ki taiyari karein.' }) },
  { g: 'Brief', id: 'r-draft', label: 'Reorder: draft POs', m: 'POST', p: '/api/reorder/draft', json: '{}' },
  { g: 'Brief', id: 'r-list', label: 'Reorder: list', m: 'GET', p: '/api/reorder' },
  { g: 'Brief', id: 'r-send', label: 'Reorder: send to supplier', m: 'POST', p: '/api/reorder/{action_id}/send', json: '{}' },
  { g: 'Brief', id: 'm-ask', label: 'Ask (text)', m: 'POST', p: '/api/munim/ask', json: J({ text: 'is hafte sabse zyada kya bika' }) },
  { g: 'Brief', id: 'm-ask-a', label: 'Ask (audio + phrase)', m: 'POST', p: '/api/munim/ask', form: [], file: { name: 'audio', accept: 'audio/*', dummy: true }, phrase: '' },
  { g: 'Brief', id: 'm-ex', label: 'Ask examples', m: 'GET', p: '/api/munim/examples' },

  { g: 'WhatsApp', id: 'w-status', label: 'Status', m: 'GET', p: '/api/wa/status' },
  { g: 'WhatsApp', id: 'w-conv', label: 'Conversations', m: 'GET', p: '/api/wa/conversations' },
  { g: 'WhatsApp', id: 'w-msgs', label: 'Messages (phone)', m: 'GET', p: `/api/wa/messages?phone=${VERMA}` },
  { g: 'WhatsApp', id: 'w-send', label: 'Merchant send', m: 'POST', p: '/api/wa/send', json: J({ customer_id: 2, body: 'Namaste Verma ji, aapka saaman taiyaar hai.' }) },
  { g: 'WhatsApp', id: 'w-in-text', label: 'Inbound: text order', m: 'POST', p: '/api/wa/simulate-inbound', form: [['from_phone', VERMA], ['type', 'text'], ['body', '2 kg cheeni aur ek surf bhej do']] },
  { g: 'WhatsApp', id: 'w-in-reply', label: 'Inbound: khata reply', m: 'POST', p: '/api/wa/simulate-inbound', form: [['from_phone', VERMA], ['type', 'text'], ['body', 'galat hai']] },
  { g: 'WhatsApp', id: 'w-in-vt', label: 'Inbound: voice (typed transcript)', m: 'POST', p: '/api/wa/simulate-inbound', form: [['from_phone', '919810000004'], ['type', 'audio'], ['body', 'bhaiya mahine ka ration bhej do atta do bag'], ['demo_phrase', '']] },
  { g: 'WhatsApp', id: 'w-in-va', label: 'Inbound: voice file', m: 'POST', p: '/api/wa/simulate-inbound', form: [['from_phone', '919810000004'], ['type', 'audio'], ['demo_phrase', '1']], file: { name: 'file', accept: 'audio/*', dummy: true } },
  { g: 'WhatsApp', id: 'w-in-img', label: 'Inbound: photo (parchi)', m: 'POST', p: '/api/wa/simulate-inbound', form: [['from_phone', '919810000004'], ['type', 'image'], ['body', 'parchi']], file: { name: 'file', accept: 'image/*', dummy: 'image' } },
  { g: 'WhatsApp', id: 'w-orders', label: 'WA orders', m: 'GET', p: '/api/wa/orders' },
  { g: 'WhatsApp', id: 'w-ord-ok', label: 'WA order: confirm', m: 'POST', p: '/api/wa/orders/{action_id}/confirm' },

  { g: 'Admin', id: 'a-health', label: 'Health', m: 'GET', p: '/api/admin/health' },
  { g: 'Admin', id: 'a-health-l', label: 'Health (live pings)', m: 'GET', p: '/api/admin/health?live=1' },
  { g: 'Admin', id: 'a-status', label: 'Status', m: 'GET', p: '/api/admin/status' },
  { g: 'Admin', id: 'a-check', label: 'Demo checklist', m: 'GET', p: '/api/admin/demo-checklist' },
  { g: 'Admin', id: 'a-reset', label: 'Reset demo data', m: 'POST', p: '/api/admin/reset-demo', confirm: 'Reset ALL demo data?' },

  { g: 'Legacy', id: 'l-inv', label: 'Inventory', m: 'GET', p: '/api/inventory' },
  { g: 'Legacy', id: 'l-dash', label: 'Dashboard', m: 'GET', p: '/api/dashboard' },
  { g: 'Legacy', id: 'l-alerts', label: 'Alerts', m: 'GET', p: '/api/alerts' },
  { g: 'Legacy', id: 'l-tx', label: 'Transactions', m: 'GET', p: '/api/transactions' },
  { g: 'Legacy', id: 'l-parse', label: 'Voice parse (transcript)', m: 'POST', p: '/api/voice/parse', form: [['transcript', PHRASES[1]]] },
  { g: 'Legacy', id: 'l-tts', label: 'TTS', m: 'POST', p: '/api/voice/tts', json: J({ text: 'Bill ban gaya. Do sau untaalis rupaye.' }) },
]

const GROUPS = [...new Set(RECIPES.map((r) => r.g))]

const STORE_EVENTS = [
  'cart_updated', 'utterance', 'action_proposed', 'action_resolved', 'checkout', 'payment_received', 'payment_failed',
  'brief_ready', 'reorder_sent', 'khata_updated', 'khata_disputed', 'khata_confirmed', 'khata_imported',
  'khata_reminders_sent', 'wa_order', 'wa_order_updated', 'postpaid_offered', 'postpaid_approved', 'galla_closed',
  'stock_updated', 'demo_reset',
]
const WA_EVENTS = ['wa_message', 'wa_status']

const ts = () => new Date().toLocaleTimeString('en-IN', { hour12: false })

/** ids worth remembering from any response */
function harvest(body) {
  if (!body || typeof body !== 'object') return {}
  const out = {}
  const put = (k, v) => v != null && v !== '' && typeof v !== 'object' && (out[k] = String(v))
  put('order_id', body.order_id)
  put('invoice_id', body.invoice_id)
  put('action_id', body.action_id ?? body.actions?.[0]?.id ?? body.action?.id ?? body.orders?.[0]?.action_id ?? body.order?.action_id)
  put('entry_id', body.entry?.id ?? body.entry_id)
  put('offer_id', body.offer_id)
  return out
}

function dummyFile(kind) {
  if (kind === 'image') {
    // 1x1 PNG
    const b = atob('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')
    return new File([Uint8Array.from(b, (c) => c.charCodeAt(0))], 'dummy.png', { type: 'image/png' })
  }
  return new File([new Uint8Array(2048)], 'speech.webm', { type: 'audio/webm' })
}

function JsonView({ value }) {
  const text = typeof value === 'string' ? value : JSON.stringify(value, null, 2)
  return (
    <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap break-words rounded-lg bg-[#0B1220] p-3 font-mono text-[12.5px] leading-relaxed text-[#D6E2F0]">
      {text}
    </pre>
  )
}

function LogEntry({ e }) {
  const [open, setOpen] = useState(e.open)
  const color = e.ok ? '#1B7F3B' : '#B3261E'
  return (
    <li className="rounded-xl border bg-white" style={{ borderColor: e.ok ? '#CDE9D5' : '#F2C5C1' }}>
      <div className="flex items-center gap-2 px-3 py-2">
        <button type="button" onClick={() => setOpen((v) => !v)} className="grid h-8 w-8 place-items-center rounded hover:bg-slate-100" aria-expanded={open} aria-label="Toggle response">
          {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        </button>
        <span className="rounded px-2 py-0.5 text-xs font-bold text-white" style={{ background: color }}>{e.status || 'ERR'}</span>
        <span className="font-mono text-xs font-bold">{e.method}</span>
        <span className="min-w-0 flex-1 truncate font-mono text-xs" title={e.path}>{e.path}</span>
        <span className="text-xs tabular-nums text-slate-600">{e.ms} ms · {e.time}</span>
        <button
          type="button"
          onClick={() => navigator.clipboard?.writeText(typeof e.body === 'string' ? e.body : JSON.stringify(e.body, null, 2))}
          className="grid h-8 w-8 place-items-center rounded hover:bg-slate-100"
          aria-label="Copy response"
          title="Copy response"
        >
          <Copy size={14} />
        </button>
      </div>
      {e.sent && <div className="truncate px-3 pb-1 font-mono text-[11px] text-slate-600" title={e.sent}>sent: {e.sent}</div>}
      {open && <div className="px-3 pb-3"><JsonView value={e.body} /></div>}
    </li>
  )
}

function EventTap() {
  const [events, setEvents] = useState([])
  const [paused, setPaused] = useState(false)
  const pausedRef = useRef(false)
  pausedRef.current = paused
  const [open, setOpen] = useState(null)
  const n = useRef(0)

  useEffect(() => {
    const sources = [
      ['store', STORE_EVENTS],
      ['wa', WA_EVENTS],
    ].map(([channel, types]) => {
      const es = new EventSource(`/api/events?channel=${channel}`)
      types.forEach((t) =>
        es.addEventListener(t, (ev) => {
          if (pausedRef.current) return
          let data = ev.data
          try {
            data = JSON.parse(ev.data)
          } catch {
            /* raw */
          }
          n.current += 1
          const key = n.current
          setEvents((list) => [{ key, channel, type: t, id: ev.lastEventId, time: ts(), data }, ...list].slice(0, 80))
        }),
      )
      return es
    })
    return () => sources.forEach((s) => s.close())
  }, [])

  return (
    <section className="flex min-h-0 flex-col rounded-2xl bg-white shadow-sm" aria-label="Live events">
      <div className="flex items-center gap-2 border-b px-3 py-2" style={{ borderColor: '#E3E8EF' }}>
        <h2 className="flex-1 text-sm font-bold uppercase tracking-wide">Live events (SSE)</h2>
        <button type="button" onClick={() => setPaused((p) => !p)} className="grid h-9 w-9 place-items-center rounded hover:bg-slate-100" aria-label={paused ? 'Resume' : 'Pause'}>
          {paused ? <Play size={16} /> : <Pause size={16} />}
        </button>
        <button type="button" onClick={() => setEvents([])} className="grid h-9 w-9 place-items-center rounded hover:bg-slate-100" aria-label="Clear events">
          <Trash2 size={16} />
        </button>
      </div>
      <ul className="min-h-0 flex-1 overflow-y-auto">
        {events.length === 0 && <li className="p-4 text-sm text-slate-600">Waiting for events. Old events replay on connect; new ones appear on top.</li>}
        {events.map((e) => (
          <li key={e.key} className="border-b px-3 py-1.5 text-xs" style={{ borderColor: '#EEF1F5' }}>
            <button type="button" className="flex w-full items-center gap-2 text-left" onClick={() => setOpen(open === e.key ? null : e.key)}>
              <span className="rounded px-1.5 py-0.5 font-bold" style={{ background: e.channel === 'wa' ? '#DDF5E4' : '#E1F3FB', color: e.channel === 'wa' ? '#0F5A2A' : '#0B4A66' }}>{e.channel}</span>
              <span className="font-mono font-bold">{e.type}</span>
              <span className="ml-auto tabular-nums text-slate-600">#{e.id} {e.time}</span>
            </button>
            {open === e.key ? (
              <pre className="mt-1 max-h-72 overflow-auto whitespace-pre-wrap break-words rounded bg-[#0B1220] p-2 font-mono text-[11.5px] text-[#D6E2F0]">{JSON.stringify(e.data, null, 2)}</pre>
            ) : (
              <div className="truncate font-mono text-[11px] text-slate-600">{typeof e.data === 'string' ? e.data : JSON.stringify(e.data)}</div>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

export default function TestConsole() {
  const [ctx, setCtx] = useState({ session: 'default', order_id: '', action_id: '', invoice_id: '', entry_id: '', offer_id: '' })
  const [sel, setSel] = useState('utt-text')
  const [open, setOpen] = useState({ Agent: true })
  const [edits, setEdits] = useState({})
  const [files, setFiles] = useState({})
  const [log, setLog] = useState([])
  const [busy, setBusy] = useState(false)
  const [healthDot, setHealthDot] = useState(null)
  const ctxRef = useRef(ctx)
  ctxRef.current = ctx
  const counter = useRef(0)

  useEffect(() => {
    getAdminHealth(false).then((h) => setHealthDot(h.status)).catch(() => setHealthDot('down'))
  }, [])

  const recipe = RECIPES.find((r) => r.id === sel)
  const ed = useMemo(() => {
    const base = { path: recipe.p, method: recipe.m, json: recipe.json ?? null, form: recipe.form ? Object.fromEntries(recipe.form) : null, phrase: recipe.phrase ?? '' }
    return { ...base, ...(edits[recipe.id] || {}) }
  }, [recipe, edits])
  const setEd = (patch) => setEdits((e) => ({ ...e, [recipe.id]: { ...(e[recipe.id] || {}), ...patch } }))

  const fill = (s) => String(s ?? '').replace(/\{(\w+)\}/g, (_, k) => ctxRef.current[k] ?? '')

  const execute = useCallback(async (r, e) => {
    const method = e.method
    const path = fill(e.path)
    const headers = {}
    if (e.phrase) headers['X-Demo-Phrase'] = e.phrase
    const opts = { headers }
    let sent = ''
    if (e.json !== null && method !== 'GET') {
      const text = fill(e.json).trim()
      if (text) {
        try {
          JSON.parse(text)
        } catch (err) {
          return { ok: false, status: 0, ms: 0, body: { error: `Invalid JSON: ${err.message}` }, method, path }
        }
        opts.json = text
        sent = text.replace(/\s+/g, ' ').slice(0, 220)
      }
    } else if (e.form !== null || r.file) {
      const fd = new FormData()
      Object.entries(e.form || {}).forEach(([k, v]) => {
        const val = fill(v)
        if (val !== '') fd.append(k, val)
      })
      if (r.file) {
        const chosen = files[r.id]
        if (chosen) fd.append(r.file.name, chosen)
        else if (r.file.dummy) fd.append(r.file.name, dummyFile(r.file.dummy))
      }
      opts.form = fd
      sent = Object.entries(e.form || {}).map(([k, v]) => `${k}=${fill(v)}`).join('&') + (r.file ? ` +${files[r.id]?.name || 'dummy file'}` : '')
    }
    const res = await rawRequest(method, path, opts)
    return { ...res, method, path, sent: sent || (e.phrase ? `X-Demo-Phrase: ${e.phrase}` : '') }
  }, [files]) // eslint-disable-line react-hooks/exhaustive-deps

  const record = (res, openIt = true) => {
    counter.current += 1
    const key = counter.current
    setLog((l) => [{ key, time: ts(), open: openIt, ...res }, ...l].slice(0, 60))
    const found = harvest(res.body)
    if (Object.keys(found).length) setCtx((c) => ({ ...c, ...found }))
  }

  const runRecipe = async (r, e) => {
    if (r.confirm && !window.confirm(r.confirm)) return null
    setBusy(true)
    try {
      const res = await execute(r, e)
      record(res)
      return res
    } finally {
      setBusy(false)
    }
  }

  const flow = async () => {
    setBusy(true)
    try {
      const get = (id) => {
        const r = RECIPES.find((x) => x.id === id)
        return [r, { path: r.p, method: r.m, json: r.json ?? null, form: r.form ? Object.fromEntries(r.form) : null, phrase: r.phrase ?? '' }]
      }
      let [r, e] = get('utt-text')
      record(await execute(r, e), false)
      ;[r, e] = get('cart-checkout')
      const co = await execute(r, e)
      record(co, false)
      if (co.body?.order_id) ctxRef.current = { ...ctxRef.current, order_id: co.body.order_id }
      ;[r, e] = get('pay-sim')
      record(await execute(r, e), true)
    } finally {
      setBusy(false)
    }
  }

  const field = 'min-h-[40px] w-full rounded-lg border bg-white px-2.5 font-mono text-[13px]'

  return (
    <FullPage background="#ECF0F4">
      <div className="flex min-h-full flex-col">
        <header className="flex flex-wrap items-center gap-3 px-4 py-2 text-white" style={{ background: INK }}>
          <h1 className="text-lg font-bold">Awaaz test console</h1>
          <span className="rounded-full px-2.5 py-0.5 text-xs font-bold" style={{ background: healthDot === 'ok' ? '#DDF5E4' : healthDot ? '#FFF1CC' : '#33415C', color: healthDot === 'ok' ? '#0F5A2A' : healthDot ? '#5C4300' : '#fff' }}>
            health: {healthDot || '...'}
          </span>
          <nav className="ml-auto flex flex-wrap gap-1 text-sm font-semibold">
            {[['/app', 'App'], ['/soundbox', 'Soundbox'], ['/wa', 'WhatsApp'], ['/status', 'Status']].map(([to, l]) => (
              <Link key={to} to={to} className="inline-flex min-h-[44px] items-center rounded-lg px-3 hover:bg-white/15">{l}</Link>
            ))}
          </nav>
        </header>

        <div className="flex flex-wrap items-center gap-2 border-b bg-white px-4 py-2" style={{ borderColor: '#D5DCE6' }}>
          <span className="text-xs font-bold uppercase tracking-wide text-slate-600">Context</span>
          {Object.keys(ctx).map((k) => (
            <label key={k} className="flex items-center gap-1 text-xs font-semibold text-slate-700">
              {`{${k}}`}
              <input
                value={ctx[k]}
                onChange={(e) => setCtx((c) => ({ ...c, [k]: e.target.value }))}
                className="min-h-[36px] w-28 rounded border px-2 font-mono text-xs"
                aria-label={k}
              />
            </label>
          ))}
          <button
            type="button"
            onClick={flow}
            disabled={busy}
            className="ml-auto inline-flex min-h-[44px] items-center gap-2 rounded-xl px-4 text-sm font-bold disabled:opacity-60"
            style={{ background: CYAN, color: INK }}
            title="utterance -> checkout -> simulate payment, with the Soundbox open to watch"
          >
            <Zap size={16} aria-hidden="true" /> Run counter flow
          </button>
        </div>

        <div className="grid min-h-0 flex-1 gap-3 p-3 lg:grid-cols-[250px_minmax(0,1fr)_370px]">
          {/* recipes */}
          <nav className="rounded-2xl bg-white p-2 shadow-sm lg:overflow-y-auto" aria-label="Endpoints" style={{ maxHeight: 'calc(100vh - 170px)' }}>
            {GROUPS.map((g) => (
              <div key={g}>
                <button
                  type="button"
                  onClick={() => setOpen((o) => ({ ...o, [g]: !o[g] }))}
                  className="flex min-h-[40px] w-full items-center gap-1 rounded-lg px-2 text-left text-sm font-bold hover:bg-slate-100"
                  aria-expanded={!!open[g]}
                >
                  {open[g] ? <ChevronDown size={15} /> : <ChevronRight size={15} />} {g}
                  <span className="ml-auto text-xs font-medium text-slate-600">{RECIPES.filter((r) => r.g === g).length}</span>
                </button>
                {open[g] &&
                  RECIPES.filter((r) => r.g === g).map((r) => (
                    <button
                      key={r.id}
                      type="button"
                      onClick={() => setSel(r.id)}
                      aria-current={sel === r.id}
                      className="flex min-h-[36px] w-full items-center gap-2 rounded-lg py-1 pl-7 pr-2 text-left text-[13px] hover:bg-slate-100"
                      style={sel === r.id ? { background: '#E1F3FB', fontWeight: 700 } : undefined}
                    >
                      <span className="w-10 shrink-0 font-mono text-[10px] font-bold text-slate-600">{r.m}</span>
                      <span className="truncate">{r.label}</span>
                    </button>
                  ))}
              </div>
            ))}
          </nav>

          {/* editor + log */}
          <main className="flex min-h-0 min-w-0 flex-col gap-3">
            <section className="rounded-2xl bg-white p-3 shadow-sm" aria-label="Request">
              <div className="mb-2 flex items-baseline gap-2">
                <h2 className="text-base font-bold">{recipe.label}</h2>
                <span className="text-xs text-slate-600">{recipe.g}</span>
              </div>
              {recipe.note && <p className="mb-2 text-xs text-slate-700">{recipe.note}</p>}
              <div className="flex gap-2">
                <select value={ed.method} onChange={(e) => setEd({ method: e.target.value })} className="min-h-[40px] rounded-lg border bg-white px-2 font-mono text-[13px] font-bold" aria-label="Method">
                  {['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map((m) => <option key={m}>{m}</option>)}
                </select>
                <input value={ed.path} onChange={(e) => setEd({ path: e.target.value })} className={field} aria-label="Path" spellCheck={false} />
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => runRecipe(recipe, ed)}
                  className="min-h-[40px] shrink-0 rounded-lg px-5 text-sm font-bold text-white disabled:opacity-60"
                  style={{ background: INK }}
                >
                  {busy ? '...' : 'Run'}
                </button>
              </div>
              <div className="mt-1 truncate font-mono text-[11px] text-slate-600">&rarr; {fill(ed.path)}</div>

              {(recipe.phrase !== undefined || recipe.file?.dummy === true) && (
                <label className="mt-2 flex items-center gap-2 text-xs font-semibold text-slate-700">
                  X-Demo-Phrase
                  <select value={ed.phrase} onChange={(e) => setEd({ phrase: e.target.value })} className="min-h-[36px] max-w-full rounded-lg border bg-white px-2 text-xs">
                    <option value="">(none)</option>
                    {Object.entries(PHRASES).map(([k, v]) => <option key={k} value={k}>{k}: {v}</option>)}
                  </select>
                </label>
              )}

              {ed.form && Object.keys(ed.form).length > 0 && (
                <div className="mt-2 grid gap-1.5 sm:grid-cols-2">
                  {Object.entries(ed.form).map(([k, v]) => (
                    <label key={k} className="flex items-center gap-2 text-xs font-bold text-slate-700">
                      <span className="w-24 shrink-0 truncate font-mono">{k}</span>
                      <input value={v} onChange={(e) => setEd({ form: { ...ed.form, [k]: e.target.value } })} className={field} spellCheck={false} />
                    </label>
                  ))}
                </div>
              )}

              {recipe.file && (
                <label className="mt-2 flex flex-wrap items-center gap-2 text-xs font-bold text-slate-700">
                  <span className="font-mono">{recipe.file.name}</span>
                  <input
                    type="file"
                    accept={recipe.file.accept}
                    onChange={(e) => setFiles((f) => ({ ...f, [recipe.id]: e.target.files?.[0] || null }))}
                    className="text-xs"
                  />
                  <span className="font-medium text-slate-600">{files[recipe.id] ? files[recipe.id].name : recipe.file.dummy ? 'none: a dummy file is sent' : 'required'}</span>
                </label>
              )}

              {ed.json !== null && ed.method !== 'GET' && (
                <textarea
                  value={ed.json}
                  onChange={(e) => setEd({ json: e.target.value })}
                  rows={Math.min(12, Math.max(3, ed.json.split('\n').length + 1))}
                  className="mt-2 w-full rounded-lg border bg-white p-2 font-mono text-[13px]"
                  aria-label="JSON body"
                  spellCheck={false}
                />
              )}
            </section>

            <section className="min-h-0 flex-1" aria-label="Responses">
              <div className="mb-1 flex items-center">
                <h2 className="flex-1 text-sm font-bold uppercase tracking-wide">Responses ({log.length})</h2>
                <button type="button" onClick={() => setLog([])} className="inline-flex min-h-[36px] items-center gap-1 rounded-lg px-2 text-xs font-semibold hover:bg-white">
                  <Trash2 size={14} /> Clear
                </button>
              </div>
              <ul className="space-y-2 pb-6">
                {log.length === 0 && <li className="rounded-xl bg-white p-4 text-sm text-slate-600">No requests yet. Pick a recipe and press Run.</li>}
                {log.map((e) => <LogEntry key={e.key} e={e} />)}
              </ul>
            </section>
          </main>

          <div className="lg:sticky lg:top-3 lg:self-start" style={{ height: 'min(78vh, 760px)' }}>
            <EventTap />
          </div>
        </div>
      </div>
    </FullPage>
  )
}
