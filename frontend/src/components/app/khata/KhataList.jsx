import { useState } from 'react'
import { Link } from 'react-router-dom'
import { BellRing, ChevronRight, ImagePlus, Search, Users } from 'lucide-react'
import { Btn, Empty, ErrorBox, Filters, Hero, Rows, Skeleton, SkeletonList, inputCls } from '../ui'
import { VoiceHint } from '../VoiceContext'
import PhotoButton from '../PhotoButton'
import ImportSheet from './ImportSheet'
import RemindersSheet from './RemindersSheet'
import useLoad from '../../../lib/useLoad'
import { useApp, useStoreEvent } from '../AppContext'
import { importKhataPhoto, listKhataCustomers } from '../../../api/client'
import { inr } from '../../../lib/format'

/** One status per person: what the merchant should notice first. */
export function statusOf(c) {
  if (c.disputed_entries > 0) return { text: 'Customer ne entry galat batayi', cls: 'text-red-700 font-medium' }
  if (c.balance > c.credit_limit) return { text: `Limit ${inr(c.credit_limit)} se upar`, cls: 'text-red-700 font-medium' }
  if (c.late_payments > 0) return { text: `${c.late_payments} baar late`, cls: 'text-orange-800 font-medium' }
  if (c.balance <= 0) return { text: 'Hisaab saaf', cls: 'text-ink-3' }
  return { text: 'Time par', cls: 'text-ink-3' }
}

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
  const refresh = () => reload({ quiet: true })
  useStoreEvent('khata_updated', refresh)
  useStoreEvent('khata_confirmed', refresh)
  useStoreEvent('khata_imported', refresh)
  useStoreEvent('postpaid_approved', refresh)
  useStoreEvent('payment_received', refresh)
  useStoreEvent('checkout', refresh)
  useStoreEvent('demo_reset', refresh)

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
    <div className="px-4 pt-1 pb-16 space-y-3">
      {data ? <Hero value={inr(total)} sub={`${owing} customer par baaki`} /> : <Skeleton className="h-16 w-40" />}
      <VoiceHint />

      <div className="grid grid-cols-2 gap-2">
        <PhotoButton variant="outline" icon={ImagePlus} label="Notebook" busy={importing} onFiles={importPhoto} className="!border-0 !bg-bg-app" />
        <Btn variant="ghost" icon={BellRing} onClick={() => setRemindOpen(true)}>Reminder</Btn>
      </div>

      <div className="relative">
        <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-3" />
        <input className={`${inputCls} pl-10`} placeholder="Naam dhundhein" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <Filters items={SORTS} value={sort} onChange={setSort} />

      {loading && !data && <SkeletonList rows={5} className="h-16" />}
      <ErrorBox error={error} onRetry={reload} />
      {data && rows.length === 0 && <Empty icon={Users} hi="Koi customer nahi" en="Notebook ki photo se jodein" />}
      {rows.length > 0 && (
        <Rows>
          {rows.map((c) => {
            const st = statusOf(c)
            return (
              <li key={c.id}>
                <Link to={`/app/khata/${c.id}`} className="min-h-[64px] px-4 py-2.5 flex items-center gap-3 active:bg-bg-app">
                  <div className="min-w-0 flex-1">
                    <div className="font-hindi text-lg font-semibold leading-tight truncate">{c.name}</div>
                    <div className={`text-sm mt-0.5 truncate ${st.cls}`}>{st.text}</div>
                  </div>
                  <div className={`text-lg font-semibold tabular ${c.balance > 0 ? 'text-ink' : 'text-green-700'}`}>{c.balance > 0 ? inr(c.balance) : 'saaf'}</div>
                  <ChevronRight size={18} className="text-ink-3 flex-shrink-0" />
                </Link>
              </li>
            )
          })}
        </Rows>
      )}

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
