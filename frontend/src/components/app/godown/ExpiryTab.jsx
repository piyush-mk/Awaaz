import { useState } from 'react'
import { CalendarClock } from 'lucide-react'
import { Chip, Empty, ErrorBox, Filters, Hero, SkeletonList } from '../ui'
import useLoad from '../../../lib/useLoad'
import { getStockExpiry } from '../../../api/client'
import { inr, num, shortDate } from '../../../lib/format'

const WINDOWS = [7, 15, 30]

export default function ExpiryTab() {
  const [days, setDays] = useState(7)
  const { data, loading, error, reload } = useLoad(() => getStockExpiry(days), [days])
  return (
    <div className="space-y-3">
      <Filters items={WINDOWS.map((d) => ({ id: d, label: `${d} din` }))} value={days} onChange={setDays} />
      {data && data.items.length > 0 && (
        <Hero value={inr(data.total_claim)} sub={`Wapas karne ka claim, ${data.count} batch ${days} din mein expire`} />
      )}
      {loading && !data && <SkeletonList rows={4} className="h-24" />}
      <ErrorBox error={error} onRetry={reload} />
      {data && data.items.length === 0 && <Empty icon={CalendarClock} hi="Kuch expire nahi ho raha" en={`Agle ${days} din mein koi batch nahi`} />}
      <ul className="divide-y divide-line">
        {data?.items.map((r) => (
          <li key={r.batch_id} className="py-3">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="font-hindi text-lg font-semibold truncate">{r.name_hi || r.name}</div>
                <div className="text-sm text-ink-3">{r.batch_no}, {num(r.qty)} {r.unit}</div>
              </div>
              <div className="text-right flex-shrink-0">
                <Chip tone={r.expired ? 'red' : r.days_left <= 3 ? 'red' : 'yellow'}>{r.expired ? 'expired' : `${r.days_left} din`}</Chip>
                <div className="text-xs text-ink-3 mt-0.5">{shortDate(r.expiry)}</div>
              </div>
            </div>
            <div className="mt-2 flex items-center justify-between rounded-xl bg-bg-app px-3 py-2">
              <span className="text-sm text-ink flex-1 pr-2">{r.suggested_action}</span>
              <b className="tabular text-lg">{inr(r.claim_amount)}</b>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
