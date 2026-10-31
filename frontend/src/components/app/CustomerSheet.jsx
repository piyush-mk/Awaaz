import { useState } from 'react'
import { Search, UserRound } from 'lucide-react'
import { Sheet, SkeletonList, ErrorBox, Empty, Chip, inputCls } from './ui'
import useLoad from '../../lib/useLoad'
import { listKhataCustomers } from '../../api/client'
import { inr } from '../../lib/format'
import { nameOf } from '../../lib/i18n'
import { tr } from '../../lib/i18n'

/** Pick a customer by name. Used for the counter chip, khata splits and disputes. */
export default function CustomerSheet({ open, onClose, onPick, title = tr('Customer chuniye') }) {
  const [q, setQ] = useState('')
  const { data, loading, error, reload } = useLoad(() => (open ? listKhataCustomers({ sort: 'name' }) : Promise.resolve(null)), [open])
  const rows = (data || []).filter((c) => !q || c.name.toLowerCase().includes(q.toLowerCase()) || (c.name_hi || '').includes(q))

  return (
    <Sheet open={open} onClose={onClose} title={title}>
      <div className="relative mb-3">
        <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-3" />
        <input className={`${inputCls} pl-10`} placeholder={tr('Naam likhein')} value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      {loading && <SkeletonList rows={4} className="h-14" />}
      <ErrorBox error={error} onRetry={reload} />
      {!loading && !error && rows.length === 0 && <Empty icon={UserRound} hi={tr('Koi customer nahi mila')} />}
      <ul className="space-y-2">
        {rows.map((c) => (
          <li key={c.id}>
            <button
              onClick={() => onPick(c)}
              className="w-full min-h-[56px] bg-bg-app rounded-xl px-4 py-2 flex items-center justify-between text-left active:bg-bg-app"
            >
              <span className="font-hindi text-lg font-bold text-ink">{nameOf(c)}</span>
              {c.balance > 0 ? <Chip tone={c.risk === 'high' ? 'red' : 'yellow'}>{tr('baaki {amt}', { amt: inr(c.balance) })}</Chip> : <Chip tone="green">{tr('saaf')}</Chip>}
            </button>
          </li>
        ))}
      </ul>
    </Sheet>
  )
}
