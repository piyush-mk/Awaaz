import { useState } from 'react'
import { MessageCircle, PackageSearch, Truck } from 'lucide-react'
import ConfirmCard from '../ConfirmCard'
import { Btn, Card, Chip, Empty, ErrorBox, SkeletonList, Stepper } from '../ui'
import { useApp } from '../AppContext'
import useLoad from '../../../lib/useLoad'
import { draftReorder, listReorders, sendReorder } from '../../../api/client'
import { speak } from '../../../lib/audio'
import { inr, num } from '../../../lib/format'

function PoCard({ po, onSent }) {
  const { showError } = useApp()
  const [qty, setQty] = useState({})
  const [asking, setAsking] = useState(false)
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState(null)

  const lines = po.lines.map((l) => ({ ...l, qty: qty[l.product_id] ?? l.qty }))
  const total = lines.reduce((s, l) => s + l.qty * (l.est_rate || 0), 0)

  const send = async () => {
    setBusy(true)
    try {
      const edits = Object.entries(qty).map(([product_id, q]) => ({ product_id: Number(product_id), qty: q }))
      const res = await sendReorder(po.action_id, edits)
      setSent(res)
      setAsking(false)
      onSent?.(res)
      speak({ spoken_text: `${po.supplier_name} ko order bhej diya.` })
    } catch (e) {
      showError(e)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card className={po.festival ? '!border-accent !border-2' : ''}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="font-hindi text-xl font-bold truncate">{po.supplier_name}</div>
          <div className="text-xs text-ink-3 flex items-center gap-1"><Truck size={12} /> {po.contact_name} . {po.lead_days} din mein . {po.po_number}</div>
        </div>
        {po.festival && <Chip tone="orange">{po.festival.name} {po.festival.days_away}d</Chip>}
      </div>

      <ul className="mt-3 divide-y divide-line">
        {lines.map((l) => (
          <li key={l.product_id} className="py-2">
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="font-hindi text-base font-bold truncate">{l.name_hi || l.name}</div>
                <div className="text-xs text-ink-3">{l.reason}</div>
              </div>
              {l.multiplier > 1 && <Chip tone="orange">{l.multiplier}x</Chip>}
            </div>
            <div className="mt-1 flex items-center justify-between">
              {sent ? (
                <b className="tabular">{num(l.qty)} {l.unit}</b>
              ) : (
                <Stepper value={l.qty} step={l.unit === 'kg' ? 1 : l.qty >= 50 ? 10 : 1} unit={l.unit} onChange={(v) => setQty((s) => ({ ...s, [l.product_id]: v }))} />
              )}
              <span className="text-sm text-ink-3 tabular">stock {num(l.current_stock)} . ~{inr(l.qty * (l.est_rate || 0))}</span>
            </div>
          </li>
        ))}
      </ul>

      <div className="mt-2 flex items-baseline justify-between border-t border-line pt-2">
        <span className="text-ink-3 text-sm">Andaaza</span>
        <b className="text-xl tabular">{inr(total)}</b>
      </div>

      {sent ? (
        <div className="mt-3 rounded-2xl bg-[#DCF8C6] p-3">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-green-900 mb-1"><MessageCircle size={14} /> WhatsApp {sent.message?.status} . {sent.message?.channel === 'sim' ? 'simulator' : 'real'}</div>
          <p className="text-sm whitespace-pre-line">{sent.message?.body}</p>
        </div>
      ) : asking ? (
        <div className="mt-3">
          <ConfirmCard question={`${po.supplier_name} ko WhatsApp par order bhejun?`} busy={busy} onYes={send} onNo={() => setAsking(false)} yesLabel="Haan, bhejo" tone="orange" />
        </div>
      ) : (
        <Btn variant="navy" icon={MessageCircle} className="w-full mt-3" onClick={() => setAsking(true)}>WhatsApp bhejo</Btn>
      )}
    </Card>
  )
}

export default function ReorderCards() {
  const { showError } = useApp()
  const { data, loading, error, reload, setData } = useLoad(() => listReorders({ status: 'proposed' }), [])
  const [drafting, setDrafting] = useState(false)

  const draft = async () => {
    setDrafting(true)
    try {
      const res = await draftReorder()
      setData({ orders: res.orders, count: res.count, unassigned: res.unassigned })
    } catch (e) {
      showError(e)
    } finally {
      setDrafting(false)
    }
  }

  return (
    <div className="space-y-3">
      <Btn size="lg" variant="primary" icon={PackageSearch} busy={drafting} className="w-full" onClick={draft}>Aaj ka order banao</Btn>
      {loading && !data && <SkeletonList rows={2} className="h-40" />}
      <ErrorBox error={error} onRetry={reload} />
      {data && data.orders.length === 0 && <Empty icon={Truck} hi="Abhi koi order draft nahi" en="Upar ka button dabayein" />}
      {data?.unassigned?.length > 0 && (
        <div className="rounded-xl bg-yellow-50 border border-yellow-300 px-3 py-2 text-sm text-yellow-900">
          Supplier tay nahi: {data.unassigned.map((u) => u.name || u.product_name || u).join(', ')}
        </div>
      )}
      {data?.orders.map((po) => <PoCard key={po.action_id} po={po} />)}
    </div>
  )
}
