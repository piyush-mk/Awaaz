import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, ArrowLeft, CheckCircle2, MessageSquarePlus, Radio, Store, User, X } from 'lucide-react'
import FullPage, { INK, SOFT } from '../components/sb/FullPage'
import Bubble, { WA } from '../components/wa/Bubble'
import Composer from '../components/wa/Composer'
import ConversationList from '../components/wa/ConversationList'
import { dayKey, dayLabel, initials } from '../components/wa/waUtils'
import useEvents from '../hooks/useEvents'
import {
  cancelWaOrder,
  confirmWaOrder,
  getConversations,
  getKhataCustomers,
  getMessages,
  getSuppliers,
  getWaOrders,
  getWaStatus,
  inr,
  simulateInbound,
  waSend,
} from '../api/sideClient'

const digits = (s) => String(s || '').replace(/\D/g, '')
const sameTail = (a, b) => digits(a).slice(-10) && digits(a).slice(-10) === digits(b).slice(-10)

function messageParams(conv) {
  if (!conv) return {}
  if (conv.customer_id) return { customerId: conv.customer_id }
  if (conv.supplier_id) return { supplierId: conv.supplier_id }
  return { phone: conv.phone }
}

function StatusChip({ status }) {
  if (!status) return <span className="rounded-full bg-white/20 px-3 py-1 text-xs font-semibold text-white">status...</span>
  const live = status.mode === 'live'
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-bold"
      style={{ background: live ? '#D9FDD3' : '#FFF1CC', color: live ? '#0B5D1E' : '#5C4300' }}
      title={
        live
          ? `Meta Cloud API live. Sent ${status.sent}, failed ${status.failed}.`
          : 'Simulator mode: messages stay in the outbox (no WA_TOKEN / WA_PHONE_NUMBER_ID).'
      }
    >
      <Radio size={13} aria-hidden="true" />
      {live ? 'Live · Meta' : 'Simulator'}
    </span>
  )
}

export default function WhatsAppSim() {
  const [convs, setConvs] = useState([])
  const [extra, setExtra] = useState([])
  const [selKey, setSelKey] = useState(null)
  const [messages, setMessages] = useState([])
  const [status, setStatus] = useState(null)
  const [orders, setOrders] = useState([])
  const [mode, setMode] = useState('customer') // who am I: customer | shop
  const [phrase, setPhrase] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [last, setLast] = useState(null)
  const [newOpen, setNewOpen] = useState(false)
  const [mobileChat, setMobileChat] = useState(false)
  const scroller = useRef(null)

  const allConvs = useMemo(() => {
    const have = new Set(convs.map((c) => c.key))
    const virtual = extra.filter((e) => !have.has(e.key))
    return [...virtual, ...convs]
  }, [convs, extra])
  const selected = allConvs.find((c) => c.key === selKey) || null

  const selRef = useRef(null)
  selRef.current = selected

  const loadConvs = useCallback(async () => {
    try {
      const list = await getConversations()
      setConvs(list)
      setSelKey((k) => k || (list[0] ? list[0].key : null))
    } catch (e) {
      setError(e.message)
    }
  }, [])

  const loadMessages = useCallback(async () => {
    const c = selRef.current
    if (!c) {
      setMessages([])
      return
    }
    try {
      setMessages(await getMessages(messageParams(c)))
    } catch (e) {
      setError(e.message)
    }
  }, [])

  const loadStatus = useCallback(() => getWaStatus().then(setStatus).catch(() => setStatus(null)), [])
  const loadOrders = useCallback(() => getWaOrders('proposed').then(setOrders).catch(() => setOrders([])), [])

  const refreshAll = useCallback(() => {
    loadConvs()
    loadMessages()
    loadOrders()
    loadStatus()
  }, [loadConvs, loadMessages, loadOrders, loadStatus])

  const debounce = useRef(null)
  const schedule = useCallback(() => {
    clearTimeout(debounce.current)
    debounce.current = setTimeout(refreshAll, 150)
  }, [refreshAll])

  useEffect(() => {
    refreshAll()
    const id = setInterval(refreshAll, 20000) // safety net if the event stream drops
    return () => {
      clearInterval(id)
      clearTimeout(debounce.current)
    }
  }, [refreshAll])

  useEffect(() => {
    loadMessages()
  }, [selKey, loadMessages])

  const connected = useEvents('wa', {
    wa_message: schedule,
    wa_status: (d) => {
      setMessages((ms) => ms.map((m) => (m.id === d.id ? { ...m, status: d.status, channel: d.channel || m.channel, error: d.error || m.error } : m)))
      schedule()
    },
  })

  useEffect(() => {
    if (scroller.current) scroller.current.scrollTop = scroller.current.scrollHeight
  }, [messages.length, selKey])

  const convOrders = useMemo(
    () =>
      selected
        ? orders.filter((o) => {
            const p = o.payload || {}
            return (selected.customer_id && p.customer_id === selected.customer_id) || sameTail(p.phone, selected.phone)
          })
        : [],
    [orders, selected],
  )

  const run = async (fn) => {
    setBusy(true)
    setError('')
    try {
      const r = await fn()
      setLast(r)
      await Promise.all([loadMessages(), loadConvs(), loadOrders()])
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const who = () => ({ phone: selected?.phone || undefined, customerId: selected?.customer_id || undefined })

  const sendText = (body) =>
    mode === 'customer'
      ? run(() => simulateInbound({ ...who(), type: 'text', body }))
      : run(() => waSend({ to: selected?.phone, customerId: selected?.customer_id, supplierId: selected?.supplier_id, body }))

  const sendVoiceBlob = (blob, filename) =>
    run(() => simulateInbound({ ...who(), type: 'audio', file: blob, filename, demoPhrase: phrase }))
  const sendVoiceText = (body) => run(() => simulateInbound({ ...who(), type: 'audio', body, demoPhrase: phrase }))
  const sendImage = (file, body) => run(() => simulateInbound({ ...who(), type: 'image', file, body }))

  const resolveOrder = (o, verb) =>
    run(async () => (verb === 'confirm' ? confirmWaOrder(o.id) : cancelWaOrder(o.id)))

  const openConv = (key) => {
    setSelKey(key)
    setMobileChat(true)
    setLast(null)
    setError('')
  }

  const grouped = useMemo(() => {
    const out = []
    let day = ''
    for (const m of messages) {
      const d = dayKey(m.created_at)
      if (d !== day) {
        day = d
        out.push({ sep: true, key: `d${d}`, label: dayLabel(m.created_at) })
      }
      out.push({ sep: false, key: `m${m.id}`, msg: m })
    }
    return out
  }, [messages])

  const isMine = (m) => (mode === 'customer' ? m.direction === 'in' : m.direction === 'out')

  return (
    <FullPage background={SOFT}>
      <div className="mx-auto flex h-full max-w-[1100px] gap-4 p-3 sm:p-4">
        {/* conversation list */}
        <aside
          className={`${mobileChat ? 'hidden' : 'flex'} w-full flex-col overflow-hidden rounded-2xl bg-white shadow-md lg:flex lg:w-[360px] lg:shrink-0`}
          aria-label="Conversations"
        >
          <div className="px-4 pb-3 pt-4 text-white" style={{ background: WA.header }}>
            <div className="flex items-center justify-between gap-2">
              <h1 className="text-xl font-bold">WhatsApp simulator</h1>
              <StatusChip status={status} />
            </div>
            <div className="mt-1 text-sm text-white/90">
              Events: {connected ? 'live' : 'reconnecting'}
              {status ? ` · bheje ${status.sent} · fail ${status.failed} · outbox ${status.outbox_total}` : ''}
            </div>
            {status?.last_error && (
              <div className="mt-2 flex items-start gap-1.5 rounded-lg bg-white/95 px-2.5 py-1.5 text-xs font-medium" style={{ color: '#8A1B12' }} title={status.last_error}>
                <AlertTriangle size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
                <span className="line-clamp-2">Last error: {status.last_error}</span>
              </div>
            )}
            <div className="mt-3 flex items-center gap-2">
              <button
                type="button"
                onClick={() => setNewOpen((v) => !v)}
                className="inline-flex min-h-[44px] items-center gap-2 rounded-lg bg-white/15 px-3 text-sm font-semibold hover:bg-white/25"
                aria-expanded={newOpen}
              >
                <MessageSquarePlus size={18} aria-hidden="true" /> Naya chat
              </button>
              <nav className="ml-auto flex gap-1 text-sm font-semibold">
                <Link to="/soundbox" className="inline-flex min-h-[44px] items-center rounded-lg px-2.5 hover:bg-white/15">Soundbox</Link>
                <Link to="/status" className="inline-flex min-h-[44px] items-center rounded-lg px-2.5 hover:bg-white/15">Status</Link>
              </nav>
            </div>
          </div>
          {newOpen && (
            <NewChat
              onClose={() => setNewOpen(false)}
              onPick={(conv) => {
                setExtra((x) => [conv, ...x.filter((e) => e.key !== conv.key)])
                setNewOpen(false)
                openConv(conv.key)
              }}
            />
          )}
          <div className="min-h-0 flex-1 overflow-y-auto">
            <ConversationList convs={allConvs} selectedKey={selKey} onSelect={openConv} />
          </div>
        </aside>

        {/* phone */}
        <section className={`${mobileChat ? 'flex' : 'hidden'} min-w-0 flex-1 justify-center lg:flex`} aria-label="Chat">
          <div
            className="flex h-full max-h-[900px] w-full max-w-[520px] flex-col overflow-hidden rounded-[34px] border-[9px] shadow-2xl"
            style={{ borderColor: INK, background: WA.chat }}
          >
            <div className="flex items-center gap-2 px-2 py-2 text-white" style={{ background: WA.header }}>
              <button
                type="button"
                onClick={() => setMobileChat(false)}
                className="grid h-11 w-11 place-items-center rounded-full hover:bg-white/15 lg:hidden"
                aria-label="Chats par wapas"
              >
                <ArrowLeft size={22} aria-hidden="true" />
              </button>
              <div
                className="grid h-10 w-10 shrink-0 place-items-center rounded-full text-sm font-bold"
                style={{ background: '#CDEBE4', color: '#0B3B33' }}
                aria-hidden="true"
              >
                {selected ? initials(selected.name) : '?'}
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-base font-semibold">{selected ? selected.name : 'Koi chat nahi chuni'}</div>
                <div className="truncate text-xs text-white/85">{selected?.phone || ''}</div>
              </div>
            </div>

            <div className="flex items-center gap-2 px-2 py-1.5 text-xs font-semibold text-white" style={{ background: WA.headerDark }}>
              <span>Main hoon:</span>
              <div className="flex overflow-hidden rounded-full border border-white/50" role="group" aria-label="Sender">
                {[
                  ['customer', 'Customer', User],
                  ['shop', 'Dukaan', Store],
                ].map(([k, label, Icon]) => (
                  <button
                    key={k}
                    type="button"
                    onClick={() => setMode(k)}
                    aria-pressed={mode === k}
                    className="inline-flex min-h-[44px] items-center gap-1.5 px-3"
                    style={{ background: mode === k ? '#fff' : 'transparent', color: mode === k ? WA.headerDark : '#fff' }}
                  >
                    <Icon size={14} aria-hidden="true" /> {label}
                  </button>
                ))}
              </div>
              <span className="ml-auto hidden text-white/85 sm:inline">
                {mode === 'customer' ? 'Customer ke phone se' : 'Dukaan ke phone se'}
              </span>
            </div>

            {convOrders.map((o) => (
              <div key={o.id} className="flex flex-wrap items-center gap-2 border-b bg-[#FFF8E1] px-3 py-2 text-sm" style={{ borderColor: '#E8D9A8', color: '#4A3A00' }}>
                <span className="min-w-0 flex-1 font-semibold">
                  WhatsApp order: ₹{inr(o.payload?.total)} ({(o.payload?.lines || []).length} item)
                </span>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => resolveOrder(o, 'confirm')}
                  className="min-h-[44px] rounded-lg px-3 font-bold text-white disabled:opacity-50"
                  style={{ background: WA.header }}
                >
                  Pack karo
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => resolveOrder(o, 'cancel')}
                  className="min-h-[44px] rounded-lg border px-3 font-bold disabled:opacity-50"
                  style={{ borderColor: '#B9A46A' }}
                >
                  Cancel
                </button>
              </div>
            ))}

            <div ref={scroller} className="min-h-0 flex-1 space-y-1.5 overflow-y-auto px-3 py-3" aria-live="polite">
              {!selected && (
                <div className="mt-10 text-center text-base" style={{ color: WA.sub }}>
                  Baayein se chat chuniye ya &ldquo;Naya chat&rdquo; dabaiye.
                </div>
              )}
              {selected && messages.length === 0 && (
                <div className="mt-10 text-center text-base" style={{ color: WA.sub }}>
                  Abhi koi message nahi. {mode === 'customer' ? '"hi" bhej kar shuru karein.' : 'Dukaan se message likhein.'}
                </div>
              )}
              {grouped.map((g) =>
                g.sep ? (
                  <div key={g.key} className="flex justify-center py-1">
                    <span className="rounded-lg bg-white/90 px-3 py-1 text-xs font-semibold shadow-sm" style={{ color: WA.sub }}>
                      {g.label}
                    </span>
                  </div>
                ) : (
                  <Bubble key={g.key} msg={g.msg} mine={isMine(g.msg)} />
                ),
              )}
            </div>

            {(last || error) && (
              <div
                className="flex items-start gap-2 border-t px-3 py-2 text-sm"
                style={{ background: error ? '#FDE7E5' : '#E8F5E9', color: error ? '#8A1B12' : '#14532D', borderColor: '#D5DADD' }}
                role={error ? 'alert' : 'status'}
              >
                {error ? <AlertTriangle size={16} className="mt-0.5 shrink-0" aria-hidden="true" /> : <CheckCircle2 size={16} className="mt-0.5 shrink-0" aria-hidden="true" />}
                <div className="min-w-0 flex-1">
                  {error ? (
                    error
                  ) : (
                    <>
                      Server: <b>{last.routed || (last.simulated ? 'ok' : 'sent')}</b>
                      {last.total != null && ` · ₹${inr(last.total)}`}
                      {last.lines ? ` · ${last.lines.length} item` : ''}
                      {last.transcript ? ` · "${last.transcript}"` : ''}
                    </>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setLast(null)
                    setError('')
                  }}
                  className="grid h-8 w-8 shrink-0 place-items-center rounded-full hover:bg-black/10"
                  aria-label="Band karein"
                >
                  <X size={14} aria-hidden="true" />
                </button>
              </div>
            )}

            <Composer
              mode={mode}
              disabled={!selected || (!selected.phone && !selected.customer_id)}
              busy={busy}
              onText={sendText}
              onVoiceBlob={sendVoiceBlob}
              onVoiceText={sendVoiceText}
              onImage={sendImage}
              phrase={phrase}
              onPhrase={setPhrase}
            />
          </div>
        </section>
      </div>
    </FullPage>
  )
}

function NewChat({ onPick, onClose }) {
  const [people, setPeople] = useState([])
  const [pick, setPick] = useState('')
  const [phone, setPhone] = useState('')
  const [name, setName] = useState('')

  useEffect(() => {
    let alive = true
    Promise.all([getKhataCustomers().catch(() => []), getSuppliers().catch(() => [])]).then(([cs, ss]) => {
      if (!alive) return
      setPeople([
        ...cs.filter((c) => c.phone).map((c) => ({ key: `c${c.id}`, name: c.name, phone: c.phone, customer_id: c.id, supplier_id: null, label: `${c.name} (customer)` })),
        ...ss.filter((s) => s.phone).map((s) => ({ key: `s${s.id}`, name: s.name, phone: s.phone, customer_id: null, supplier_id: s.id, label: `${s.name} (supplier)` })),
      ])
    })
    return () => {
      alive = false
    }
  }, [])

  const go = (e) => {
    e.preventDefault()
    const base = { count: 0, inbound_count: 0, last_message: null, last_at: null, last_id: 0 }
    if (pick) {
      const p = people.find((x) => x.key === pick)
      if (p) onPick({ ...base, ...p })
      return
    }
    const d = digits(phone)
    if (d.length < 8) return
    const norm = d.length === 10 ? `91${d}` : d
    onPick({ ...base, key: `p${norm}`, name: name.trim() || `+${norm}`, phone: norm, customer_id: null, supplier_id: null })
  }

  const field = 'min-h-[44px] w-full rounded-lg border bg-white px-3 text-base'
  return (
    <form onSubmit={go} className="space-y-2 border-b p-3" style={{ borderColor: '#EDF0F1', background: '#F7F8F8' }}>
      <div className="flex items-center justify-between">
        <div className="text-sm font-bold" style={{ color: WA.ink }}>Customer chuniye</div>
        <button type="button" onClick={onClose} className="grid h-11 w-11 place-items-center rounded-full hover:bg-black/5" aria-label="Band karein">
          <X size={18} aria-hidden="true" />
        </button>
      </div>
      <label className="block text-xs font-semibold" style={{ color: WA.sub }}>
        Pehchane hue log
        <select value={pick} onChange={(e) => setPick(e.target.value)} className={`${field} mt-1`} style={{ borderColor: '#C5CED3' }}>
          <option value="">Phone number daalna hai...</option>
          {people.map((p) => (
            <option key={p.key} value={p.key}>{p.label} {p.phone}</option>
          ))}
        </select>
      </label>
      {!pick && (
        <div className="grid grid-cols-2 gap-2">
          <label className="block text-xs font-semibold" style={{ color: WA.sub }}>
            Phone
            <input value={phone} onChange={(e) => setPhone(e.target.value)} inputMode="tel" placeholder="9198XXXXXXXX" className={`${field} mt-1`} style={{ borderColor: '#C5CED3' }} />
          </label>
          <label className="block text-xs font-semibold" style={{ color: WA.sub }}>
            Naam (optional)
            <input value={name} onChange={(e) => setName(e.target.value)} className={`${field} mt-1`} style={{ borderColor: '#C5CED3' }} />
          </label>
        </div>
      )}
      <button
        type="submit"
        disabled={!pick && digits(phone).length < 8}
        className="min-h-[44px] w-full rounded-lg px-4 text-base font-bold text-white disabled:opacity-50"
        style={{ background: WA.header }}
      >
        Chat kholein
      </button>
    </form>
  )
}
