import { useState } from 'react'
import { Card, ErrorBox, SectionTitle, SkeletonList, Tabs } from '../../components/app/ui'
import { HourlyChart, SeriesChart } from '../../components/app/hisaab/Charts'
import Galla from '../../components/app/hisaab/Galla'
import Invoices from '../../components/app/hisaab/Invoices'
import { useStoreEvent } from '../../components/app/AppContext'
import useLoad from '../../lib/useLoad'
import { getDashboardV2 } from '../../api/client'
import { inr, num } from '../../lib/format'

const TABS = [
  { id: 'today', hi: 'आज', en: 'Today' },
  { id: 'bills', hi: 'बिल', en: 'Invoices' },
  { id: 'galla', hi: 'गल्ला', en: 'Cash close' },
]

const SPLIT = [
  { key: 'cash', label: 'Cash', color: '#0E1B33' },
  { key: 'upi', label: 'Paytm / UPI', color: '#00B9F5' },
  { key: 'khata', label: 'Khata', color: '#FF8A1F' },
  { key: 'postpaid', label: 'Postpaid', color: '#8A97AB' },
  { key: 'card', label: 'Card', color: '#B8C2D0' },
]

function Tile({ label, value, sub, tone }) {
  return (
    <Card className="!p-3">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-ink-3">{label}</div>
      <div className="text-2xl font-bold tabular leading-tight">{value}</div>
      {sub && <div className={`text-xs mt-0.5 ${tone || 'text-ink-3'}`}>{sub}</div>}
    </Card>
  )
}

function Today() {
  const { data: d, loading, error, reload } = useLoad(() => getDashboardV2(), [])
  useStoreEvent('payment_received', () => reload({ quiet: true }))
  if (loading && !d) return <SkeletonList rows={4} className="h-28" />
  if (error) return <ErrorBox error={error} onRetry={reload} />
  if (!d) return null

  const delta = d.yesterday?.vs_last_week_pct
  const split = SPLIT.map((s) => ({ ...s, amount: d.payment_split[s.key] || 0, pct: d.payment_split_pct[s.key] || 0 })).filter((s) => s.amount > 0)

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <Tile label="Aaj ki sale" value={inr(d.today.sales)} sub={`${d.today.invoices} bill`} />
        <Tile label="Avg bill" value={inr(d.today.avg_bill, 0)} sub={`kal ${inr(d.yesterday.sales)}`} />
        <Tile label="Margin" value={inr(d.margin.margin, 0)} sub={`${num(d.margin.margin_pct, 1)}% of sale`} tone="text-green-700" />
        <Tile
          label="Kal vs pichla hafta"
          value={`${delta > 0 ? '+' : ''}${num(delta, 0)}%`}
          sub={delta >= 0 ? 'zyada' : 'kam'}
          tone={delta >= 0 ? 'text-green-700' : 'text-stock-red'}
        />
      </div>

      <Card>
        <div className="font-hindi text-lg font-bold mb-2">Paisa kaise aaya</div>
        <div className="flex h-5 rounded-full overflow-hidden bg-bg-app">
          {split.map((s) => (
            <div key={s.key} style={{ width: `${s.pct}%`, background: s.color }} title={`${s.label} ${s.pct}%`} />
          ))}
        </div>
        <ul className="mt-3 space-y-1.5">
          {split.map((s) => (
            <li key={s.key} className="flex items-center gap-2 text-sm">
              <span className="w-3 h-3 rounded-sm flex-shrink-0" style={{ background: s.color }} />
              <span className="flex-1">{s.label}</span>
              <span className="text-ink-3 tabular">{num(s.pct, 0)}%</span>
              <b className="tabular w-24 text-right">{inr(s.amount)}</b>
            </li>
          ))}
        </ul>
      </Card>

      <Card>
        <div className="font-hindi text-lg font-bold">Ghante ke hisaab se</div>
        <div className="text-xs text-ink-3 mb-1">Aaj, ghanta {d.hourly.length ? '7 se 22' : ''}</div>
        <HourlyChart data={d.hourly} />
      </Card>

      <Card>
        <div className="font-hindi text-lg font-bold">Pichhle 14 din</div>
        <div className="text-xs text-ink-3 mb-1">Halka bar: aaj, abhi tak</div>
        <SeriesChart data={d.series} />
      </Card>

      <Card>
        <div className="font-hindi text-lg font-bold mb-2">Aaj sabse zyada bika</div>
        <ul className="divide-y divide-line">
          {d.top_items.map((t, i) => (
            <li key={t.product_id} className="flex items-center gap-3 py-2">
              <span className="w-6 text-ink-3 tabular text-sm">{i + 1}</span>
              <span className="flex-1 font-semibold">{t.name}</span>
              <span className="text-ink-3 text-sm tabular">{num(t.qty)} {t.unit}</span>
              <b className="tabular w-20 text-right">{inr(t.amount)}</b>
            </li>
          ))}
        </ul>
      </Card>

      <div className="grid grid-cols-2 gap-3">
        <Tile label="Udhaar baaki" value={inr(d.udhaar.total_outstanding)} sub={`${d.udhaar.customers_with_balance} customer . ${d.udhaar.overdue_count} late`} tone="text-orange-700" />
        <Tile label="Stock value" value={inr(d.total_stock_value)} sub={`${d.low_stock_count} item kam`} tone={d.low_stock_count ? 'text-stock-red' : undefined} />
      </div>
    </div>
  )
}

export default function Hisaab() {
  const [tab, setTab] = useState('today')
  return (
    <div className="px-4 pt-3 pb-6">
      <SectionTitle hi="हिसाब" en="Hisaab: aaj kitna bika" />
      <Tabs items={TABS} value={tab} onChange={setTab} />
      <div className="mt-2">
        {tab === 'today' && <Today />}
        {tab === 'bills' && <Invoices />}
        {tab === 'galla' && <Galla />}
      </div>
    </div>
  )
}
