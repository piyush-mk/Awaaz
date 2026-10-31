import { useState } from 'react'
import { FileText, RotateCcw, Trash2 } from 'lucide-react'
import PhotoButton from '../PhotoButton'
import ConfirmCard from '../ConfirmCard'
import SourceChip from '../SourceChip'
import { Btn, Card, Chip, Empty, Stepper } from '../ui'
import { useApp } from '../AppContext'
import { cancelPurchase, confirmPurchase, scanPurchase } from '../../../api/client'
import { speak } from '../../../lib/audio'
import { inr, num } from '../../../lib/format'

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
        <div className="pt-16 flex justify-center">
          <PhotoButton variant="blue" busy={busy} label="Bill ki photo" onFiles={scan} className="min-h-[64px] !px-8 text-lg" />
        </div>
      </div>
    )
  }

  if (!bill.lines?.length) {
    return (
      <Empty icon={FileText} hi="Bill padh nahi paya">
        <PhotoButton variant="blue" busy={busy} label="Doosri photo" onFiles={scan} />
      </Empty>
    )
  }

  const isHot = (l) => l.flags?.some((f) => f.severity === 'warn')
  const lines = [...bill.lines].sort((x, y) => isHot(y) - isHot(x))
  return (
    <div className="space-y-3">
      <Card>
        <div className="flex items-start gap-2">
          <div className="flex-1 min-w-0">
            <div className="font-hindi text-xl font-bold truncate">{bill.supplier?.name}</div>
            <div className="text-sm text-ink-3">{bill.bill_no}</div>
          </div>
          <SourceChip source={bill.source} latency={bill.latency_ms} demo={bill.demo_mode} />
        </div>
        <div className="mt-2 flex items-baseline justify-between">
          <span className="text-ink-3 text-sm">{bill.summary?.lines} item</span>
          <span className="text-2xl font-bold tabular">{inr(bill.total)}</span>
        </div>
        {bill.duplicate?.is_duplicate && <Chip tone="red" className="mt-2">Yeh bill pehle darj ho chuka hai</Chip>}
      </Card>

      <ul className="space-y-2">
        {lines.map((l) => {
          const skipped = !!skip[l.index]
          const q = qty[l.index] ?? l.qty
          const hot = isHot(l)
          return (
            <li key={l.index} className={`rounded-2xl p-3 ${skipped ? 'opacity-40' : ''} ${hot ? 'bg-orange-50' : 'bg-bg-app'}`}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="font-hindi text-base font-bold leading-tight">{l.product_name || l.name_raw}</div>
                </div>
                <div className="text-right flex-shrink-0 tabular">
                  <div className="font-bold">{inr(q * l.rate)}</div>
                  <div className="text-xs text-ink-3">{inr(l.rate)} x {num(q)}</div>
                </div>
              </div>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {l.is_new_candidate && <Chip tone="blue">naya</Chip>}
                {l.rate_delta > 0 && <Chip tone="red">+{inr(l.rate_delta)}</Chip>}
                {l.free_qty_expected > (free[l.index] ?? l.free_qty_received) && <Chip tone="orange">{l.free_qty_expected} free nahi mila</Chip>}
                {l.flags?.some((f) => f.code === 'expiry_soon') && <Chip tone="yellow">{l.days_to_expiry} din expiry</Chip>}
                {l.flags?.some((f) => f.code === 'low_margin') && <Chip tone="yellow">kam margin</Chip>}
              </div>
              <div className="mt-2 flex items-center justify-between gap-2">
                <Stepper value={q} step={l.unit === 'kg' ? 0.5 : 1} onChange={(v) => setQty((s) => ({ ...s, [l.index]: v }))} />
                <button onClick={() => setSkip((s) => ({ ...s, [l.index]: !s[l.index] }))} aria-label={skipped ? 'Wapas jodein' : 'Hatayein'} className="w-11 h-11 flex items-center justify-center text-ink-3">
                  {skipped ? <RotateCcw size={20} /> : <Trash2 size={20} />}
                </button>
              </div>
              {l.free_qty_expected > 0 && (
                <div className="mt-1 flex items-center justify-between gap-2 text-sm font-medium">
                  Free mila
                  <Stepper value={free[l.index] ?? l.free_qty_received} onChange={(v) => setFree((s) => ({ ...s, [l.index]: v }))} />
                </div>
              )}
            </li>
          )
        })}
      </ul>

      <ConfirmCard
        question={`Stock mein jodun? ${inr(bill.total)}`}
        busy={confirming}
        onYes={confirm}
        onNo={cancel}
        yesLabel="Haan, jodo"
        tone="orange"
      />
    </div>
  )
}
