import { useEffect, useState } from 'react'
import { ChevronDown, Search, Boxes } from 'lucide-react'
import { Card, Chip, Empty, ErrorBox, SkeletonList, inputCls } from '../ui'
import useLoad from '../../../lib/useLoad'
import { useStoreEvent } from '../AppContext'
import { getStock } from '../../../api/client'
import { inr, num, qtyLabel, shortDate } from '../../../lib/format'

const SORTS = [
  { id: 'id', label: 'Sab' },
  { id: 'cover', label: 'Kam cover' },
  { id: 'expiry', label: 'Expiry' },
  { id: 'value', label: 'Value' },
]
const DOT = { low: 'bg-stock-red', medium: 'bg-stock-yellow', high: 'bg-stock-green' }

function Row({ item }) {
  const [open, setOpen] = useState(false)
  const cover = item.days_of_cover
  return (
    <li className="bg-white rounded-2xl border border-line overflow-hidden">
      <button onClick={() => setOpen((v) => !v)} className="w-full min-h-[64px] px-3 py-2 flex items-center gap-3 text-left">
        <span className={`w-3 h-3 rounded-full flex-shrink-0 ${DOT[item.status] || 'bg-line'}`} />
        <div className="min-w-0 flex-1">
          <div className="font-hindi text-lg font-bold leading-tight truncate">{item.name_hi || item.name}</div>
          <div className="text-xs text-ink-3 truncate">
            {item.name_hi ? `${item.name} . ` : ''}
            {inr(item.price)}/{item.unit}
          </div>
        </div>
        <div className="text-right flex-shrink-0">
          <div className="font-bold tabular">{qtyLabel(item.qty, item.unit)}</div>
          <div className="flex gap-1 justify-end mt-0.5">
            {cover != null && <Chip tone={cover < 3 ? 'red' : cover < 7 ? 'yellow' : 'gray'}>{num(cover, 1)} din</Chip>}
            {(item.expiry_status === 'soon' || item.expiry_status === 'expired') && (
              <Chip tone="orange">{item.expiry_status === 'expired' ? 'expired' : `${item.days_to_expiry}d expiry`}</Chip>
            )}
          </div>
        </div>
        <ChevronDown size={18} className={`text-ink-3 flex-shrink-0 ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="px-3 pb-3 border-t border-line pt-2 text-sm space-y-2">
          <div className="grid grid-cols-3 gap-2 tabular">
            <div><div className="text-xs text-ink-3">Cost</div><b>{item.last_cost_price != null ? inr(item.last_cost_price) : inr(item.cost_price)}</b></div>
            <div><div className="text-xs text-ink-3">Margin</div><b>{item.margin_pct != null ? `${num(item.margin_pct, 1)}%` : '-'}</b></div>
            <div><div className="text-xs text-ink-3">Value</div><b>{inr(item.stock_value)}</b></div>
          </div>
          <div className="text-xs text-ink-3">
            {num(item.velocity_per_day, 1)} {item.unit}/din bikta hai . threshold {num(item.threshold)}
            {item.supplier_name ? ` . ${item.supplier_name}` : ''}
          </div>
          {item.festival_multiplier > 1 && <Chip tone="orange">tyohar ke liye {item.festival_multiplier}x demand</Chip>}
          {item.batches?.length > 0 ? (
            <ul className="space-y-1">
              {item.batches.map((b) => (
                <li key={b.batch_id} className="flex justify-between rounded-lg bg-bg-app px-2.5 py-1.5">
                  <span className="font-mono text-xs">{b.batch_no || 'batch'}</span>
                  <span className="tabular">{num(b.qty, 2)} {item.unit}</span>
                  <span className={`text-xs ${b.days_to_expiry != null && b.days_to_expiry <= 7 ? 'text-stock-red font-bold' : 'text-ink-3'}`}>
                    {b.expiry ? `exp ${shortDate(b.expiry)}` : 'no expiry'}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <div className="text-xs text-ink-3">Koi batch nahi</div>
          )}
        </div>
      )}
    </li>
  )
}

export default function StockTab() {
  const [q, setQ] = useState('')
  const [debounced, setDebounced] = useState('')
  const [sort, setSort] = useState('id')
  const [lowOnly, setLowOnly] = useState(false)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 250)
    return () => clearTimeout(t)
  }, [q])

  const { data, loading, error, reload } = useLoad(
    () => getStock({ q: debounced, sort, status: lowOnly ? 'low' : undefined }),
    [debounced, sort, lowOnly],
  )
  useStoreEvent('stock_updated', () => reload({ quiet: true }))
  useStoreEvent('payment_received', () => reload({ quiet: true }))

  return (
    <div className="space-y-3">
      {data && (
        <div className="grid grid-cols-3 gap-2">
          <Card className="!p-3"><div className="text-[11px] text-ink-3">Stock value</div><div className="font-bold tabular text-lg">{inr(data.summary.total_stock_value)}</div></Card>
          <Card className="!p-3"><div className="text-[11px] text-ink-3">Kam stock</div><div className="font-bold tabular text-lg text-stock-red">{data.summary.low_count}</div></Card>
          <Card className="!p-3"><div className="text-[11px] text-ink-3">Expiry paas</div><div className="font-bold tabular text-lg text-orange-700">{data.summary.expiring_count}</div></Card>
        </div>
      )}
      <div className="relative">
        <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-3" />
        <input className={`${inputCls} pl-10`} placeholder="Saaman dhundhein" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <div className="flex gap-2 overflow-x-auto app-scroll -mx-4 px-4">
        {SORTS.map((s) => (
          <button key={s.id} onClick={() => setSort(s.id)} className={`flex-shrink-0 min-h-[44px] px-4 rounded-full text-sm font-semibold border ${sort === s.id ? 'bg-ink text-white border-ink' : 'bg-white border-line text-ink-3'}`}>
            {s.label}
          </button>
        ))}
        <button onClick={() => setLowOnly((v) => !v)} className={`flex-shrink-0 min-h-[44px] px-4 rounded-full text-sm font-semibold border ${lowOnly ? 'bg-stock-red text-white border-stock-red' : 'bg-white border-line text-ink-3'}`}>
          Sirf kam stock
        </button>
      </div>
      {loading && !data && <SkeletonList rows={6} className="h-16" />}
      <ErrorBox error={error} onRetry={reload} />
      {data && data.items.length === 0 && <Empty icon={Boxes} hi="Kuch nahi mila" en="Doosra naam try karein" />}
      <ul className="space-y-2">{data?.items.map((it) => <Row key={it.product_id} item={it} />)}</ul>
    </div>
  )
}
