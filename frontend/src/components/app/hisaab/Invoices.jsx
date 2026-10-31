import { ExternalLink, Receipt } from 'lucide-react'
import { Chip, Empty, ErrorBox, Rows, SkeletonList } from '../ui'
import useLoad from '../../../lib/useLoad'
import { useStoreEvent } from '../AppContext'
import { listInvoices } from '../../../api/client'
import { inr, shortTime, shortDate, toPath } from '../../../lib/format'

export default function Invoices() {
  const { data, loading, error, reload } = useLoad(() => listInvoices({ limit: 20 }), [])
  useStoreEvent('payment_received', () => reload({ quiet: true }))
  useStoreEvent('checkout', () => reload({ quiet: true }))
  useStoreEvent('demo_reset', () => reload({ quiet: true }))

  if (loading && !data) return <SkeletonList rows={4} className="h-16" />
  if (error) return <ErrorBox error={error} onRetry={reload} />
  if (!data?.length) return <Empty icon={Receipt} hi="Abhi koi bill nahi" />

  const today = new Date().toDateString()
  return (
    <Rows>
      {data.map((inv) => {
        const d = new Date(inv.created_at)
        const when = d.toDateString() === today ? shortTime(inv.created_at) : `${shortDate(inv.created_at)} ${shortTime(inv.created_at)}`
        return (
          <li key={inv.id}>
            <a
              href={toPath(inv.public_url)}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-3 px-4 py-3 min-h-[64px] active:bg-bg-app"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm text-ink-3 truncate">{inv.number}</span>
                  {inv.status !== 'paid' && <Chip tone="yellow">{inv.status}</Chip>}
                  {inv.doc_type === 'bill_of_supply' && <Chip>supply</Chip>}
                </div>
                <div className="font-hindi text-base font-semibold truncate">{inv.customer_name || 'Walk-in'}</div>
                <div className="text-xs text-ink-3 truncate">{inv.payment_summary || '-'}, {when}</div>
              </div>
              <div className="text-right">
                <div className="text-lg font-semibold tabular">{inr(inv.total)}</div>
                <ExternalLink size={14} className="inline text-ink-3" />
              </div>
            </a>
          </li>
        )
      })}
    </Rows>
  )
}
