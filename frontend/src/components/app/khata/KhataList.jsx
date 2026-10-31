import { useState } from 'react'
import { Link } from 'react-router-dom'
import { BellRing, Camera, ChevronRight, Users } from 'lucide-react'
import { Empty, ErrorBox, Filters, Hero, Rows, SearchToggle, Skeleton, SkeletonList } from '../ui'
import PhotoButton from '../PhotoButton'
import ImportSheet from './ImportSheet'
import RemindersSheet from './RemindersSheet'
import useLoad from '../../../lib/useLoad'
import { useApp, useStoreEvent } from '../AppContext'
import { importKhataPhoto, listKhataCustomers } from '../../../api/client'
import { inr } from '../../../lib/format'
import { nameOf } from '../../../lib/i18n'
import { tr } from '../../../lib/i18n'

const SORTS = [
  { id: 'balance', label: tr('Zyada baaki') },
  { id: 'risk', label: tr('Late') },
  { id: 'recent', label: tr('Naya') },
]

/** Only a problem gets a second line. */
export function statusOf(c) {
  if (c.disputed_entries > 0) return { text: tr('Entry galat bataya'), cls: 'text-red-700' }
  if (c.balance > c.credit_limit) return { text: tr('Limit {amt} se upar', { amt: inr(c.credit_limit) }), cls: 'text-red-700' }
  if (c.late_payments > 0) return { text: tr('{n} baar late', { n: c.late_payments }), cls: 'text-orange-800' }
  return null
}

export default function KhataList() {
  const { showToast, showError } = useApp()
  const [sort, setSort] = useState('balance')
  const [q, setQ] = useState('')
  const [importing, setImporting] = useState(false)
  const [proposal, setProposal] = useState(null)
  const [remindOpen, setRemindOpen] = useState(false)
  const { data, loading, error, reload } = useLoad(() => listKhataCustomers({ sort }), [sort])

  useStoreEvent('khata_disputed', (d) => {
    showToast(tr('{name} ne ek entry galat bataya', { name: d.customer }), 'warning')
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
    <div className="px-4 pt-1 pb-16 space-y-2">
      <div className="flex items-start justify-between gap-2">
        {data ? <Hero value={inr(total)} sub={tr('{n} customer', { n: owing })} /> : <Skeleton className="h-16 w-40" />}
        <div className="flex gap-2 flex-shrink-0">
          <PhotoButton compact variant="outline" icon={Camera} label={tr('Notebook')} busy={importing} onFiles={importPhoto} className="!bg-bg-app" />
          <button onClick={() => setRemindOpen(true)} aria-label={tr('Reminder')} className="w-12 h-12 rounded-xl bg-bg-app flex items-center justify-center"><BellRing size={20} /></button>
        </div>
      </div>

      <div className="flex items-center gap-2 min-h-[48px]">
        {!q && <div className="flex-1 min-w-0"><Filters items={SORTS} value={sort} onChange={setSort} /></div>}
        <SearchToggle value={q} onChange={setQ} placeholder={tr('Naam dhundhein')} />
      </div>

      {loading && !data && <SkeletonList rows={5} className="h-14" />}
      <ErrorBox error={error} onRetry={reload} />
      {data && rows.length === 0 && <Empty icon={Users} hi={tr('Koi customer nahi')} />}
      {rows.length > 0 && (
        <Rows>
          {rows.map((c) => {
            const st = statusOf(c)
            return (
              <li key={c.id}>
                <Link to={`/app/khata/${c.id}`} className="min-h-[60px] px-4 py-2 flex items-center gap-3 active:bg-bg-app">
                  <div className="min-w-0 flex-1">
                    <div className="font-hindi text-lg font-semibold leading-tight truncate">{nameOf(c)}</div>
                    {st && <div className={`text-sm font-medium mt-0.5 truncate ${st.cls}`}>{st.text}</div>}
                  </div>
                  <div className={`text-lg font-semibold tabular ${c.balance > 0 ? 'text-ink' : 'text-green-700'}`}>{c.balance > 0 ? inr(c.balance) : tr('saaf')}</div>
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
          showToast(tr('{amt} khate mein jud gaye', { amt: res.total_imported ? inr(res.total_imported) : '' }))
          reload({ quiet: true })
        }}
      />
      <RemindersSheet open={remindOpen} onClose={() => setRemindOpen(false)} />
    </div>
  )
}
