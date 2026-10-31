import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowDownLeft, ArrowUpRight, ChevronLeft, ExternalLink, Flag, Check } from 'lucide-react'
import { Btn, ErrorBox, Hero, Rows, SkeletonList } from '../ui'
import { statusOf } from './KhataList'
import EntrySheet from './EntrySheet'
import useLoad from '../../../lib/useLoad'
import { useApp, useStoreEvent } from '../AppContext'
import { confirmKhataEntry, disputeKhataEntry, getKhataCustomer } from '../../../api/client'
import { inr, shortDate, toPath } from '../../../lib/format'

export default function KhataDetail() {
  const { id } = useParams()
  const { showToast, showError } = useApp()
  const { data: c, loading, error, reload } = useLoad(() => getKhataCustomer(id), [id])
  const [sheet, setSheet] = useState(null) // 'credit' | 'payment'
  const [open, setOpen] = useState(null)

  useStoreEvent('khata_disputed', (d) => {
    if (String(d.customer_id) === String(id)) {
      showToast(`${d.customer} ne ek entry galat bataya`, 'warning')
      reload({ quiet: true })
    }
  })

  const refresh = (d) => {
    if (!d?.customer_id || String(d.customer_id) === String(id)) reload({ quiet: true })
  }
  useStoreEvent('khata_updated', refresh)
  useStoreEvent('khata_confirmed', refresh)
  useStoreEvent('postpaid_approved', refresh)
  useStoreEvent('demo_reset', refresh)

  const mark = async (entry, kind) => {
    try {
      if (kind === 'dispute') await disputeKhataEntry(entry.id, { note: 'dukaandaar ne galat mana' })
      else await confirmKhataEntry(entry.id, {})
      setOpen(null)
      reload({ quiet: true })
    } catch (e) {
      showError(e)
    }
  }

  if (loading && !c) return <div className="p-4"><SkeletonList rows={5} /></div>
  if (error) return <div className="p-4"><ErrorBox error={error} onRetry={reload} /></div>
  if (!c) return null

  const disputed = c.entries.filter((e) => e.disputed)
  return (
    <div className="px-4 pb-16 space-y-3">
      <Link to="/app/khata" className="-ml-1 inline-flex items-center gap-1 min-h-[44px] text-sm font-semibold text-ink-3">
        <ChevronLeft size={18} /> Sab customer
      </Link>

      <div>
        <div className="font-hindi text-2xl font-semibold">{c.name}</div>
        <div className="text-sm text-ink-3 mb-3">{c.phone || 'phone nahi hai'}</div>
        <Hero value={inr(c.balance)} sub={c.balance > c.credit_limit ? null : `Limit ${inr(c.credit_limit)}`} />
        <div className={`mt-1 text-[15px] ${statusOf(c).cls}`}>{statusOf(c).text}</div>
        {c.limit_reason && <p className="mt-2 font-hindi text-base text-ink">{c.limit_reason}</p>}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Btn variant="accent" icon={ArrowUpRight} onClick={() => setSheet('credit')}>Udhaar diya</Btn>
        <Btn variant="green" icon={ArrowDownLeft} onClick={() => setSheet('payment')}>Paisa mila</Btn>
      </div>

      {disputed.length > 0 && (
        <div className="rounded-2xl bg-red-50 p-3">
          <div className="flex items-center gap-2 font-hindi text-lg font-bold text-red-800"><Flag size={18} /> Customer ne galat bataya</div>
          <ul className="mt-1 text-sm text-red-900">
            {disputed.map((e) => <li key={e.id}>{shortDate(e.at)}: {inr(Math.abs(e.amount))} {e.note ? `(${e.note})` : ''}</li>)}
          </ul>
        </div>
      )}

      {c.passbook_url && (
        <a href={toPath(c.passbook_url)} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 min-h-[44px] text-sm font-semibold text-paytm-blue-dark">
          <ExternalLink size={16} /> Customer ka passbook dekhein
        </a>
      )}

      <div className="font-hindi text-lg font-semibold">Hisaab</div>
      <Rows>
        {c.entries.map((e) => {
          const credit = e.amount > 0
          const expanded = open === e.id
          return (
            <li key={e.id} className={e.disputed ? 'bg-red-50' : ''}>
              <button onClick={() => setOpen(expanded ? null : e.id)} className="w-full min-h-[60px] px-4 py-2 flex items-center gap-3 text-left">
                <span className={`w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0 ${credit ? 'bg-orange-100 text-orange-800' : 'bg-green-100 text-green-800'}`}>
                  {credit ? <ArrowUpRight size={18} /> : <ArrowDownLeft size={18} />}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="font-semibold truncate">{e.note || (credit ? 'Udhaar' : 'Jama')}</div>
                  <div className="text-xs text-ink-3">
                    {shortDate(e.at)}
                    {e.confirmed_by_customer && <span className="ml-1 text-green-700">customer ne maana</span>}
                    {e.disputed && <span className="ml-1 text-red-700 font-semibold">galat bataya</span>}
                  </div>
                </div>
                <div className="text-right tabular">
                  <div className={`font-bold ${credit ? 'text-orange-800' : 'text-green-700'}`}>{credit ? '+' : '-'}{inr(Math.abs(e.amount))}</div>
                  <div className="text-xs text-ink-3">baaki {inr(e.running_balance)}</div>
                </div>
              </button>
              {expanded && (
                <div className="px-4 pb-3 flex gap-2">
                  <Btn size="sm" variant="ghost" icon={Check} className="flex-1" onClick={() => mark(e, 'confirm')}>Customer ne maana</Btn>
                  <Btn size="sm" variant="danger" icon={Flag} className="flex-1" onClick={() => mark(e, 'dispute')}>Galat hai</Btn>
                </div>
              )}
            </li>
          )
        })}
      </Rows>

      <EntrySheet open={!!sheet} kind={sheet || 'credit'} customer={c} onClose={() => setSheet(null)} onChanged={() => reload({ quiet: true })} />
    </div>
  )
}
