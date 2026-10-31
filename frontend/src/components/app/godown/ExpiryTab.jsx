import { useState } from 'react'
import { CalendarClock } from 'lucide-react'
import { Empty, ErrorBox, Filters, Hero, Rows, SkeletonList } from '../ui'
import useLoad from '../../../lib/useLoad'
import { getStockExpiry } from '../../../api/client'
import { inr, num } from '../../../lib/format'

const WINDOWS = [7, 15, 30]

export default function ExpiryTab() {
  const [days, setDays] = useState(7)
  const { data, loading, error, reload } = useLoad(() => getStockExpiry(days), [days])
  return (
    <div className="space-y-2">
      {data && data.items.length > 0 && <Hero value={inr(data.total_claim)} sub={`Wapas karne ka claim, ${data.count} batch`} />}
      <Filters items={WINDOWS.map((d) => ({ id: d, label: `${d} din` }))} value={days} onChange={setDays} />
      {loading && !data && <SkeletonList rows={4} className="h-14" />}
      <ErrorBox error={error} onRetry={reload} />
      {data && data.items.length === 0 && <Empty icon={CalendarClock} hi="Kuch expire nahi ho raha" />}
      {data?.items.length > 0 && (
        <Rows>
          {data.items.map((r) => (
            <li key={r.batch_id} className="min-h-[64px] px-4 py-2.5 flex items-center gap-3">
              <div className="min-w-0 flex-1">
                <div className="font-hindi text-lg font-semibold leading-tight truncate">{r.name_hi || r.name}</div>
                <div className={`text-sm font-medium mt-0.5 ${r.expired || r.days_left <= 3 ? 'text-red-700' : 'text-orange-800'}`}>
                  {r.expired ? 'Expired' : `${r.days_left} din`}, {num(r.qty)} {r.unit}
                </div>
              </div>
              <div className="text-lg font-semibold tabular">{inr(r.claim_amount)}</div>
            </li>
          ))}
        </Rows>
      )}
    </div>
  )
}
