import { useCallback, useEffect, useRef, useState } from 'react'
import useEvents from '../../hooks/useEvents'
import { getDashboard, inr, sessionFromUrl } from '../../api/sideClient'

/**
 * The Soundbox screen is driven entirely by `store` channel events.
 *
 *   mode: 'idle' | 'bill' | 'qr' | 'paid' | 'brief'
 *
 *   cart_updated     -> bill (live lines, weigh instruction, running total); empty cart -> idle
 *   utterance        -> "heard" bubble (transcript + reply), speaks the reply
 *   action_proposed  -> confirm card (udhaar / restock ...), action_resolved clears it
 *   checkout         -> qr (exact amount, upi_string, order id); complete=true bills skip the QR
 *   payment_received -> paid (giant amount, spoken text, low-stock lines, receipt link), idle after a while
 *   payment_failed   -> banner, QR stays
 *   brief_ready      -> brief (text + audio)
 *   reorder_sent, khata_updated, khata_disputed, khata_confirmed, wa_order, wa_order_updated,
 *   postpaid_offered, postpaid_approved, galla_closed, stock_updated, khata_imported,
 *   khata_reminders_sent, demo_reset -> one-line banners (some also spoken)
 *
 * The server replays up to 50 old events when a stream first connects; those are ignored
 * (a short window after the first `hello`) so the screen never replays yesterday's payment.
 */

const PAID_HOLD_MS = 10000
const BRIEF_HOLD_MS = 45000
const HEARD_MS = 10000
const BANNER_MS = 9000
const REPLAY_WINDOW_MS = 600

export default function useSoundbox({ speak, cancelSpeech }) {
  const sessionFilter = useRef(sessionFromUrl()).current
  const [mode, setModeState] = useState('idle')
  const [cart, setCart] = useState(null)
  const [heard, setHeard] = useState(null) // {transcript, reply}
  const [checkout, setCheckout] = useState(null)
  const [paid, setPaid] = useState(null)
  const [brief, setBrief] = useState(null)
  const [proposal, setProposal] = useState(null) // pending PendingAction awaiting Haan / Nahi
  const [banners, setBanners] = useState([])
  const [tally, setTally] = useState(null)

  const modeRef = useRef('idle')
  const timers = useRef({})
  const coldUntil = useRef(0)
  const seenHello = useRef(false)
  const lastCheckoutAt = useRef(0)
  const lastPaidAt = useRef(0)
  const lastSaid = useRef({ text: '', at: 0 })
  const bannerId = useRef(0)
  const speakRef = useRef(speak)
  speakRef.current = speak

  const setMode = useCallback((m) => {
    modeRef.current = m
    setModeState(m)
  }, [])

  const later = useCallback((key, ms, fn) => {
    clearTimeout(timers.current[key])
    timers.current[key] = setTimeout(fn, ms)
  }, [])

  const goIdle = useCallback(() => {
    clearTimeout(timers.current.idle)
    setMode('idle')
    setCheckout(null)
    setPaid(null)
    setBrief(null)
  }, [setMode])

  useEffect(
    () => () => {
      Object.values(timers.current).forEach(clearTimeout)
    },
    [],
  )

  const say = useCallback((text, audioUrl, opts = {}) => {
    if (!text && !audioUrl) return
    const now = Date.now()
    if (text && lastSaid.current.text === text && now - lastSaid.current.at < 4000) return
    lastSaid.current = { text, at: now }
    speakRef.current(text, { audioUrl, ...opts })
  }, [])

  const banner = useCallback(
    (text, tone = 'info', spoken) => {
      const id = (bannerId.current += 1)
      setBanners((b) => [...b.slice(-2), { id, text, tone }])
      setTimeout(() => setBanners((b) => b.filter((x) => x.id !== id)), BANNER_MS)
      if (spoken) say(spoken)
    },
    [say],
  )

  const refreshTally = useCallback(() => {
    getDashboard()
      .then((d) => setTally(typeof d.today_sales === 'number' ? d.today_sales : null))
      .catch(() => {})
  }, [])
  useEffect(refreshTally, [refreshTally])

  // wraps a handler: drops replayed history and events of other sessions
  const on = (fn) => (data) => {
    if (Date.now() < coldUntil.current) return
    if (sessionFilter && data && data.session_id && data.session_id !== sessionFilter) return
    fn(data || {})
  }

  const connected = useEvents('store', {
    hello: () => {
      if (!seenHello.current) {
        seenHello.current = true
        coldUntil.current = Date.now() + REPLAY_WINDOW_MS
      }
    },

    cart_updated: on((d) => {
      const c = d.cart
      if (!c) return
      if (c.status === 'checked_out') return
      const lines = c.lines || []
      setCart(c)
      const m = modeRef.current
      if (lines.length === 0) {
        if (m === 'bill' || m === 'qr') goIdle()
        return
      }
      if (m === 'brief') return
      clearTimeout(timers.current.idle)
      setCheckout(null)
      setPaid(null)
      setMode('bill')
    }),

    utterance: on((d) => {
      if (d.transcript || d.spoken_text) {
        setHeard({ transcript: d.transcript || '', reply: d.spoken_text || '' })
        later('heard', HEARD_MS, () => setHeard(null))
      }
      const now = Date.now()
      // checkout / payment announce themselves; do not read the same total twice
      if (now - lastCheckoutAt.current < 4000 || now - lastPaidAt.current < 2000) return
      say(d.spoken_text, d.audio_url)
    }),

    action_proposed: on((d) => {
      if (d.action) setProposal({ ...d.action, spoken_text: d.spoken_text })
    }),

    action_resolved: on((d) => {
      setProposal((p) => (p && p.id === d.id ? null : p))
      if (d.status === 'confirmed' && d.summary) banner(`${d.summary}: ho gaya`, 'ok')
      say(d.spoken_text)
    }),

    checkout: on((d) => {
      lastCheckoutAt.current = Date.now()
      setCheckout(d)
      if (d.complete) return // cash / khata only: payment_received follows, no QR needed
      clearTimeout(timers.current.idle)
      setPaid(null)
      setMode('qr')
      say(d.spoken_text, d.audio_url, { interrupt: true })
    }),

    payment_received: on((d) => {
      lastPaidAt.current = Date.now()
      setPaid(d)
      setCheckout(null)
      setProposal(null)
      setMode('paid')
      say(d.spoken_text || `${inr(d.amount)} rupaye prapt hue`, d.audio_url, { interrupt: true })
      later('idle', PAID_HOLD_MS, goIdle)
      refreshTally()
    }),

    payment_failed: on((d) => {
      banner(`Payment fail: ${d.reason || d.error || d.order_id || ''}`.trim(), 'error', 'Payment nahi hua')
    }),

    brief_ready: on((d) => {
      setBrief(d)
      setMode('brief')
      say(d.spoken_text || d.text, d.audio_url, { interrupt: true })
      later('idle', BRIEF_HOLD_MS, goIdle)
    }),

    reorder_sent: on((d) =>
      banner(`PO ${d.po_number || ''} ${d.supplier_name || ''} ko bheja: ${d.lines || 0} item, kareeb ₹${inr(d.total_est)}`, 'ok'),
    ),
    khata_updated: on((d) => {
      const credit = d.kind === 'credit'
      banner(
        `${d.customer}: ${credit ? 'udhaar' : 'jama'} ₹${inr(Math.abs(d.amount))}, baaki ₹${inr(d.balance)}${d.warning ? ' (' + d.warning + ')' : ''}`,
        d.warning ? 'warn' : 'info',
      )
    }),
    khata_disputed: on((d) =>
      banner(d.message || `${d.customer} ne khata entry galat bataya`, 'warn', d.message || `${d.customer} ne entry galat bataya`),
    ),
    khata_confirmed: on((d) => banner(`${d.customer} ne khata entry confirm ki`, 'ok')),
    khata_imported: on((d) => banner('Khata notebook import ke liye tayyar', 'info')),
    khata_reminders_sent: on((d) => banner(`${d.count} khata reminder bheje`, 'info')),
    wa_order: on((d) =>
      banner(
        `WhatsApp order: ${d.customer} ₹${inr(d.total)} (${(d.lines || []).length} item)`,
        'info',
        `${d.customer} ka WhatsApp order aaya, ${inr(d.total)} rupaye`,
      ),
    ),
    wa_order_updated: on((d) => banner(`WhatsApp order ${d.status}: ${d.customer || ''}`, 'info')),
    postpaid_offered: on((d) => banner(`Postpaid offer: ${d.customer || ''} ₹${inr(d.amount)} (simulated)`, 'info')),
    postpaid_approved: on((d) => banner(d.message || 'Postpaid approve hua (simulated)', 'ok', d.message)),
    galla_closed: on((d) =>
      banner(`Galla: ₹${inr(d.counted)} gina, ₹${inr(d.expected)} hona chahiye`, Math.abs(d.diff || 0) > 0.5 ? 'warn' : 'ok', d.message_hi),
    ),
    stock_updated: on((d) => {
      const n = (d.products || []).length
      banner(`Stock update (${d.reason || 'restock'}): ${n} item${d.supplier ? ', ' + d.supplier : ''}`, 'info')
    }),
    demo_reset: () => {
      if (Date.now() < coldUntil.current) return
      cancelSpeech?.()
      setCart(null)
      setProposal(null)
      goIdle()
      banner('Demo data reset ho gaya', 'info')
      refreshTally()
    },
  })

  const dismissProposal = useCallback(() => setProposal(null), [])

  return {
    connected,
    mode,
    cart,
    heard,
    checkout,
    paid,
    brief,
    proposal,
    banners,
    tally,
    goIdle,
    dismissProposal,
    banner,
    say,
    sessionFilter,
  }
}
