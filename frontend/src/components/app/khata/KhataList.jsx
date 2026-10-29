import { useState } from 'react'
import { Link } from 'react-router-dom'
import { BellRing, ChevronRight, ImagePlus, Search, Users } from 'lucide-react'
import { Btn, Card, Chip, Empty, ErrorBox, SectionTitle, SkeletonList, inputCls } from '../ui'
import PhotoButton from '../PhotoButton'
import ImportSheet from './ImportSheet'
import RemindersSheet from './RemindersSheet'
import useLoad from '../../../lib/useLoad'
import { useApp, useStoreEvent } from '../AppContext'
import { importKhataPhoto, listKhataCustomers } from '../../../api/client'
import { inr } from '../../../lib/format'

const RISK = { high: 'red', medium: 'yellow', low: 'green' }
const SORTS = [
  { id: 'balance', label: 'Zyada baaki' },
  { id: 'risk', label: 'Risk' },
  { id: 'recent', label: 'Haal ka' },
  { id: 'name', label: 'Naam' },
]

export default function KhataList() {
  const { showToast, showError } = useApp()
  const [sort, setSort] = useState('balance')
  const [q, setQ] = useState('')
  const [importing, setImporting] = useState(false)
  const [proposal, setProposal] = useState(null)
  const [remindOpen, setRemindOpen] = useState(false)
  const { data, loading, error, reload } = useLoad(() => listKhataCustomers({ sort }), [sort])

  useStoreEvent('khata_disputed', (d) => {
    showToast(`${d.customer} ne ek entry galat bataya`, 'warning')
    reload({ quiet: true })
  })

  const rows = (data || []).filter((c) => !q || c.name.toLowerCase().includes(q.toLowerCase()) || (c.name_hi || '').includes(q))
  const total = (data || []).reduce((s, c) => s + Math.max(c.balance, 0), 0)
  const owing = (data || []).filter((c) => c.balance > 0).length

  const importPhoto = async (files) => {
    setImporting(true)
    try {
      setProposal(await importKhataPhoto(files[0]))
    } catch (e) {
      showError(e)
    } finally {
      setImporting(false)
    }
  }

  return (
    <div className="px-4 pt-3 pb-6 space-y-3">
      <SectionTitle hi="खाता" en="Khata: kisne kitna dena hai" />

      <Card className="!bg-ink text-white border-ink">
        <div className="text-xs text-white/60">Kul baaki</div>
        <div className="text-4xl font-bold tabular">{inr(total)}</div>
        <div className="text-sm text-white/70">{owing} customer ke paas</div>
      </Card>

      <div className="grid grid-cols-2 gap-3">
        <PhotoButton variant="outline" icon={ImagePlus} label="Notebook photo" busy={importing} onFiles={importPhoto} />
        <Btn variant="ghost" icon={BellRing} onClick={() => setRemindOpen(true)}>Reminder bhejo</Btn>
      </div>

      <div className="relative">
        <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-3" />
        <input className={`${inputCls} pl-10`} placeholder="Naam dhundhein" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <div className="flex gap-2 overflow-x-auto app-scroll -mx-4 px-4">
        {SORTS.map((s) => (
          <button key={s.id} onClick={() => setSort(s.id)} className={`flex-shrink-0 min-h-[44px] px-4 rounded-full text-sm font-semibold border ${sort === s.id ? 'bg-ink text-white border-ink' : 'bg-white border-line text-ink-3'}`}>
            {s.label}
          </button>
        ))}
      </div>

      {loading && !data && <SkeletonList rows={5} className="h-20" />}
      <ErrorBox error={error} onRetry={reload} />
      {data && rows.length === 0 && <Empty icon={Users} hi="Koi customer nahi" en="Notebook ki photo se jodein" />}
      <ul className="space-y-2">
        {rows.map((c) => (
          <li key={c.id}>
            <Link to={`/app/khata/${c.id}`} className={`block rounded-2xl border bg-white p-3 active:bg-bg-app ${c.disputed_entries ? 'border-stock-red' : 'border-line'}`}>
              <div className="flex items-center gap-3">
                <div className="min-w-0 flex-1">
                  <div className="font-hindi text-xl font-bold leading-tight truncate">{c.name}</div>
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    <Chip tone={RISK[c.risk] || 'gray'}>risk {c.risk}</Chip>
                    {c.late_payments > 0 && <Chip tone="red">{c.late_payments} baar late</Chip>}
                    {c.disputed_entries > 0 && <Chip tone="red">galat bataya</Chip>}
                    {c.over_limit && <Chip tone="orange">limit paar</Chip>}
                  </div>
                </div>
                <div className="text-right">
                  <div className={`text-xl font-bold tabular ${c.balance > 0 ? 'text-ink' : 'text-green-700'}`}>{c.balance > 0 ? inr(c.balance) : 'saaf'}</div>
                  <div className="text-[11px] text-ink-3 tabular">limit {inr(c.credit_limit)}</div>
                </div>
                <ChevronRight size={18} className="text-ink-3 flex-shrink-0" />
              </div>
              {c.balance > 0 && c.risk !== 'low' && c.limit_reason && <p className="mt-2 text-xs text-ink-3 leading-snug">{c.limit_reason}</p>}
            </Link>
          </li>
        ))}
      </ul>

      <ImportSheet
        proposal={proposal}
        onClose={() => setProposal(null)}
        onDone={(res) => {
          setProposal(null)
          showToast(`${res.total_imported ? inr(res.total_imported) : ''} khate mein jud gaye`)
          reload({ quiet: true })
        }}
      />
      <RemindersSheet open={remindOpen} onClose={() => setRemindOpen(false)} />
    </div>
  )
}
