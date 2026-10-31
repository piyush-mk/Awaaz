import { useCallback, useEffect, useRef, useState } from 'react'
import { Ear, ScanLine, UserRound } from 'lucide-react'
import { useApp, useStoreEvent } from '../../components/app/AppContext'
import { useVoice, useVoiceHandler } from '../../components/app/VoiceContext'
import PhotoButton from '../../components/app/PhotoButton'
import CartPanel from '../../components/app/CartPanel'
import ActionCard from '../../components/app/ActionCard'
import CustomerSheet from '../../components/app/CustomerSheet'
import PaySheet from '../../components/app/PaySheet'
import PayQR from '../../components/app/PayQR'
import PaidView from '../../components/app/PaidView'
import SourceChip from '../../components/app/SourceChip'
import { Btn } from '../../components/app/ui'
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

export default function Counter() {
  const { sessionId, showToast, showError } = useApp()
  const { rec, busy, room, submit: voiceSubmit } = useVoice()

  const [cart, setCart] = useState(null)
  const [stage, setStage] = useState('cart') // cart | pay | paid
  const [checkout, setCheckout] = useState(null)
  const [paid, setPaid] = useState(null)
  const [pending, setPending] = useState([])
  const [last, setLast] = useState(null)
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
  const recRef = useRef(rec)
  recRef.current = rec

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
      setPayOpen(false) // before the guard: payment_received can arrive ahead of the checkout reply
      if (paidOrders.current.has(data.order_id)) return
      setCheckout(data)
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
      setPayOpen(false)
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
  useStoreEvent('action_resolved', (d) => {
    setPending((cur) => cur.filter((a) => a.id !== d.id))
  })
  useStoreEvent('demo_reset', () => {
    stageRef.current = 'cart'
    setStage('cart')
    setCheckout(null)
    setPaid(null)
    setUsual(null)
    setParchi(null)
    setPending([])
    setLast(null)
    refreshCart()
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

  useVoiceHandler(async ({ audio, filename, text: typed }) => {
    const res = await sendUtterance({ audio, filename, text: typed, context: 'counter', sessionId })
    setLast(res)
    if (res.cart) applyCart(res.cart)
    else refreshCart()
    processActions(res.actions)
    if (res.missed?.length) showToast(`${res.missed.join(', ')} note kiya`, 'warning')
    if (!res.actions?.some((a) => a.status === 'confirmed' && a.result?.order_id)) say(res)
  })

  // Stop listening when this screen closes or a bill is being paid.
  useEffect(() => {
    if (stage !== 'cart' && rec.handsFree) rec.stopHandsFree()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stage])
  useEffect(
    () => () => {
      recRef.current?.stopHandsFree()
    },
    [],
  )

  const toggleHandsFree = async () => {
    if (rec.handsFree) await rec.stopHandsFree()
    else if (!(await rec.startHandsFree())) showToast('Microphone chalu nahi hua', 'error')
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
    <div className="relative min-h-full flex flex-col bg-bg-app">
      <div className="px-4 pt-3 pb-8 space-y-3 flex-1">
        {stage === 'cart' && (
          <div className="flex items-center gap-2">
            <button
              onClick={() => setCustomerOpen(true)}
              aria-label="Customer"
              className="flex-1 min-h-[44px] min-w-0 px-2 rounded-xl flex items-center justify-center gap-1.5 bg-white text-sm font-semibold"
            >
              <UserRound size={18} className="flex-shrink-0" />
              <span className="truncate">{customer ? customer.name : 'Customer'}</span>
            </button>
            <div className="flex-1 min-w-0"><PhotoButton icon={ScanLine} variant="outline" busy={parchiBusy} label="Parchi" onFiles={doParchi} className="w-full !min-h-[44px] !px-2 !gap-1.5 text-sm" /></div>
            <button
              onClick={toggleHandsFree}
              disabled={!rec.supported}
              aria-pressed={rec.handsFree}
              aria-label="Sun raha hai"
              className={`flex-1 min-h-[44px] min-w-0 px-2 rounded-xl flex items-center justify-center gap-1.5 text-sm font-semibold whitespace-nowrap disabled:opacity-40 ${rec.handsFree ? 'bg-ink text-white' : 'bg-white'}`}
            >
              <Ear size={18} className={`flex-shrink-0 ${rec.handsFree ? 'text-paytm-blue' : ''}`} />
              {rec.handsFree ? 'Sun raha' : 'Sunta rahe'}
            </button>
          </div>
        )}

        {usual && stage === 'cart' && (
          <div className="bg-white rounded-2xl p-3 flex items-center gap-3">
            <div className="min-w-0 flex-1 font-hindi text-lg font-semibold truncate">{usual.customer?.name || customer?.name} ka usual? {inr(usual.total)}</div>
            <Btn size="sm" variant="navy" onClick={addUsual}>Haan</Btn>
          </div>
        )}

        {last && stage === 'cart' && (
          <div className="flex items-start gap-2 px-1">
            <p data-heard className="flex-1 min-w-0 font-hindi text-base italic text-ink-3 leading-snug">{last.transcript ? `\u201C${last.transcript}\u201D` : last.spoken_text}</p>
            <SourceChip source={last.source} latency={last.latency_ms} demo={last.demo_mode && last.source === 'fixture'} />
          </div>
        )}

        {parchi && stage === 'cart' && parchi.unmatched?.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {parchi.unmatched.map((u) => (
              <button key={u.name} onClick={() => noteMissed(u.name)} className="min-h-[44px] px-3 rounded-full bg-orange-50 text-sm font-semibold text-orange-900">
                {u.name} nahi hai
              </button>
            ))}
          </div>
        )}

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
            {isEmpty && !last && !pending.length && (
              <div className="pt-16 text-center">
                <div className="font-hindi text-3xl font-semibold text-ink leading-tight">Boliye, kya dena hai?</div>
                <button onClick={() => voiceSubmit({ text: room.examples[0] })} className="mt-3 min-h-[44px] px-2 font-hindi text-base italic text-ink-3">
                  &ldquo;{room.hint}&rdquo;
                </button>
              </div>
            )}
          </>
        )}

        {stage === 'pay' && checkout && <PayQR checkout={checkout} onPaid={onPaid} onBack={newBill} />}
        {stage === 'paid' && paid && <PaidView data={paid} onNew={newBill} />}
      </div>

      {stage === 'cart' && !isEmpty && (
        <div className="sticky bottom-0 z-10 px-4 pt-3 pb-11 bg-bg-app">
          <button onClick={() => setPayOpen(true)} className="w-full min-h-[56px] rounded-xl bg-ink text-white px-5 flex items-center justify-between text-lg font-semibold active:bg-ink-2">
            <span>Bill banao</span>
            <span className="tabular">{inr(cart.total)}</span>
          </button>
        </div>
      )}

      <CustomerSheet open={customerOpen} onClose={() => setCustomerOpen(false)} onPick={pickCustomer} />
      <PaySheet open={payOpen} onClose={() => setPayOpen(false)} total={cart?.total || 0} customer={customer} busy={paying} onConfirm={doCheckout} />
    </div>
  )
}
