import { useEffect, useState } from 'react'
import { ChevronDown, Boxes } from 'lucide-react'
import { Chip, Empty, ErrorBox, Filters, Hero, Rows, SearchToggle, SkeletonList } from '../ui'
import useLoad from '../../../lib/useLoad'
import { useStoreEvent } from '../AppContext'
import { getStock } from '../../../api/client'
import { inr, num, qtyLabel, shortDate } from '../../../lib/format'

const FILTERS = [
  { id: 'all', label: 'Sab' },
  { id: 'low', label: 'Kam' },
  { id: 'expiry', label: 'Expiry' },
]

/** Only a problem gets a second line. */
function statusOf(item) {
  const cover = item.days_of_cover
  if (item.expiry_status === 'expired') return { text: 'Expired', cls: 'text-red-700' }
  if (item.status === 'low') return { text: 'Kam hai', cls: 'text-red-700' }
  if (cover != null && cover < 1) return { text: 'Aaj khatam', cls: 'text-red-700' }
  if (cover != null && cover < 3) return { text: `${num(cover, 0)} din bacha`, cls: 'text-red-700' }
  if (item.expiry_status === 'soon') return { text: `${item.days_to_expiry} din mein expiry`, cls: 'text-orange-800' }
  if (cover != null && cover < 7) return { text: `${num(cover, 0)} din bacha`, cls: 'text-orange-800' }
  return null
}

function Row({ item }) {
  const [open, setOpen] = useState(false)
  const st = statusOf(item)
  return (
    <li>
      <button onClick={() => setOpen((v) => !v)} aria-expanded={open} className="w-full min-h-[64px] px-4 py-2.5 flex items-center gap-3 text-left active:bg-bg-app">
        <div className="min-w-0 flex-1">
          <div className="font-hindi text-lg font-semibold leading-tight truncate">{item.name_hi || item.name}</div>
          {st && <div className={`text-sm font-medium mt-0.5 truncate ${st.cls}`}>{st.text}</div>}
        </div>
        <div className="font-semibold tabular flex-shrink-0">{qtyLabel(item.qty, item.unit)}</div>
        <ChevronDown size={18} className={`text-ink-3 flex-shrink-0 ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="px-4 pb-3 text-sm space-y-2">
          <div className="grid grid-cols-3 gap-2 tabular">
            <div><div className="text-xs text-ink-3">Daam</div><b>{inr(item.price)}</b></div>
            <div><div className="text-xs text-ink-3">Cost</div><b>{item.last_cost_price != null ? inr(item.last_cost_price) : inr(item.cost_price)}</b></div>
            <div><div className="text-xs text-ink-3">Margin</div><b>{item.margin_pct != null ? `${num(item.margin_pct, 1)}%` : '-'}</b></div>
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
  const [filter, setFilter] = useState('all')
  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 250)
    return () => clearTimeout(t)
  }, [q])

  const { data, loading, error, reload } = useLoad(
    () => getStock({ q: debounced, sort: filter === 'expiry' ? 'expiry' : 'id', status: filter === 'low' ? 'low' : undefined }),
    [debounced, filter],
  )
  const refresh = () => reload({ quiet: true })
  useStoreEvent('stock_updated', refresh)
  useStoreEvent('payment_received', refresh)
  useStoreEvent('checkout', refresh)
  useStoreEvent('action_resolved', refresh)
  useStoreEvent('demo_reset', refresh)

  return (
    <div className="space-y-2">
      {data && <Hero value={inr(data.summary.total_stock_value)} sub={`${data.summary.low_count} kam, ${data.summary.expiring_count} expiry paas`} />}
      <div className="flex items-center gap-2 min-h-[48px]">
        {!q && <div className="flex-1 min-w-0"><Filters items={FILTERS} value={filter} onChange={setFilter} /></div>}
        <SearchToggle value={q} onChange={setQ} placeholder="Saaman dhundhein" />
      </div>
      {loading && !data && <SkeletonList rows={6} className="h-14" />}
      <ErrorBox error={error} onRetry={reload} />
      {data && data.items.length === 0 && <Empty icon={Boxes} hi="Kuch nahi mila" />}
      {data?.items.length > 0 && <Rows>{data.items.map((it) => <Row key={it.product_id} item={it} />)}</Rows>}
    </div>
  )
}
