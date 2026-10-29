import { useCallback, useEffect, useRef, useState } from 'react'
import { Ear, Keyboard, Receipt, ScanLine, Send, UserRound, Sparkles } from 'lucide-react'
import { useApp, useStoreEvent } from '../../components/app/AppContext'
import MicOrb from '../../components/app/MicOrb'
import PhotoButton from '../../components/app/PhotoButton'
import CartPanel from '../../components/app/CartPanel'
import ActionCard from '../../components/app/ActionCard'
import CustomerSheet from '../../components/app/CustomerSheet'
import PaySheet from '../../components/app/PaySheet'
import PayQR from '../../components/app/PayQR'
import PaidView from '../../components/app/PaidView'
import SourceChip from '../../components/app/SourceChip'
import { Btn, Chip, inputCls } from '../../components/app/ui'
import useRecorder from '../../hooks/useRecorder'
import { speak, stopSpeaking } from '../../lib/audio'
import { inr } from '../../lib/format'
import {
  addCartLines,
  addUsualToCart,
  attachCartCustomer,
  checkoutCart,
  clearCart,
  getCart,
  getInvoice,
  listActions,
  parseParchi,
  removeCartLine,
  sendUtterance,
  setCartLineQty,
  addMissedSale,
} from '../../api/client'

const EXAMPLES = ['do maggi ek surf excel chaar colgate', 'bees rupaye ki cheeni', 'bas kitna hua']

export default function Counter() {
  const { sessionId, showToast, showError } = useApp()

  const [cart, setCart] = useState(null)
  const [stage, setStage] = useState('cart') // cart | pay | paid
  const [checkout, setCheckout] = useState(null)
  const [paid, setPaid] = useState(null)
  const [pending, setPending] = useState([])
  const [last, setLast] = useState(null)
  const [busy, setBusy] = useState(false)
  const [text, setText] = useState('')
  const [showText, setShowText] = useState(false)
  const [customerOpen, setCustomerOpen] = useState(false)
  const [payOpen, setPayOpen] = useState(false)
  const [paying, setPaying] = useState(false)
  const [usual, setUsual] = useState(null)
  const [parchi, setParchi] = useState(null)
  const [parchiBusy, setParchiBusy] = useState(false)

  const stageRef = useRef(stage)
  stageRef.current = stage
  const checkoutRef = useRef(null)
  checkoutRef.current = checkout
  const paidOrders = useRef(new Set())
  const queue = useRef(Promise.resolve())
  const recRef = useRef(null)

  // ----- cart state ---------------------------------------------------------------------------------------

  // Accept a cart only if it is not older than the one on screen (HTTP reply and SSE race each other).
  const applyCart = useCallback((next) => {
    if (!next) return
    setCart((cur) => (cur && cur.updated_at && next.updated_at && next.updated_at < cur.updated_at ? cur : next))
  }, [])

  const refreshCart = useCallback(async () => {
    try {
      applyCart(await getCart(sessionId))
    } catch (e) {
      showError(e)
    }
  }, [applyCart, sessionId, showError])

  const say = useCallback(async (reply) => {
    const rec = recRef.current
    rec?.setSuspended(true)
    try {
      await speak(reply)
    } finally {
      setTimeout(() => rec?.setSuspended(false), 350)
    }
  }, [])

  const showCheckout = useCallback(
    (data) => {
      if (!data || !data.order_id) return
      if (paidOrders.current.has(data.order_id)) return
      setCheckout(data)
      setPayOpen(false)
      if (data.complete) {
        paidOrders.current.add(data.order_id)
        setPaid({ ...data, amount: data.total })
        setStage('paid')
        say(data)
      } else {
        setStage('pay')
      }
    },
    [say],
  )

  const onPaid = useCallback(
    (data) => {
      const orderId = data.order_id
      if (orderId && paidOrders.current.has(orderId)) return
      if (orderId) paidOrders.current.add(orderId)
      setPaid({ ...data, amount: data.amount ?? data.invoice?.total, receipt_url: data.receipt_url || data.invoice?.receipt_url })
      setStage('paid')
      say(data)
    },
    [say],
  )

  const newBill = useCallback(async () => {
    stopSpeaking()
    try {
      applyCart(await clearCart(sessionId))
    } catch (e) {
      showError(e)
    }
    setStage('cart')
    setCheckout(null)
    setPaid(null)
    setUsual(null)
    setParchi(null)
    setPending([])
    setLast(null)
  }, [applyCart, sessionId, showError])

  // First load: cart, open proposals, and recovery of a bill that was already created.
  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const c = await getCart(sessionId)
        if (!alive) return
        applyCart(c)
        if (c.status === 'checked_out' && c.invoice_id) {
          const inv = await getInvoice(c.invoice_id)
          if (!alive) return
          if (inv.status === 'paid') {
            applyCart(await clearCart(sessionId))
          } else {
            showCheckout(await checkoutCart(sessionId))
          }
        }
        const acts = await listActions({ session_id: sessionId, status: 'proposed' })
        if (alive) setPending(acts.filter((a) => a.kind !== 'cart_edit'))
      } catch (e) {
        if (alive) showError(e)
      }
    })()
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId])

  // ----- live events --------------------------------------------------------------------------------------

  useStoreEvent('cart_updated', (d) => {
    if (d.session_id === sessionId && stageRef.current === 'cart') applyCart(d.cart)
  })
  useStoreEvent('checkout', (d) => {
    if (d.session_id === sessionId && stageRef.current === 'cart') showCheckout(d)
  })
  useStoreEvent('payment_received', (d) => {
    const mine = d.session_id === sessionId || (checkoutRef.current && d.order_id === checkoutRef.current.order_id)
    if (mine) onPaid(d)
  })
  useStoreEvent('action_proposed', (d) => {
    if (d.session_id !== sessionId || !d.action || d.action.kind === 'cart_edit') return
    setPending((cur) => (cur.some((a) => a.id === d.action.id) ? cur : [...cur, d.action]))
  })

  // ----- utterances ---------------------------------------------------------------------------------------

  const processActions = useCallback(
    (actions = []) => {
      actions.forEach((a) => {
        if (a.kind === 'cart_edit') return
        if (a.status === 'proposed') {
          setPending((cur) => (cur.some((x) => x.id === a.id) ? cur.map((x) => (x.id === a.id ? a : x)) : [...cur, a]))
          return
        }
        setPending((cur) => cur.filter((x) => x.id !== a.id))
        if (a.status === 'confirmed' && a.result) {
          if (a.result.order_id) showCheckout(a.result)
          else if (a.result.spoken_text) showToast(a.result.spoken_text)
        }
      })
    },
    [showCheckout, showToast],
  )

  const submit = useCallback(
    async ({ audio, filename, text: typed }) => {
      setBusy(true)
      try {
        const res = await sendUtterance({ audio, filename, text: typed, context: 'counter', sessionId })
        setLast(res)
        if (res.cart) applyCart(res.cart)
        else refreshCart()
        processActions(res.actions)
        if (res.missed?.length) showToast(`${res.missed.join(', ')} note kiya`, 'warning')
        if (!res.actions?.some((a) => a.status === 'confirmed' && a.result?.order_id)) say(res)
      } catch (e) {
        showError(e)
      } finally {
        setBusy(false)
      }
    },
    [applyCart, processActions, refreshCart, say, sessionId, showError, showToast],
  )

  const enqueue = useCallback(
    (job) => {
      queue.current = queue.current.then(() => submit(job)).catch(() => {})
    },
    [submit],
  )

  const rec = useRecorder({
    onAudio: (blob, meta) => enqueue({ audio: blob, filename: meta.filename }),
  })
  recRef.current = rec

  // Stop listening when this screen closes or a bill is being paid.
  useEffect(() => {
    if (stage !== 'cart' && rec.handsFree) rec.stopHandsFree()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stage])

  const toggleHandsFree = async () => {
    if (rec.handsFree) await rec.stopHandsFree()
    else if (!(await rec.startHandsFree())) showToast('Microphone chalu nahi hua', 'error')
  }

  const sendText = (e, phrase) => {
    e?.preventDefault?.()
    const t = (phrase ?? text).trim()
    if (!t) return
    setText('')
    enqueue({ text: t })
  }

  // ----- cart edits ---------------------------------------------------------------------------------------

  const changeQty = async (line, qty) => {
    try {
      applyCart(qty <= 0 ? await removeCartLine(sessionId, line.product_id) : await setCartLineQty(sessionId, line.product_id, qty))
    } catch (e) {
      showError(e)
    }
  }
  const removeLine = async (line) => {
    try {
      applyCart(await removeCartLine(sessionId, line.product_id))
    } catch (e) {
      showError(e)
    }
  }

  const pickCustomer = async (c) => {
    setCustomerOpen(false)
    try {
      const res = await attachCartCustomer(sessionId, { customer_id: c.id })
      applyCart(res.cart)
      setUsual(res.usual && res.usual.lines?.length ? res.usual : null)
      showToast(`${c.name} chuna gaya`)
    } catch (e) {
      showError(e)
    }
  }

  const addUsual = async () => {
    try {
      applyCart(await addUsualToCart(sessionId, {}))
      setUsual(null)
    } catch (e) {
      showError(e)
    }
  }

  const doParchi = async (files) => {
    setParchiBusy(true)
    try {
      const res = await parseParchi(files[0])
      if (res.lines?.length) {
        const items = res.lines.map((l) => ({ product_id: l.product_id, qty: l.qty, unit: l.unit }))
        applyCart(await addCartLines(sessionId, items, 'add'))
      }
      setParchi(res)
      say({ spoken_text: res.message_hi })
    } catch (e) {
      showError(e)
    } finally {
      setParchiBusy(false)
    }
  }

  const noteMissed = async (name) => {
    try {
      const r = await addMissedSale(name)
      showToast(`${name}: ${r.asked_this_week} baar maanga gaya`)
      setParchi((p) => (p ? { ...p, unmatched: p.unmatched.filter((u) => u.name !== name) } : p))
    } catch (e) {
      showError(e)
    }
  }

  const doCheckout = async (body) => {
    setPaying(true)
    try {
      showCheckout(await checkoutCart(sessionId, body))
    } catch (e) {
      showError(e)
    } finally {
      setPaying(false)
    }
  }

  const lines = cart?.lines || []
  const isEmpty = lines.length === 0
  const customer = cart?.customer

  return (
    <div className="relative min-h-full flex flex-col">
      <div className="px-4 pt-3 space-y-3 flex-1">
        {/* customer + hands-free */}
        {stage === 'cart' && (
          <div className="flex items-center gap-2">
            <button
              onClick={() => setCustomerOpen(true)}
              className="flex-1 min-h-[48px] min-w-0 bg-white rounded-xl border border-line px-3 flex items-center gap-2 text-left"
            >
              <UserRound size={18} className="text-ink-3 flex-shrink-0" />
              <span className="font-hindi text-base font-bold truncate">{customer ? customer.name : 'Customer'}</span>
              {customer?.balance > 0 && <Chip tone="yellow" className="ml-auto">baaki {inr(customer.balance)}</Chip>}
            </button>
            <button
              onClick={toggleHandsFree}
              disabled={!rec.supported}
              aria-pressed={rec.handsFree}
              className={`min-h-[48px] px-3 rounded-xl border flex items-center gap-2 font-semibold ${
                rec.handsFree ? 'bg-ink text-white border-ink' : 'bg-white text-ink border-line'
              } disabled:opacity-40`}
            >
              <Ear size={18} className={rec.handsFree ? 'text-paytm-blue' : ''} />
              <span className="font-hindi text-sm font-bold whitespace-nowrap">Sun raha hai</span>
              <span className={`w-9 h-5 rounded-full relative transition-colors ${rec.handsFree ? 'bg-stock-green' : 'bg-line'}`}>
                <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all ${rec.handsFree ? 'left-[18px]' : 'left-0.5'}`} />
              </span>
            </button>
          </div>
        )}

        {usual && stage === 'cart' && (
          <div className="bg-white rounded-2xl border-2 border-accent p-3 flex items-center gap-3">
            <Sparkles size={22} className="text-accent flex-shrink-0" />
            <div className="min-w-0 flex-1">
              <div className="font-hindi text-lg font-bold truncate">{usual.prompt || `${usual.customer?.name} ka usual?`}</div>
              <div className="text-sm text-ink-3 truncate">
                {usual.lines.map((l) => l.name).join(', ')} . {inr(usual.total)}
              </div>
            </div>
            <Btn size="sm" variant="accent" onClick={addUsual}>
              Haan
            </Btn>
          </div>
        )}

        {/* last utterance */}
        {last && stage === 'cart' && (
          <div className="bg-white rounded-2xl border border-line p-3">
            <div className="flex items-start gap-2">
              <div className="flex-1 min-w-0">
                <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-3">Aapne kaha</div>
                <div className="font-hindi text-lg font-bold text-ink leading-snug">&ldquo;{last.transcript}&rdquo;</div>
              </div>
              <SourceChip source={last.source} latency={last.latency_ms} demo={last.demo_mode && last.source === 'fixture'} />
            </div>
            {last.spoken_text && <p className="mt-1 font-hindi text-base text-ink-3">{last.spoken_text}</p>}
            {last.errors?.length > 0 && <p className="mt-1 text-sm text-stock-red">{last.errors.join('; ')}</p>}
          </div>
        )}

        {/* parchi result */}
        {parchi && stage === 'cart' && (
          <div className="bg-white rounded-2xl border border-line p-3">
            <div className="flex items-start gap-2">
              <div className="flex-1">
                <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-3">Parchi padh li</div>
                <p className="font-hindi text-base font-bold">{parchi.message_hi}</p>
              </div>
              <SourceChip source={parchi.source} latency={parchi.latency_ms} demo={parchi.demo_mode} />
            </div>
            {parchi.unmatched?.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-2">
                {parchi.unmatched.map((u) => (
                  <button
                    key={u.name}
                    onClick={() => noteMissed(u.name)}
                    className="min-h-[44px] px-3 rounded-full bg-orange-50 border border-orange-200 text-sm font-semibold text-orange-900"
                  >
                    {u.name} nahi hai: note karein
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* proposals */}
        {pending.map((a) => (
          <ActionCard
            key={a.id}
            action={a}
            onResolved={(res, action, kind) => {
              setPending((cur) => cur.filter((x) => x.id !== action.id))
              if (res.cart) applyCart(res.cart)
              if (kind === 'confirm') {
                if (res.result?.order_id) showCheckout(res.result)
                else {
                  showToast(res.spoken_text || 'Ho gaya')
                  if (res.spoken_text) say(res)
                  refreshCart()
                }
              }
            }}
          />
        ))}

        {stage === 'cart' && (
          <>
            <CartPanel cart={cart} onQty={changeQty} onRemove={removeLine} disabled={busy} />
            {isEmpty && (
              <div className="pt-6 pb-2 text-center">
                <div className="font-hindi text-3xl font-bold text-ink leading-tight">Boliye, kya dena hai?</div>
                <div className="mt-1 text-sm text-ink-3">Mic dabayein aur bolein, ya &ldquo;Sun raha hai&rdquo; chalu karein</div>
                <div className="mt-5 flex flex-col items-stretch gap-2">
                  {EXAMPLES.map((ex) => (
                    <button
                      key={ex}
                      onClick={() => sendText(null, ex)}
                      className="min-h-[48px] rounded-xl bg-white border border-line px-4 text-left font-hindi text-base text-ink-3 active:bg-bg-app"
                    >
                      &ldquo;{ex}&rdquo;
                    </button>
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        {stage === 'pay' && checkout && (
          <PayQR checkout={checkout} onPaid={onPaid} onBack={newBill} />
        )}
        {stage === 'paid' && paid && <PaidView data={paid} onNew={newBill} />}
      </div>

      {/* dock */}
      {stage === 'cart' && (
        <div className="sticky bottom-0 z-10 px-4 pt-3 pb-3 bg-bg-app border-t border-line shadow-[0_-6px_16px_rgba(14,27,51,0.06)]">
          {!isEmpty && (
            <Btn size="lg" variant="navy" icon={Receipt} className="w-full mb-3" onClick={() => setPayOpen(true)}>
              Bill banao . {inr(cart.total)}
            </Btn>
          )}
          <div className="flex items-center justify-between">
            <div className="w-16 flex flex-col items-center gap-1">
              <PhotoButton compact icon={ScanLine} variant="outline" busy={parchiBusy} label="Parchi" onFiles={doParchi} />
              <span className="text-[11px] text-ink-3">Parchi</span>
            </div>
            <div className="flex flex-col items-center gap-1">
              <MicOrb rec={rec} busy={busy && !rec.handsFree} />
              <span className="text-xs font-medium text-ink-3 h-4">
                {rec.error ||
                  (busy
                    ? 'Samajh raha hoon...'
                    : rec.handsFree
                      ? rec.phase === 'speech'
                        ? 'Sun liya, ruk kar bhejunga...'
                        : 'Sun raha hoon...'
                      : rec.recording
                        ? 'Chhodein ya dobara tap karein'
                        : rec.supported
                          ? 'Dabayein aur bolein'
                          : 'Mic nahi hai, type karein')}
              </span>
            </div>
            <div className="w-16 flex flex-col items-center gap-1">
              <button
                onClick={() => setShowText((v) => !v)}
                aria-label="Type karein"
                className={`w-12 h-12 rounded-xl border flex items-center justify-center ${
                  showText ? 'bg-ink text-white border-ink' : 'bg-white border-line'
                }`}
              >
                <Keyboard size={20} />
              </button>
              <span className="text-[11px] text-ink-3">Type</span>
            </div>
          </div>
          {showText && (
            <form onSubmit={sendText} className="mt-3 flex gap-2">
              <input
                className={inputCls}
                placeholder="ya type karein: do maggi, ek surf"
                value={text}
                onChange={(e) => setText(e.target.value)}
                autoFocus
              />
              <button
                type="submit"
                disabled={!text.trim() || busy}
                aria-label="Bhejein"
                className="w-12 h-12 flex-shrink-0 rounded-xl bg-paytm-blue text-ink flex items-center justify-center disabled:opacity-50"
              >
                <Send size={20} />
              </button>
            </form>
          )}
        </div>
      )}

      <CustomerSheet open={customerOpen} onClose={() => setCustomerOpen(false)} onPick={pickCustomer} />
      <PaySheet
        open={payOpen}
        onClose={() => setPayOpen(false)}
        total={cart?.total || 0}
        customer={customer}
        busy={paying}
        onConfirm={doCheckout}
      />
    </div>
  )
}
