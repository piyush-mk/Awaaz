// Exercises every function in src/api/client.js against a live backend, without a browser.
//   cd backend && DATABASE_URL=sqlite:////tmp/x.sqlite DEMO_MODE=on .venv/bin/uvicorn main:app --port 8000
//   node frontend/scripts/check-api.mjs [http://localhost:8000]
// Prints PASS / FAIL per step and the client.js functions that no step called.

const BASE = process.argv[2] || process.env.API_BASE || 'http://localhost:8000'
globalThis.__AWAAZ_API_BASE__ = BASE

const api = await import('../src/api/client.js')
const { toPath } = await import('../src/lib/format.js')

const used = new Set()
const A = new Proxy(api, { get: (t, k) => (used.add(k), t[k]) })

let passed = 0
let failed = 0
const failures = []
async function step(name, fn) {
  try {
    const note = await fn()
    passed += 1
    console.log(`PASS  ${name}${note ? `  (${note})` : ''}`)
  } catch (e) {
    failed += 1
    failures.push(name)
    console.log(`FAIL  ${name}\n      ${e.message}`)
  }
}
function ok(cond, msg) {
  if (!cond) throw new Error(msg || 'assertion failed')
}
const jpg = () => new File([new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 1, 2, 3, 4, 5, 6, 7, 8])], 'photo.jpg', { type: 'image/jpeg' })
const audio = () => new Blob([new Uint8Array(2048).fill(7)], { type: 'audio/webm' })
const sid = `check-${Math.random().toString(36).slice(2, 8)}`

// --- live event stream (SSE) read with fetch, since Node has no EventSource ---------------------------------
const events = []
const ac = new AbortController()
;(async () => {
  try {
    const res = await fetch(`${BASE}/api/events?channel=store`, { signal: ac.signal })
    const dec = new TextDecoder()
    let buf = ''
    for await (const chunk of res.body) {
      buf += dec.decode(chunk, { stream: true })
      let i
      while ((i = buf.indexOf('\n\n')) >= 0) {
        const block = buf.slice(0, i)
        buf = buf.slice(i + 2)
        const ev = /event: (.*)/.exec(block)?.[1]
        const data = /data: (.*)/.exec(block)?.[1]
        if (ev && data) events.push({ ev, data: JSON.parse(data) })
      }
    }
  } catch {
    // aborted
  }
})()
const waitEvent = async (type, pred = () => true, ms = 4000) => {
  const t0 = Date.now()
  while (Date.now() - t0 < ms) {
    const e = events.find((x) => x.ev === type && pred(x.data))
    if (e) return e.data
    await new Promise((r) => setTimeout(r, 50))
  }
  throw new Error(`no ${type} event within ${ms} ms`)
}

console.log(`API base ${BASE}   session ${sid}\n`)

// --- admin ------------------------------------------------------------------------------------------------
await step('getStatus', async () => {
  const s = await A.getStatus()
  ok(s.store, 'no store name')
  return s.store
})
await step('getHealth', async () => {
  const h = await A.getHealth()
  ok(h && typeof h === 'object')
})

// --- counter: utterances, cart ----------------------------------------------------------------------------
let res
await step('sendUtterance text -> cart Rs 249 (+ cart_updated SSE)', async () => {
  res = await A.sendUtterance({ text: 'do maggi ek surf excel chaar colgate', sessionId: sid })
  ok(res.cart.total === 249, `total ${res.cart.total}`)
  ok(res.cart.lines.length === 3)
  const ev = await waitEvent('cart_updated', (d) => d.session_id === sid)
  ok(ev.cart.total === 249, 'SSE cart total')
  return `${res.source} ${res.latency_ms} ms`
})
await step('sendUtterance audio blob', async () => {
  const r = await A.sendUtterance({ audio: audio(), sessionId: `${sid}-audio`, filename: 'utterance.webm' })
  ok(typeof r.transcript === 'string', 'no transcript')
  return `"${r.transcript}"`
})
await step('sendUtterance loose "bees rupaye ki cheeni" -> 450 gram tolo', async () => {
  const r = await A.sendUtterance({ text: 'bees rupaye ki cheeni', sessionId: `${sid}-loose` })
  ok(r.cart.lines[0].weigh_instruction === '450 gram tolo', r.cart.lines[0].weigh_instruction)
})
await step('sendUtterance "galat hai" undo', async () => {
  const r = await A.sendUtterance({ text: 'galat hai', sessionId: `${sid}-loose` })
  ok(r.control === 'undo')
  const c = await A.getCart(`${sid}-loose`)
  ok(c.lines.length === 0, 'cart not emptied')
})
await step('getCart', async () => ok((await A.getCart(sid)).total === 249))
await step('createCart', async () => ok((await A.createCart({ session_id: `${sid}-new` })).status === 'open'))
await step('addCartLines (set mode, by name)', async () => {
  const c = await A.addCartLines(`${sid}-new`, [{ name: 'Parle-G', qty: 3 }], 'add')
  ok(c.total === 30, `total ${c.total}`)
  const c2 = await A.addCartLines(`${sid}-new`, [{ name: 'Parle-G', qty: 5 }], 'set')
  ok(c2.total === 50)
})
await step('setCartLineQty / removeCartLine', async () => {
  const c = await A.setCartLineQty(`${sid}-new`, 9, 2)
  ok(c.total === 20, `total ${c.total}`)
  const c2 = await A.removeCartLine(`${sid}-new`, 9)
  ok(c2.lines.length === 0)
})
let usualCustomer
await step('listKhataCustomers (and find one with a usual basket)', async () => {
  const list = await A.listKhataCustomers({ sort: 'name' })
  ok(list.length >= 5)
  for (const c of list) {
    try {
      const u = await api.getUsual(c.id)
      if (u.lines.length) {
        usualCustomer = c
        break
      }
    } catch {
      // keep looking
    }
  }
  return `${list.length} customers, usual: ${usualCustomer?.name || 'none'}`
})
await step('attachCartCustomer (+ usual offer)', async () => {
  const c = usualCustomer || (await A.listKhataCustomers())[0]
  const r = await A.attachCartCustomer(`${sid}-new`, { customer_id: c.id })
  ok(r.customer.id === c.id)
  return r.usual ? `usual: ${r.usual.prompt}` : 'no usual'
})
await step('getUsual / lookupUsual / addUsualToCart', async () => {
  if (!usualCustomer) return 'skipped: no customer has a usual basket'
  const u = await A.getUsual(usualCustomer.id)
  ok(u.lines.length > 0)
  const l = await A.lookupUsual({ name: usualCustomer.name })
  ok(l.lines.length > 0)
  const c = await A.addUsualToCart(`${sid}-new`, {})
  ok(c.lines.length > 0)
})
await step('clearCart', async () => ok((await A.clearCart(`${sid}-new`)).lines.length === 0))

// --- pending actions ----------------------------------------------------------------------------------------
let udhaar
await step('utterance -> add_udhaar proposal + action_proposed SSE', async () => {
  const r = await A.sendUtterance({ text: 'Verma ji ke khate mein 500', sessionId: `${sid}-k` })
  udhaar = r.actions.find((a) => a.kind === 'add_udhaar')
  ok(udhaar && udhaar.status === 'proposed')
  await waitEvent('action_proposed', (d) => d.session_id === `${sid}-k`)
})
await step('listActions / getAction', async () => {
  const l = await A.listActions({ session_id: `${sid}-k`, status: 'proposed' })
  ok(l.some((a) => a.id === udhaar.id))
  ok((await A.getAction(udhaar.id)).id === udhaar.id)
})
await step('confirmAction (add_udhaar)', async () => {
  const r = await A.confirmAction(udhaar.id, {})
  ok(r.action.status === 'confirmed')
})
await step('cancelAction', async () => {
  const r = await A.sendUtterance({ text: 'Joshi ji ke khate mein 100', sessionId: `${sid}-k` })
  const a = r.actions.find((x) => x.status === 'proposed')
  ok(a, 'no proposal')
  const c = await A.cancelAction(a.id)
  ok(c.action.status === 'cancelled')
})

// --- checkout, QR, payment ------------------------------------------------------------------------------------
let co
await step('checkoutCart -> exact-amount UPI string (+ checkout SSE)', async () => {
  co = await A.checkoutCart(sid, {})
  ok(co.upi_string.startsWith('upi://pay?'), 'upi string')
  ok(/am=249\.00/.test(co.upi_string), 'amount in QR')
  ok(co.order_id && !co.complete)
  await waitEvent('checkout', (d) => d.order_id === co.order_id)
})
await step('getPayment (pending)', async () => ok((await A.getPayment(co.order_id)).status === 'pending'))
await step('simulatePayment -> payment_received SSE with spoken text', async () => {
  const r = await A.simulatePayment(co.order_id)
  ok(r.status === 'success' && r.invoice_paid)
  const ev = await waitEvent('payment_received', (d) => d.order_id === co.order_id)
  ok(ev.session_id === sid, 'SSE session id')
  ok(ev.spoken_text.includes('249'), ev.spoken_text)
  return ev.spoken_text
})
await step('receipt page /r/token is reachable via toPath()', async () => {
  const inv = await A.getInvoice(co.invoice_id)
  ok(inv.status === 'paid')
  const html = await (await fetch(BASE + toPath(inv.public_url))).text()
  ok(/249/.test(html), 'receipt shows total')
})
await step('listInvoices', async () => ok((await A.listInvoices({ limit: 5 })).length === 5))
await step('sendInvoice', async () => {
  const r = await A.sendInvoice(co.invoice_id, { to: '919810000002', voice: false })
  ok(r.ok)
})
await step('checkout split cash+khata (completes at once) then khata warning field', async () => {
  const s2 = `${sid}-split`
  await A.sendUtterance({ text: 'do maggi', sessionId: s2 })
  const c = await A.checkoutCart(s2, { splits: { cash: 10, khata: 14, upi: null }, customer_id: 2 })
  ok(c.complete === true, 'should complete without QR')
  ok(c.payments.length === 2)
})
await step('utterance "bas kitna hua" -> checkout proposal -> confirmAction returns QR result', async () => {
  const s3 = `${sid}-voice`
  await A.sendUtterance({ text: 'do colgate', sessionId: s3 })
  const r = await A.sendUtterance({ text: 'bas kitna hua', sessionId: s3 })
  const a = r.actions.find((x) => x.kind === 'checkout')
  ok(a, 'no checkout proposal')
  const c = await A.confirmAction(a.id)
  ok(c.result.upi_string, 'no upi_string in confirm result')
})

// --- khata ---------------------------------------------------------------------------------------------------
let cust
await step('getKhataCustomer (ledger)', async () => {
  cust = await A.getKhataCustomer(2)
  ok(cust.entries.length > 0 && cust.limit_reason)
})
await step('createKhataCustomer', async () => ok((await A.createKhataCustomer({ name: 'Check Kumar', phone: '919810099999' })).id))
let entry
await step('addKhataEntry credit -> WhatsApp text + limit warning', async () => {
  const r = await A.addKhataEntry({ customer_id: 2, kind: 'credit', amount: 300, note: 'check' })
  entry = r.entry
  ok(r.whatsapp.text.includes('Kul baaki'), 'whatsapp text')
  ok(r.warning && r.warning.over_limit, 'limit warning')
  return r.warning.message_hi
})
await step('addKhataEntry payment', async () => ok((await A.addKhataEntry({ customer_id: 2, kind: 'payment', amount: 100 })).balance_after < cust.balance + 300))
await step('confirmKhataEntry / disputeKhataEntry (+ khata_disputed SSE)', async () => {
  ok((await A.confirmKhataEntry(entry.id)).confirmed_by_customer)
  const d = await A.disputeKhataEntry(entry.id, { note: 'galat' })
  ok(d.disputed)
  await waitEvent('khata_disputed', (x) => x.entry_id === entry.id)
})
await step('previewReminders / sendReminders', async () => {
  const p = await A.previewReminders({})
  ok(p.count > 0 && p.reminders[0].text)
  const s = await A.sendReminders({ customer_ids: [2] })
  ok(s.sent.length === 1)
})
let offer
await step('offerPostpaid / getPostpaid / approvePostpaid (simulated)', async () => {
  offer = await A.offerPostpaid({ customer_id: 2, amount: 300 })
  ok(offer.simulated && offer.status === 'offered')
  ok((await A.getPostpaid(offer.offer_id)).offer_id === offer.offer_id)
  const ap = await A.approvePostpaid(offer.offer_id)
  ok(ap.status === 'approved' && ap.shop_paid_now)
})
await step('importKhataPhoto -> getKhataImport -> confirmKhataImport', async () => {
  const p = await A.importKhataPhoto(jpg())
  ok(p.rows.length > 0)
  ok((await A.getKhataImport(p.action_id)).action_id === p.action_id)
  const rows = p.rows.map((r, index) => ({ index, include: index < 2, name: r.name, amount: r.amount }))
  const c = await A.confirmKhataImport(p.action_id, rows)
  ok(c.status === 'confirmed' && c.entries.length === 2, `entries ${c.entries?.length}`)
})

// --- godown ----------------------------------------------------------------------------------------------------
await step('getStock (+ search, days_of_cover)', async () => {
  const s = await A.getStock({ sort: 'cover' })
  ok(s.items.length > 20 && 'days_of_cover' in s.items[0])
  ok((await A.getStock({ q: 'maggi' })).items.length >= 1)
})
await step('getStockCover / getProductDetail', async () => {
  ok((await A.getStockCover()).items.length > 0)
  ok((await A.getProductDetail(1)).sales_30d.length === 30)
})
await step('getStockExpiry (claim amounts)', async () => {
  const e = await A.getStockExpiry(7)
  ok(e.items.length > 0 && e.total_claim > 0)
})
await step('getMissedSales / addMissedSale', async () => {
  ok((await A.getMissedSales(7)).items.length > 0)
  const r = await A.addMissedSale('Kurkure')
  ok(r.asked_this_week >= 1)
})
await step('setPrices', async () => ok((await A.setPrices([{ name: 'Ande', price: 7 }])).updated.length === 1))
let scan
await step('scanPurchase -> flags + message_hi', async () => {
  scan = await A.scanPurchase(jpg())
  const codes = new Set(scan.flags.map((f) => f.code))
  ok(codes.has('price_increase') && codes.has('scheme_missed') && codes.has('expiry_soon') && codes.has('new_product'), [...codes].join(','))
  ok(scan.message_hi)
  return `${scan.lines.length} lines, flags ${[...codes].join('/')}`
})
await step('confirmPurchase (qty edit, free qty)', async () => {
  const r = await A.confirmPurchase(scan.action_id, { lines: [{ index: 0, qty: 11, free_qty: 1 }], create_new_products: true })
  ok(r.status === 'confirmed' && r.stock_updates.length > 5)
})
await step('cancelPurchase', async () => {
  const s = await A.scanPurchase(jpg())
  ok((await A.cancelPurchase(s.action_id)).status === 'cancelled')
})
await step('listPurchases / listSuppliers', async () => {
  ok((await A.listPurchases()).length >= 1)
  ok((await A.listSuppliers()).length >= 3)
})
let audit
await step('shelfAudit (2 photos) -> rows + loss', async () => {
  audit = await A.shelfAudit([jpg(), jpg()])
  ok(audit.rows.length > 0 && audit.totals.loss_value < 0)
})
await step('confirmShelfAudit (corrected count)', async () => {
  const r = await A.confirmShelfAudit(audit.action_id, { counts: { [audit.rows[0].product_id]: audit.rows[0].expected } })
  ok(r.status === 'confirmed')
})
await step('cancelShelfAudit', async () => {
  const a = await A.shelfAudit([jpg()])
  ok((await A.cancelShelfAudit(a.action_id)).status === 'cancelled')
})
await step('parseParchi -> push lines into cart', async () => {
  const p = await A.parseParchi(jpg())
  ok(p.lines.length > 0 && p.message_hi)
  const c = await A.addCartLines(`${sid}-parchi`, p.lines.map((l) => ({ product_id: l.product_id, qty: l.qty, unit: l.unit })), 'add')
  ok(c.lines.length === p.lines.length, `${c.lines.length} vs ${p.lines.length}`)
})

// --- hisaab ----------------------------------------------------------------------------------------------------
await step('getDashboardV2', async () => {
  const d = await A.getDashboardV2()
  ok(d.today.sales > 0 && d.series.length === 14 && d.payment_split && d.hourly.length > 0)
  return `today ${d.today.sales}`
})
let exp
await step('getGallaExpected', async () => {
  exp = await A.getGallaExpected()
  ok(exp.expected > 0)
  return `expected ${exp.expected}`
})
let gs
await step('scanGalla -> denominations', async () => {
  gs = await A.scanGalla(jpg())
  ok(gs.denominations['500'] != null && gs.table.length === 8)
})
await step('closeGalla -> "hona chahiye tha ... kam" + speech', async () => {
  const r = await A.closeGalla(gs.denominations)
  ok(/hona chahiye tha/.test(r.message_hi), r.message_hi)
  await waitEvent('galla_closed', () => true)
  return r.message_hi
})
await step('getGallaHistory', async () => ok((await A.getGallaHistory()).items.length >= 1))

// --- salaah ------------------------------------------------------------------------------------------------------
await step('getBrief (facts, sentences, festival)', async () => {
  const b = await A.getBrief()
  ok(b.sentences.length >= 3 && b.facts.festival)
})
await step('speakBrief / playBrief (+ brief_ready SSE)', async () => {
  const s = await A.speakBrief()
  ok(s.text)
  await A.speakBrief('namaste')
  const p = await A.playBrief()
  ok(p.published)
  await waitEvent('brief_ready', () => true)
})
let po
await step('draftReorder -> per-supplier POs with festival multipliers', async () => {
  const d = await A.draftReorder()
  ok(d.orders.length >= 2)
  po = d.orders.find((o) => o.festival) || d.orders[0]
  ok(po.lines.some((l) => l.multiplier > 1), 'no festival multiplier on any line')
  ok((await A.draftReorder(po.supplier_id)).orders.length === 1)
})
await step('listReorders / sendReorder (edited qty)', async () => {
  const l = await A.listReorders({ status: 'proposed' })
  ok(l.orders.length >= 1)
  const target = l.orders[0]
  const r = await A.sendReorder(target.action_id, [{ product_id: target.lines[0].product_id, qty: 12 }], 'check')
  ok(r.status === 'sent' && /12/.test(r.message.body), r.message?.body)
})
await step('getMunimExamples / askMunim (text) -> answer + table', async () => {
  ok((await A.getMunimExamples()).examples.length >= 5)
  const r = await A.askMunim({ text: 'is hafte sabse zyada kya bika' })
  ok(r.answer && r.table.rows.length > 0)
})
await step('askMunim (audio)', async () => {
  const r = await A.askMunim({ audio: audio() })
  ok(r.answer)
})

// --- whatsapp orders ----------------------------------------------------------------------------------------------
await step('listWaOrders / confirmWaOrder / cancelWaOrder', async () => {
  const sim = (body) =>
    fetch(`${BASE}/api/wa/simulate-inbound`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ customer_id: 2, type: 'text', body }) }).then((r) => r.json())
  const o1 = await sim('2 maggi aur 1 kilo cheeni')
  const o2 = await sim('1 surf excel')
  ok(o1.action_id && o2.action_id)
  const l = await A.listWaOrders('proposed')
  ok(l.some((o) => o.id === o1.action_id))
  ok((await A.confirmWaOrder(o1.action_id)).status === 'confirmed')
  ok((await A.cancelWaOrder(o2.action_id)).status === 'cancelled')
  // "Bill banao" path: lines into the counter cart
  const c = await A.addCartLines(`${sid}-wa`, l.find((o) => o.id === o1.action_id).payload.lines.map((x) => ({ product_id: x.product_id, qty: x.qty, unit: x.unit })), 'add')
  ok(c.lines.length === 2)
})

// --- legacy exports still working ---------------------------------------------------------------------------------
await step('legacy: parseVoice / textToSpeech', async () => {
  const p = await A.parseVoice(null, 'do maggi ek surf excel')
  ok(p)
  ok(await A.textToSpeech('namaste'))
})
await step('legacy: getInventory / restockInventory / editInventory / addProduct', async () => {
  const inv = await A.getInventory()
  ok(inv.length > 5)
  const pid = inv[0].product_id
  ok(await A.restockInventory([{ product_id: pid, name: inv[0].name, quantity: 1, unit: inv[0].unit, price: inv[0].price }]))
  ok(await A.editInventory(pid, inv[0].quantity))
  ok(await A.addProduct(`Check Item ${sid}`, 5, 'unit', 10, 5))
})
await step('legacy: generateBill / confirmBill', async () => {
  const b = await A.generateBill([{ product_id: 1, name: 'Maggi', quantity: 2, unit: 'packet', price: 12, gst_rate: 5 }])
  ok(b && b.items?.length === 1, 'bill has items')
  ok(await A.confirmBill(b.items, b.grand_total))
})
await step('legacy: parsePhoto', async () => ok(await A.parsePhoto(jpg())))
await step('legacy: getDashboard / getAlerts / getTransactions', async () => {
  ok(await A.getDashboard())
  ok(await A.getAlerts())
  ok(await A.getTransactions(5))
})

ac.abort()

const exported = Object.keys(api).filter((k) => typeof api[k] === 'function')
const unused = exported.filter((k) => !used.has(k))
console.log(`\n${passed} passed, ${failed} failed. client.js exports: ${exported.length}, called: ${exported.length - unused.length}`)
if (unused.length) console.log(`NOT CALLED: ${unused.join(', ')}`)
if (failed) console.log(`FAILED: ${failures.join(' | ')}`)
process.exit(failed || unused.length ? 1 : 0)
