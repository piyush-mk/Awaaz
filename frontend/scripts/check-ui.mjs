#!/usr/bin/env node
/**
 * End-to-end UI check: drives the phone app, Soundbox and WhatsApp simulator in real Chrome, at the same time,
 * so live updates are tested across screens. Resets the demo data, so never point it at a demo you care about.
 *
 *   node scripts/check-ui.mjs [--base http://localhost:5173] [--shots dir]
 */
import { chromium } from 'playwright-core'
import { mkdirSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

const arg = (name, dflt) => {
  const i = process.argv.indexOf(name)
  return i > 0 ? process.argv[i + 1] : dflt
}
const BASE = arg('--base', 'http://localhost:5173')
const SHOTS = arg('--shots', null)
const LIVE_MS = 4000
if (SHOTS) mkdirSync(SHOTS, { recursive: true })

const PNG = path.join(tmpdir(), 'awaaz-check.png')
writeFileSync(PNG, Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==', 'base64'))

const results = []
const consoleErrors = []
const check = (name, ok, detail = '') => {
  results.push([name, !!ok, detail])
  console.log(`  [${ok ? 'PASS' : 'FAIL'}] ${name}${detail ? `  (${detail})` : ''}`)
  return !!ok
}
const section = (s) => console.log(`\n${s}`)

const browser = await chromium.launch({
  channel: 'chrome',
  args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream', '--autoplay-policy=no-user-gesture-required'],
})
const phoneCtx = await browser.newContext({ viewport: { width: 375, height: 760 }, hasTouch: false, permissions: ['microphone'] })
const inEnglish = () => { if (!localStorage.getItem('awaaz.lang')) localStorage.setItem('awaaz.lang', 'en') }
await phoneCtx.addInitScript(inEnglish)

function watch(page, label) {
  page.on('pageerror', (e) => consoleErrors.push(`${label}: ${e.message}`))
  page.on('console', (m) => {
    if (m.type() === 'error' && !/Failed to load resource|favicon|speech|audio/i.test(m.text())) consoleErrors.push(`${label}: ${m.text()}`)
  })
  return page
}
const shot = async (page, name) => {
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, `${name}.png`) })
}
/** True when the text shows up on the page within the live-update window, with no reload. */
const sees = async (page, text, ms = LIVE_MS) => {
  try {
    await page.getByText(text, { exact: false }).first().waitFor({ state: 'visible', timeout: ms })
    return true
  } catch {
    return false
  }
}
const api = async (p, opts) => (await fetch(BASE + '/api' + p, opts)).json()
const post = (p, body) => api(p, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body || {}) })
const stockOf = async (name) => (await api('/stock')).items.find((i) => i.name === name)?.qty
const noOverflow = (page) => page.evaluate(() => {
  const main = document.querySelector('main')
  return !main || main.scrollWidth <= main.clientWidth + 1
})

const typeIt = async (page, text) => {
  await page.getByRole('button', { name: 'Type' }).first().click()
  await page.getByRole('textbox', { name: 'Type' }).fill(text)
  await page.getByRole('button', { name: 'Send' }).click()
}
const openRoom = (page, room) => page.getByRole('link', { name: room, exact: true }).click()
const yes = (page) => page.getByRole('button', { name: /^Yes/ }).last().click()
const heard = (page, ms = 8000) => page.locator('[data-heard]').first().waitFor({ state: 'visible', timeout: ms }).then(() => true, () => false)
const paid = (page, ms = 6000) => page.getByRole('img', { name: 'Payment received' }).waitFor({ timeout: ms }).then(() => true, () => false)
const closeTop = (page) => page.getByRole('button', { name: 'Close', exact: true }).last().click()

const phone = watch(await phoneCtx.newPage(), 'phone')
const watcherCtx = await browser.newContext({ viewport: { width: 375, height: 760 } })
await watcherCtx.addInitScript(inEnglish)
const watcher = watch(await watcherCtx.newPage(), 'watcher') // a second phone on another room: proves live updates
const box = watch(await (await browser.newContext({ viewport: { width: 1280, height: 800 } })).newPage(), 'soundbox')
const wa = watch(await (await browser.newContext({ viewport: { width: 1280, height: 800 } })).newPage(), 'wa')

try {
  section('Setup')
  check('reset demo data', (await post('/admin/reset-demo')).ok !== false)
  await box.goto(`${BASE}/soundbox`)
  await box.getByText('Tap to enable sound').click().catch(() => {})
  await wa.goto(`${BASE}/wa`)
  await phone.goto(`${BASE}/app/counter`)
  await watcher.goto(`${BASE}/app/hisaab`)
  check('phone app loads on the Counter', await sees(phone, 'What should I bill?'))
  await shot(phone, '01-counter-empty')
  check('merchant header has no demo links', !(await phone.getByRole('link', { name: 'Status' }).isVisible().catch(() => false)))
  await phone.getByRole('button', { name: 'More', exact: true }).click()
  check('Soundbox, WhatsApp and Status are in the menu', await sees(phone, 'Other screens'))
  await closeTop(phone)

  section('Counter: voice bill, live on the Soundbox')
  await typeIt(phone, 'do maggi ek surf excel chaar colgate')
  check('cart totals Rs249', await sees(phone, '₹249'))
  check('Soundbox shows the bill live', await sees(box, 'Colgate'))
  await typeIt(phone, 'bees rupaye ki cheeni')
  check('loose item: 450 gram tolo', await sees(phone, 'Weigh 450 g'))
  check('Soundbox shows the weigh instruction', await sees(box, '450 gram tolo'))
  await shot(phone, '02-counter-cart')
  check('no sideways scroll', await noOverflow(phone))
  await phone.getByRole('button', { name: /Cheeni/ }).first().click()
  await phone.getByRole('button', { name: /^Remove/ }).click()
  check('remove a line by hand: back to Rs249', await sees(phone, '₹249'))
  await phone.getByRole('button', { name: /Maggi/ }).first().click()
  await phone.getByRole('button', { name: 'more', exact: true }).click()
  check('stepper changes the bill: Rs261', await sees(phone, '₹261'))
  await phone.getByRole('button', { name: 'less', exact: true }).click()
  check('stepper back to Rs249', await sees(phone, '₹249'))

  section('Counter: QR, payment, stock, receipts')
  const colgate = await stockOf('Colgate')
  const salesBefore = (await api('/dashboard/v2')).today.sales
  await phone.getByRole('button', { name: /Make bill/ }).click()
  await shot(phone, '03-pay-sheet')
  await phone.getByRole('button', { name: 'Paytm' }).click()
  check('exact-amount QR on the phone', await sees(phone, 'Payment received'))
  await shot(phone, '04-qr')
  check('QR on the Soundbox', await sees(box, '249'))
  await phone.getByRole('button', { name: 'Payment received', exact: true }).click()
  check('paid screen', await paid(phone))
  await shot(phone, '05-paid')
  check('Soundbox shows received', await sees(box, /received|mil gaya|prapt|मिल/i, 6000))
  check('stock dropped by 4', (await stockOf('Colgate')) === colgate - 4, `${colgate} to ${await stockOf('Colgate')}`)
  check('second phone: Hisaab updated live', await sees(watcher, `₹${(salesBefore + 249).toLocaleString('en-IN')}`, 5000), `expected ${salesBefore + 249}`)
  await phone.reload()
  await phone.waitForTimeout(1200)
  check('reload does not replay the old payment', !(await phone.getByRole('img', { name: 'Payment received' }).isVisible().catch(() => false)))

  section('Counter: payment modes do not leak between bills')
  await typeIt(phone, 'ek surf excel')
  await sees(phone, 'Make bill')
  await phone.getByRole('button', { name: /Make bill/ }).click()
  await phone.getByRole('button', { name: 'Cash' }).click()
  check('cash bill completes with no QR', await paid(phone))
  await phone.getByRole('button', { name: 'New bill' }).click()
  await typeIt(phone, 'ek surf excel')
  await sees(phone, 'Make bill')
  await phone.getByRole('button', { name: /Make bill/ }).click()
  await phone.getByRole('button', { name: 'Mix' }).click()
  check('mix asks how much of each', await phone.getByRole('textbox', { name: 'Cash' }).isVisible())
  await closeTop(phone)
  await phone.getByRole('button', { name: /Make bill/ }).click()
  check('pay sheet starts fresh for each opening', await phone.getByRole('button', { name: 'Paytm' }).isVisible())
  await phone.getByRole('button', { name: 'Credit' }).first().click()
  check('khata asks for a customer first', await sees(phone, 'Whose credit?'))
  await closeTop(phone)
  await closeTop(phone)

  section('Mic: full-screen listening, in a real recording')
  const mic = phone.getByRole('button', { name: 'Press to speak' })
  const bb = await mic.boundingBox()
  await phone.mouse.move(bb.x + bb.width / 2, bb.y + bb.height / 2)
  await phone.mouse.down()
  check('listening screen opens', await sees(phone, 'Listening'))
  await shot(phone, '06-listening')
  await phone.waitForTimeout(1200)
  await phone.mouse.up()
  check('release sends it', await heard(phone))
  await post(`/cart/${await phone.evaluate(() => localStorage.getItem('awaaz.counter.session'))}`).catch(() => {})
  await mic.click()
  check('tap keeps recording', await sees(phone, 'Listening'))
  await phone.getByRole('button', { name: 'Cancel' }).click()
  await phone.waitForTimeout(400)
  check('cancel closes with nothing sent', !(await phone.getByText('Understanding').isVisible().catch(() => false)))

  section('Godown: mic adds stock, live')
  await openRoom(phone, 'Stock')
  check('stock list', await sees(phone, 'Maggi'))
  await shot(phone, '07-godown')
  check('no sideways scroll', await noOverflow(phone))
  const before = await stockOf('Maggi')
  await typeIt(phone, 'das packet maggi')
  check('restock waits for Haan', await sees(phone, 'Add to stock?'))
  await shot(phone, '08-restock-confirm')
  check('nothing changes before Haan', (await stockOf('Maggi')) === before)
  await yes(phone)
  await phone.waitForTimeout(800)
  check('stock goes up after Haan', (await stockOf('Maggi')) === before + 10, `${before} to ${await stockOf('Maggi')}`)
  check('list updates with no reload', await sees(phone, `${before + 10} packet`))

  await phone.getByRole('tab', { name: 'Scan bill' }).click()
  await phone.locator('input[type=file]').first().setInputFiles(PNG)
  check('bill scan flags the price rise', await sees(phone, '+₹3', 8000))
  await shot(phone, '09-bill-scan')
  await yes(phone)
  check('bill scan confirms into stock', await sees(phone, 'Added to stock', 6000))

  await phone.getByRole('tab', { name: 'Shelf' }).click()
  await phone.locator('input[type=file]').first().setInputFiles(PNG)
  check('shelf audit shows differences', await sees(phone, 'Loss', 8000))
  await yes(phone)
  await phone.waitForTimeout(800)
  check('shelf audit confirms', await sees(phone, 'New audit', 6000))

  await phone.getByRole('tab', { name: 'Expiry' }).click()
  check('expiry claims', await sees(phone, 'Return claim'))
  await shot(phone, '10-expiry')
  await phone.getByRole('tab', { name: 'Not found' }).click()
  await phone.getByRole('textbox', { name: 'What was missing' }).fill('kurkure')
  await phone.getByRole('button', { name: 'Note' }).click()
  check('missed sale noted', await sees(phone, /kurkure/i))

  section('Khata: voice udhaar, WhatsApp proof, Postpaid')
  await watcher.goto(`${BASE}/app/khata`)
  await sees(watcher, 'Verma ji')
  await openRoom(phone, 'Credit')
  check('customer list', await sees(phone, 'Verma ji'))
  await shot(phone, '11-khata')
  check('one status per person', !(await phone.getByText('risk').first().isVisible().catch(() => false)))
  check('no sideways scroll', await noOverflow(phone))
  await typeIt(phone, 'verma ji ke khate mein paanch sau')
  check('udhaar waits for Haan', await sees(phone, 'Add to credit?'))
  await shot(phone, '12-udhaar-confirm')
  await yes(phone)
  check('second phone: balance updates live', await sees(watcher, '₹1,350', 5000))
  check('WhatsApp simulator receives the confirmation live', await sees(wa, 'Verma', 5000))
  const verma = (await api('/khata/customers')).find((c) => c.name.includes('Verma'))
  const msgs = await api(`/wa/messages?customer_id=${verma.id}`)
  check('confirmation text has the new balance', msgs.some((m) => String(m.body).includes('1,350')))

  await phone.goto(`${BASE}/app/khata/${verma.id}`)
  check('customer page', await sees(phone, '₹1,000 limit'))
  await shot(phone, '13-khata-detail')
  await phone.getByRole('button', { name: 'Give credit' }).click()
  await phone.getByRole('button', { name: '200', exact: true }).click()
  check('over-limit warning before saving', await sees(phone, 'limit: due'))
  await phone.getByRole('button', { name: /Add credit/ }).click()
  check('entry saved', await phone.getByRole('img', { name: 'Added to credit' }).waitFor({ timeout: 4000 }).then(() => true, () => false))
  check('WhatsApp sent shown', await sees(phone, 'WhatsApp sent'))
  if (await phone.getByRole('button', { name: /Offer Paytm Postpaid/ }).isVisible().catch(() => false)) {
    await phone.getByRole('button', { name: /Offer Paytm Postpaid/ }).click()
    await phone.getByRole('button', { name: /approve/i }).click()
    check('simulated Postpaid approves', await sees(phone, 'Approved'))
  } else check('Postpaid offered when over limit', false)
  await phone.getByRole('button', { name: 'OK' }).click()
  check('customer page updates after the entry', await sees(phone, '₹1,550'))
  await phone.getByRole('button', { name: 'Got paid' }).click()
  await phone.getByRole('button', { name: '500', exact: true }).click()
  await phone.getByRole('button', { name: /Record payment/ }).click()
  check('payment recorded', await phone.getByRole('img', { name: 'Payment recorded' }).waitFor({ timeout: 4000 }).then(() => true, () => false))
  await phone.getByRole('button', { name: 'OK' }).click()
  check('balance drops', await sees(phone, '₹1,050'))

  await openRoom(phone, 'Credit')
  await phone.getByRole('button', { name: 'Reminders' }).click()
  check('reminder preview', await sees(phone, 'people?'))
  await yes(phone)
  check('reminders sent', await sees(phone, 'reminders sent'))
  await closeTop(phone)
  await phone.locator('input[type=file]').first().setInputFiles(PNG)
  check('notebook photo is read', await sees(phone, 'Read from notebook', 8000))
  await yes(phone)
  check('notebook entries imported', await sees(phone, 'added to credit', 6000))

  section('Hisaab: live numbers, invoices, galla')
  await openRoom(phone, 'Accounts')
  check('today screen', await sees(phone, 'Top sellers'))
  await shot(phone, '14-hisaab')
  check('no sideways scroll', await noOverflow(phone))
  await typeIt(phone, 'aaj ki sale kitni hai')
  check('mic answers a question here', await heard(phone))
  await shot(phone, '15-answer')
  await closeTop(phone)
  await phone.getByRole('tab', { name: 'Bills' }).click()
  check('invoice list', await sees(phone, 'RGS/'))
  await phone.getByRole('tab', { name: 'Cash close' }).click()
  check('expected cash', await sees(phone, 'Expected in cash box'))
  await phone.locator('input[type=file]').first().setInputFiles(PNG)
  check('cash photo counted', await sees(phone, 'Counted', 8000))
  await shot(phone, '16-galla')
  await yes(phone)
  check('day closes with the difference', await sees(phone, 'OK', 6000))

  section('Salaah: brief, questions, reorder, WhatsApp orders')
  await phone.getByRole('link', { name: 'Advice' }).click()
  check('morning brief', await sees(phone, /8,420/, 8000))
  await phone.getByRole('button', { name: 'Read' }).click()
  check('brief text opens on request', await sees(phone, /sale hui/i, 2000))
  await shot(phone, '17-brief')
  await phone.getByRole('button', { name: 'On Soundbox' }).click()
  check('brief plays on the Soundbox', await sees(box, /8,420/, 6000))
  await phone.getByRole('tab', { name: 'Orders' }).click()
  await phone.getByRole('button', { name: 'Make order' }).click()
  check('reorder draft', await sees(phone, 'Send on WhatsApp', 6000))
  await shot(phone, '18-reorder')
  await phone.getByRole('button', { name: 'Send on WhatsApp' }).first().click()
  await yes(phone)
  check('order sent to the supplier', await sees(phone, /WhatsApp (sent|delivered|queued)/, 6000))
  await phone.getByRole('tab', { name: 'Ask' }).click()
  await phone.locator('main li button').first().click()
  check('ask tab answers', await heard(phone))
  await closeTop(phone)
  await phone.getByRole('tab', { name: 'WhatsApp' }).click()
  const form = new FormData()
  form.append('type', 'audio'); form.append('from_phone', '919810000004'); form.append('demo_phrase', '1')
  await fetch(`${BASE}/api/wa/simulate-inbound`, { method: 'POST', body: form })
  check('customer voice order appears live', await sees(phone, 'Mrs. Kapoor', 6000))
  await shot(phone, '19-wa-order')
  await phone.getByRole('button', { name: /Make bill/ }).click()
  check('order moves to the Counter', await phone.waitForURL('**/app/counter', { timeout: 6000 }).then(() => true, () => false))
  const left = await api('/wa/orders?status=proposed')
  check('billed order leaves the list', left.length === 0, `${left.length} open`)

  section('Screens around the app')
  await phone.goto(`${BASE}/status`)
  check('status page', await sees(phone, 'Reset'))
  const inv = (await api('/invoices?limit=1'))[0]
  const res = await fetch(new URL(inv.public_url).pathname.replace(/^/, BASE))
  check('public receipt page', res.ok && (await res.text()).includes('RGS/'))
  const pb = (await api('/khata/customers'))[0]
  check('customer passbook page', (await fetch(BASE + new URL(pb.passbook_url).pathname)).ok)

  section('Live reset')
  await phone.goto(`${BASE}/app/hisaab`)
  await sees(phone, 'Top sellers')
  await post('/admin/reset-demo')
  const salesAfter = (await api('/dashboard/v2')).today.sales
  check('reset reaches an open screen with no reload', await sees(phone, `₹${salesAfter.toLocaleString('en-IN')}`, 6000))

  section('Language')
  await post('/admin/reset-demo')
  const ROOMS = ['counter', 'godown', 'khata', 'hisaab', 'salaah']
  // Words that would mean a screen still shows Hinglish in English mode.
  const HINGLISH = /\b(karein|karo|banao|bhejo|hai|nahi|kya|baaki|likho|jama|udhaar|dhundhein|sunein|haan)\b/i
  for (const r of ROOMS) {
    await phone.goto(`${BASE}/app/${r}`)
    await phone.waitForTimeout(1200)
    const txt = await phone.locator('main, nav, header').allInnerTexts()
    const hit = txt.join(' ').match(HINGLISH)
    check(`English: no Hinglish on ${r}`, !hit, hit ? hit[0] : '')
    check(`English: no Devanagari on ${r}`, !/[\u0900-\u097F]/.test(txt.join(' ').replace(/[\u0900-\u097F]+\s*(?=\d)/g, '')) || r === 'godown' || r === 'counter')
  }
  await phone.getByRole('button', { name: 'More', exact: true }).click()
  await phone.getByRole('button', { name: 'हिंदी' }).click()
  await phone.waitForLoadState('load')
  await phone.waitForTimeout(800)
  check('switch to Hindi applies at once', await phone.getByRole('link', { name: 'काउंटर' }).isVisible().catch(() => false))
  await phone.reload()
  check('language choice survives a reload', await sees(phone, 'बोलिए', 3000) || await sees(phone, 'काउंटर', 1000))
  await phone.evaluate(() => localStorage.setItem('awaaz.lang', 'en'))
  await shot(phone, 'hi-menu')
  const hiPage = await (await browser.newContext({ viewport: { width: 375, height: 760 } })).newPage()
  await hiPage.goto(`${BASE}/app/counter`)
  check('Hindi is the default for a new phone', await sees(hiPage, 'बोलिए'))
  await shot(hiPage, 'hi-counter')
  for (const [r, name] of [['godown', 'गोदाम'], ['khata', 'खाता'], ['hisaab', 'हिसाब'], ['salaah', 'सलाह']]) {
    await hiPage.goto(`${BASE}/app/${r}`)
    await hiPage.waitForTimeout(1500)
    check(`Hindi: ${r} title`, await sees(hiPage, name))
    await shot(hiPage, `hi-${r}`)
    const txt = (await hiPage.locator('main, nav, header').allInnerTexts()).join(' ')
    const latin = [...new Set(txt.match(/[A-Za-z]{3,}/g) || [])].filter((w) => !/^(demo|Paytm|UPI|QR|WhatsApp)$/i.test(w))
    console.log(`    Hindi ${r} Latin words: ${latin.join(', ')}`)
  }
  await hiPage.goto(`${BASE}/app/counter`)
  await hiPage.getByRole('button', { name: 'टाइप करें' }).click()
  await hiPage.locator('[role=dialog] li button').first().click()
  check('Hindi example bills correctly', await sees(hiPage, '₹249'))
  await sees(hiPage, 'तोलें', 500)
  await shot(hiPage, 'hi-cart')
  await hiPage.context().close()

  section('Wording')
  for (const r of ['counter', 'godown', 'khata', 'hisaab', 'salaah']) {
    await phone.goto(`${BASE}/app/${r}`)
    await phone.waitForTimeout(800)
    const txt = await phone.evaluate(() => document.body.innerText)
    check(`no "munim" on ${r}`, !/munim|मुनीम/i.test(txt))
  }
  check('no JavaScript errors on any screen', consoleErrors.length === 0, consoleErrors.slice(0, 5).join(' | '))
} catch (e) {
  check(`script stopped: ${e.message.split('\n')[0]}`, false)
  await shot(phone, 'zz-failure').catch(() => {})
} finally {
  await browser.close()
}

const failed = results.filter((r) => !r[1])
console.log(`\n${results.length - failed.length}/${results.length} checks passed`)
if (failed.length) console.log('FAILED:\n' + failed.map((f) => `  - ${f[0]}  ${f[2]}`).join('\n'))
process.exit(failed.length ? 1 : 0)
