import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Image as ImageIcon, MessageSquareText, Mic, ShoppingBasket } from 'lucide-react'
import ConfirmCard from '../ConfirmCard'
import SourceChip from '../SourceChip'
import { Btn, Card, Chip, Empty, ErrorBox, SkeletonList } from '../ui'
import { useApp, useStoreEvent } from '../AppContext'
import useLoad from '../../../lib/useLoad'
import { addCartLines, attachCartCustomer, cancelWaOrder, confirmWaOrder, listWaOrders } from '../../../api/client'
import { inr, qtyLabel } from '../../../lib/format'

const ICON = { text: MessageSquareText, audio: Mic, image: ImageIcon }

function OrderCard({ order, onResolved }) {
  const { sessionId, showError, showToast } = useApp()
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const p = order.payload || {}
  const Icon = ICON[p.input_type] || MessageSquareText

  const resolve = async (kind) => {
    setBusy(true)
    try {
      await (kind === 'confirm' ? confirmWaOrder(order.id) : cancelWaOrder(order.id))
      showToast(kind === 'confirm' ? 'Customer ko WhatsApp bhej diya' : 'Order cancel kiya', kind === 'confirm' ? 'success' : 'warning')
      onResolved()
    } catch (e) {
      showError(e)
    } finally {
      setBusy(false)
    }
  }

  const toCounter = async () => {
    setBusy(true)
    try {
      if (p.customer_id) await attachCartCustomer(sessionId, { customer_id: p.customer_id }).catch(() => {})
      await addCartLines(sessionId, p.lines.map((l) => ({ product_id: l.product_id, qty: l.qty, unit: l.unit })), 'add')
      // The order is now being billed: take it off this list and tell the customer.
      await confirmWaOrder(order.id).catch(() => {})
      showToast('Counter par bill taiyaar')
      navigate('/app/counter')
    } catch (e) {
      showError(e)
      setBusy(false)
    }
  }

  return (
    <Card>
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <Icon size={18} className="text-paytm-blue flex-shrink-0" />
            <span className="font-hindi text-xl font-bold truncate">{p.customer}</span>
          </div>
          {p.transcript && <p className="mt-1 text-sm text-ink-3 italic">&ldquo;{p.transcript}&rdquo;</p>}
        </div>
        <SourceChip source={order.source} latency={order.latency_ms} demo={order.source === 'fixture'} />
      </div>
      <ul className="mt-3 divide-y divide-line">
        {p.lines.map((l) => (
          <li key={l.product_id} className="py-1.5 flex items-center justify-between">
            <span className="font-hindi text-base font-bold">{l.name_hi || l.name}</span>
            <span className="text-sm text-ink-3 tabular">{qtyLabel(l.qty, l.unit)}</span>
            <b className="tabular w-16 text-right">{inr(l.line_total)}</b>
          </li>
        ))}
      </ul>
      {p.unmatched?.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {p.unmatched.map((u, i) => <Chip key={i} tone="yellow">nahi mila: {u.name}</Chip>)}
        </div>
      )}
      <div className="mt-2 flex items-baseline justify-between border-t border-line pt-2">
        <span className="text-ink-3 text-sm">Kul</span>
        <b className="text-xl tabular">{inr(p.total)}</b>
      </div>

      <Btn variant="navy" icon={ShoppingBasket} className="w-full mt-3" busy={busy} onClick={toCounter}>Bill banao (counter par)</Btn>
      <div className="mt-3">
        <ConfirmCard question="Order pakka karun? Customer ko WhatsApp jayega" busy={busy} onYes={() => resolve('confirm')} onNo={() => resolve('cancel')} noLabel="Cancel" />
      </div>
    </Card>
  )
}

export default function WaOrders() {
  const { data, loading, error, reload } = useLoad(() => listWaOrders('proposed'), [])
  useStoreEvent('wa_order', () => reload({ quiet: true }))
  useStoreEvent('wa_order_updated', () => reload({ quiet: true }))
  useStoreEvent('demo_reset', () => reload({ quiet: true }))

  return (
    <div className="space-y-3">
      {loading && !data && <SkeletonList rows={2} className="h-40" />}
      <ErrorBox error={error} onRetry={reload} />
      {data && data.length === 0 && <Empty icon={MessageSquareText} hi="Koi naya WhatsApp order nahi" en="Customer ka order yahin dikhega" />}
      {data?.map((o) => <OrderCard key={o.id} order={o} onResolved={() => reload({ quiet: true })} />)}
    </div>
  )
}
