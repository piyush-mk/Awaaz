import { useState } from 'react'
import { AlertTriangle, FileText, Gift, Clock, PackagePlus, TrendingUp, Volume2 } from 'lucide-react'
import PhotoButton from '../PhotoButton'
import ConfirmCard from '../ConfirmCard'
import SourceChip from '../SourceChip'
import { Btn, Card, Chip, Empty, Stepper } from '../ui'
import { useApp } from '../AppContext'
import { cancelPurchase, confirmPurchase, scanPurchase } from '../../../api/client'
import { speak } from '../../../lib/audio'
import { inr, num } from '../../../lib/format'

const FLAG = {
  price_increase: { icon: TrendingUp, tone: 'bg-red-50 border-red-200 text-red-800', label: 'Rate badha' },
  scheme_missed: { icon: Gift, tone: 'bg-orange-50 border-orange-300 text-orange-900', label: 'Free maal nahi mila' },
  expiry_soon: { icon: Clock, tone: 'bg-yellow-50 border-yellow-300 text-yellow-900', label: 'Jaldi expire' },
  new_product: { icon: PackagePlus, tone: 'bg-sky-50 border-sky-200 text-sky-900', label: 'Naya item' },
  low_margin: { icon: AlertTriangle, tone: 'bg-yellow-50 border-yellow-300 text-yellow-900', label: 'Kam margin' },
  duplicate_bill: { icon: AlertTriangle, tone: 'bg-red-50 border-red-200 text-red-800', label: 'Bill pehle aa chuka' },
}

function FlagRow({ flag }) {
  const f = FLAG[flag.code] || { icon: AlertTriangle, tone: 'bg-bg-app border-line text-ink', label: flag.code }
  const Icon = f.icon
  return (
    <div className={`flex items-start gap-2 rounded-xl px-3 py-2 ${f.tone}`}>
      <Icon size={18} className="flex-shrink-0 mt-0.5" />
      <div className="text-sm font-medium leading-snug">{flag.message}</div>
    </div>
  )
}

export default function BillScanTab() {
  const { showError, showToast } = useApp()
  const [busy, setBusy] = useState(false)
  const [bill, setBill] = useState(null)
  const [qty, setQty] = useState({})
  const [free, setFree] = useState({})
  const [skip, setSkip] = useState({})
  const [confirming, setConfirming] = useState(false)
  const [done, setDone] = useState(null)

  const reset = () => {
    setBill(null)
    setDone(null)
    setQty({})
    setFree({})
    setSkip({})
  }

  const scan = async (files) => {
    setBusy(true)
    reset()
    try {
      const res = await scanPurchase(files[0])
      setBill(res)
      speak({ spoken_text: res.message_hi })
    } catch (e) {
      showError(e)
    } finally {
      setBusy(false)
    }
  }

  const confirm = async () => {
    setConfirming(true)
    try {
      const lines = bill.lines
        .filter((l) => qty[l.index] !== undefined || free[l.index] !== undefined || skip[l.index])
        .map((l) => ({
          index: l.index,
          ...(qty[l.index] !== undefined ? { qty: qty[l.index] } : {}),
          ...(free[l.index] !== undefined ? { free_qty: free[l.index] } : {}),
          ...(skip[l.index] ? { skip: true } : {}),
        }))
      const res = await confirmPurchase(bill.action_id, { lines, create_new_products: true })
      setDone(res)
      speak({ spoken_text: `Bill darj ho gaya. ${res.items_recorded} item stock mein jude.` })
    } catch (e) {
      showError(e)
    } finally {
      setConfirming(false)
    }
  }

  const cancel = async () => {
    try {
      await cancelPurchase(bill.action_id)
      showToast('Bill chhod diya', 'warning')
    } catch (e) {
      showError(e)
    }
    reset()
  }

  if (done) {
    return (
      <Card className="text-center">
        <div className="font-hindi text-2xl font-bold">Stock jud gaya</div>
        <div className="text-ink-3">{done.supplier}, {done.bill_no}, {inr(done.total)}</div>
        <ul className="mt-3 text-left space-y-1">
          {done.stock_updates.map((u) => (
            <li key={u.product_id} className="flex justify-between text-sm">
              <span className="font-semibold">{u.name}</span>
              <span className="tabular text-ink-3">{num(u.old_stock)} se <b className="text-ink">{num(u.new_stock)}</b> (+{num(u.added)})</span>
            </li>
          ))}
        </ul>
        {done.new_products?.length > 0 && <div className="mt-2 text-sm text-ink-3">Naye item: {done.new_products.map((p) => p.name).join(', ')}</div>}
        <Btn className="w-full mt-4" variant="navy" onClick={reset}>Doosra bill</Btn>
      </Card>
    )
  }

  if (!bill) {
    return (
      <div className="space-y-3">
        <Empty icon={FileText} hi="Distributor ka bill scan karein" en="Photo lein: rate, free maal, expiry sab check hoga">
          <PhotoButton variant="blue" busy={busy} label="Bill ki photo" onFiles={scan} />
        </Empty>
        {busy && <div className="text-center text-sm text-ink-3">Bill padh raha hoon...</div>}
      </div>
    )
  }

  if (!bill.lines?.length) {
    return (
      <Empty icon={FileText} hi="Is photo mein bill padh nahi paya" en="Poora bill frame mein rakhein, saaf roshni mein">
        <PhotoButton variant="blue" busy={busy} label="Doosri photo" onFiles={scan} />
      </Empty>
    )
  }

  const warnings = (bill.flags || []).filter((f) => f.severity !== 'info')
  return (
    <div className="space-y-3">
      <Card>
        <div className="flex items-start gap-2">
          <div className="flex-1 min-w-0">
            <div className="font-hindi text-xl font-bold truncate">{bill.supplier?.name}</div>
            <div className="text-sm text-ink-3">{bill.bill_no}, {bill.bill_date}</div>
          </div>
          <SourceChip source={bill.source} latency={bill.latency_ms} demo={bill.demo_mode} />
        </div>
        <div className="mt-2 flex items-baseline justify-between">
          <span className="text-ink-3 text-sm">{bill.summary?.lines} item</span>
          <span className="text-2xl font-bold tabular">{inr(bill.total)}</span>
        </div>
        {bill.duplicate?.is_duplicate && <Chip tone="red" className="mt-2">Yeh bill pehle darj ho chuka hai</Chip>}
        {bill.message_hi && (
          <button onClick={() => speak({ spoken_text: bill.message_hi })} className="mt-3 w-full text-left rounded-xl bg-white p-3 flex gap-2">
            <Volume2 size={18} className="flex-shrink-0 mt-1 text-paytm-blue" />
            <span className="font-hindi text-base">{bill.message_hi}</span>
          </button>
        )}
      </Card>

      {warnings.length > 0 && (
        <div className="space-y-2">
          <div className="font-hindi text-lg font-bold px-1">Dhyan dein ({warnings.length})</div>
          {warnings.map((f, i) => <FlagRow key={i} flag={f} />)}
        </div>
      )}

      <div className="font-hindi text-lg font-bold px-1">Bill ke item</div>
      <ul className="space-y-2">
        {bill.lines.map((l) => {
          const skipped = !!skip[l.index]
          const q = qty[l.index] ?? l.qty
          const hot = l.flags?.some((f) => f.severity === 'warn')
          return (
            <li key={l.index} className={`rounded-2xl p-3 ${skipped ? 'opacity-40' : ''} ${hot ? 'bg-orange-50' : 'bg-bg-app'}`}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="font-hindi text-base font-bold leading-tight">{l.product_name || l.name_raw}</div>
                  <div className="text-xs text-ink-3 truncate">{l.name_raw}, batch {l.batch || '-'}, exp {l.expiry || '-'}</div>
                </div>
                <div className="text-right flex-shrink-0 tabular">
                  <div className="font-bold">{inr(q * l.rate)}</div>
                  <div className="text-xs text-ink-3">{inr(l.rate)} x {num(q)}</div>
                </div>
              </div>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {l.is_new_candidate && <Chip tone="blue">naya item</Chip>}
                {l.rate_delta > 0 && <Chip tone="red">+{inr(l.rate_delta)} ({num(l.rate_delta_pct, 1)}%)</Chip>}
                {l.free_qty_expected > 0 && <Chip tone={(free[l.index] ?? l.free_qty_received) >= l.free_qty_expected ? 'green' : 'orange'}>{l.scheme_text}</Chip>}
                {l.flags?.some((f) => f.code === 'expiry_soon') && <Chip tone="yellow">{l.days_to_expiry} din mein expire</Chip>}
              </div>
              <div className="mt-2 flex items-center justify-between gap-2">
                <Stepper value={q} step={l.unit === 'kg' ? 0.5 : 1} onChange={(v) => setQty((s) => ({ ...s, [l.index]: v }))} />
                {l.free_qty_expected > 0 && (
                  <label className="flex items-center gap-1.5 text-sm font-semibold">
                    Free mila
                    <Stepper value={free[l.index] ?? l.free_qty_received} onChange={(v) => setFree((s) => ({ ...s, [l.index]: v }))} />
                  </label>
                )}
                <button onClick={() => setSkip((s) => ({ ...s, [l.index]: !s[l.index] }))} className="min-h-[44px] px-3 text-sm font-semibold text-ink-3 underline">
                  {skipped ? 'Wapas jodein' : 'Hatayein'}
                </button>
              </div>
            </li>
          )
        })}
      </ul>

      <ConfirmCard
        question={`Stock mein jodun? ${inr(bill.total)}`}
        warn={warnings.length ? `${warnings.length} cheezein check karni hain (upar dekhein)` : null}
        busy={confirming}
        onYes={confirm}
        onNo={cancel}
        yesLabel="Haan, jodo"
        tone="orange"
      />
    </div>
  )
}
