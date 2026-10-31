import { useEffect, useState } from 'react'
import { ChevronDown, Search, Boxes } from 'lucide-react'
import { Chip, Empty, ErrorBox, Filters, Hero, Rows, SkeletonList, inputCls } from '../ui'
import { VoiceHint } from '../VoiceContext'
import useLoad from '../../../lib/useLoad'
import { useStoreEvent } from '../AppContext'
import { getStock } from '../../../api/client'
import { inr, num, qtyLabel, shortDate } from '../../../lib/format'

const SORTS = [
  { id: 'id', label: 'Sab' },
  { id: 'cover', label: 'Kam din' },
  { id: 'expiry', label: 'Expiry' },
  { id: 'value', label: 'Value' },
]

/** One honest status line: running out first, then expiry, then plain days of stock. */
function statusOf(item) {
  const cover = item.days_of_cover
  if (item.expiry_status === 'expired') return { text: 'Expired', cls: 'text-red-700 font-medium' }
  if (item.status === 'low') return { text: 'Stock kam hai', cls: 'text-red-700 font-medium' }
  if (cover != null && cover < 3) return { text: `${num(cover, 1)} din ka stock`, cls: 'text-red-700 font-medium' }
  if (item.expiry_status === 'soon') return { text: `${item.days_to_expiry} din mein expiry`, cls: 'text-orange-800 font-medium' }
  if (cover != null && cover < 7) return { text: `${num(cover, 1)} din ka stock`, cls: 'text-orange-800 font-medium' }
  return { text: cover != null ? `${num(cover, 0)} din ka stock` : `${inr(item.price)}/${item.unit}`, cls: 'text-ink-3' }
}

function Row({ item }) {
  const [open, setOpen] = useState(false)
  const st = statusOf(item)
  return (
    <li>
      <button onClick={() => setOpen((v) => !v)} aria-expanded={open} className="w-full min-h-[64px] px-4 py-2.5 flex items-center gap-3 text-left active:bg-bg-app">
        <div className="min-w-0 flex-1">
          <div className="font-hindi text-lg font-semibold leading-tight truncate">{item.name_hi || item.name}</div>
          <div className={`text-sm mt-0.5 truncate ${st.cls}`}>{st.text}</div>
        </div>
        <div className="font-semibold tabular flex-shrink-0">{qtyLabel(item.qty, item.unit)}</div>
        <ChevronDown size={18} className={`text-ink-3 flex-shrink-0 ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="px-4 pb-3 text-sm space-y-2">
          <div className="grid grid-cols-3 gap-2 tabular">
            <div><div className="text-xs text-ink-3">Cost</div><b>{item.last_cost_price != null ? inr(item.last_cost_price) : inr(item.cost_price)}</b></div>
            <div><div className="text-xs text-ink-3">Margin</div><b>{item.margin_pct != null ? `${num(item.margin_pct, 1)}%` : '-'}</b></div>
            <div><div className="text-xs text-ink-3">Value</div><b>{inr(item.stock_value)}</b></div>
          </div>
          <div className="text-xs text-ink-3">
            {item.name_hi ? `${item.name}, ` : ''}{inr(item.price)}/{item.unit}, {num(item.velocity_per_day, 1)} {item.unit} roz bikta hai
            {item.supplier_name ? `, ${item.supplier_name}` : ''}
          </div>
          {item.festival_multiplier > 1 && <Chip tone="orange">tyohar ke liye {item.festival_multiplier}x demand</Chip>}
          {item.batches?.length > 0 ? (
            <ul className="space-y-1">
              {item.batches.map((b) => (
                <li key={b.batch_id} className="flex justify-between rounded-lg bg-bg-app px-2.5 py-1.5">
                  <span className="text-xs">{b.batch_no || 'batch'}</span>
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
  useStoreEvent('checkout', () => reload({ quiet: true }))
  useStoreEvent('action_resolved', () => reload({ quiet: true }))
  useStoreEvent('demo_reset', () => reload({ quiet: true }))

  return (
    <div className="space-y-3">
      <VoiceHint />
      {data && (
        <Hero
          value={inr(data.summary.total_stock_value)}
          sub={`Stock ki value, ${data.summary.low_count} item kam, ${data.summary.expiring_count} ki expiry paas`}
        />
      )}
      <div className="relative">
        <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-3" />
        <input className={`${inputCls} pl-10`} placeholder="Saaman dhundhein" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <Filters
        items={[...SORTS, { id: 'low', label: 'Sirf kam stock' }]}
        value={lowOnly ? 'low' : sort}
        onChange={(id) => {
          if (id === 'low') setLowOnly(true)
          else {
            setLowOnly(false)
            setSort(id)
          }
        }}
      />
      {loading && !data && <SkeletonList rows={6} className="h-16" />}
      <ErrorBox error={error} onRetry={reload} />
      {data && data.items.length === 0 && <Empty icon={Boxes} hi="Kuch nahi mila" en="Doosra naam try karein" />}
      {data?.items.length > 0 && <Rows>{data.items.map((it) => <Row key={it.product_id} item={it} />)}</Rows>}
    </div>
  )
}
