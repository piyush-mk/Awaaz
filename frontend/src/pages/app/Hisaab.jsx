import { useState } from 'react'
import { ErrorBox, Hero, Rows, SkeletonList, Tabs } from '../../components/app/ui'
import { HourlyChart, SeriesChart } from '../../components/app/hisaab/Charts'
import Galla from '../../components/app/hisaab/Galla'
import Invoices from '../../components/app/hisaab/Invoices'
import { useStoreEvent } from '../../components/app/AppContext'
import useLoad from '../../lib/useLoad'
import { getDashboardV2 } from '../../api/client'
import { inr, qtyLabel } from '../../lib/format'
import { tr } from '../../lib/i18n'

const TABS = [
  { id: 'today', label: tr('Aaj') },
  { id: 'bills', label: tr('Bill') },
  { id: 'galla', label: tr('Galla') },
]

const SPLIT = [
  { key: 'cash', label: tr('Cash'), color: '#0E1B33' },
  { key: 'upi', label: tr('Paytm / UPI'), color: '#00B9F5' },
  { key: 'khata', label: tr('Khata'), color: '#FF8A1F' },
  { key: 'postpaid', label: tr('Postpaid'), color: '#8A97AB' },
  { key: 'card', label: tr('Card'), color: '#B8C2D0' },
]

function Line({ label, value, sub }) {
  return (
    <li className="flex items-center justify-between gap-3 px-4 py-3">
      <div className="min-w-0">
        <div className="text-base truncate">{label}</div>
        {sub && <div className="text-sm text-ink-3 truncate">{sub}</div>}
      </div>
      <div className="font-semibold tabular flex-shrink-0">{value}</div>
    </li>
  )
}

function Today() {
  const { data: d, loading, error, reload } = useLoad(() => getDashboardV2(), [])
  const refresh = () => reload({ quiet: true })
  useStoreEvent('payment_received', refresh)
  useStoreEvent('checkout', refresh)
  useStoreEvent('khata_updated', refresh)
  useStoreEvent('stock_updated', refresh)
  useStoreEvent('demo_reset', refresh)
  if (loading && !d) return <SkeletonList rows={4} className="h-28" />
  if (error) return <ErrorBox error={error} onRetry={reload} />
  if (!d) return null

  const split = SPLIT.map((s) => ({ ...s, amount: d.payment_split[s.key] || 0, pct: d.payment_split_pct[s.key] || 0 })).filter((s) => s.amount > 0)

  return (
    <div className="space-y-5">
      <Hero value={inr(d.today.sales)} sub={tr('{n} bill, margin {m}', { n: d.today.invoices, m: inr(d.margin.margin, 0) })} />

      <div>
        <HourlyChart data={d.hourly} />
        <div className="text-sm text-ink-3 mt-1">{tr('Kal {amt}', { amt: inr(d.yesterday.sales) })}</div>
      </div>

      {split.length > 0 && (
        <div>
          <div className="flex h-2 rounded-full overflow-hidden bg-bg-app mb-1">
            {split.map((s) => (
              <div key={s.key} style={{ width: `${s.pct}%`, background: s.color }} title={`${s.label} ${s.pct}%`} />
            ))}
          </div>
          <Rows className="!border-t-0">
            {split.map((s) => <Line key={s.key} label={s.label} value={inr(s.amount)} />)}
          </Rows>
        </div>
      )}

      <div>
        <div className="font-hindi text-lg font-semibold mb-1">{tr('Sabse zyada bika')}</div>
        <Rows>
          {d.top_items.map((t) => <Line key={t.product_id} label={`${t.name}, ${qtyLabel(t.qty, t.unit)}`} value={inr(t.amount)} />)}
        </Rows>
      </div>

      <div>
        <div className="font-hindi text-lg font-semibold mb-1">{tr('Pichhle 14 din')}</div>
        <SeriesChart data={d.series} />
      </div>

      <Rows>
        <Line label={tr('Udhaar baaki')} value={inr(d.udhaar.total_outstanding)} />
        <Line label={tr('Stock ki value')} value={inr(d.total_stock_value)} />
      </Rows>
    </div>
  )
}

export default function Hisaab() {
  const [tab, setTab] = useState('today')
  return (
    <div className="px-4 pb-16">
      <Tabs items={TABS} value={tab} onChange={setTab} />
      <div className="mt-4">
        {tab === 'today' && <Today />}
        {tab === 'bills' && <Invoices />}
        {tab === 'galla' && <Galla />}
      </div>
    </div>
  )
}
