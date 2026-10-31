import { useState } from 'react'
import { Send } from 'lucide-react'
import { Sheet, SkeletonList, ErrorBox } from '../ui'
import ConfirmCard from '../ConfirmCard'
import useLoad from '../../../lib/useLoad'
import { previewReminders, sendReminders } from '../../../api/client'
import { useApp } from '../AppContext'
import { inr } from '../../../lib/format'
import { tr } from '../../../lib/i18n'

/** Salary-day reminder preview and send (WhatsApp). */
export default function RemindersSheet({ open, onClose }) {
  const { showToast, showError } = useApp()
  const { data, loading, error, reload } = useLoad(() => (open ? previewReminders({}) : Promise.resolve(null)), [open])
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState(null)

  const send = async () => {
    setBusy(true)
    try {
      const res = await sendReminders({})
      setSent(res)
      showToast(tr('{n} reminder bheje', { n: res.sent.length }))
    } catch (e) {
      showError(e)
    } finally {
      setBusy(false)
    }
  }
  const close = () => {
    setSent(null)
    onClose()
  }

  return (
    <Sheet open={open} onClose={close} title={tr('Reminder')}>
      {loading && <SkeletonList rows={3} />}
      <ErrorBox error={error} onRetry={reload} />
      {data && !sent && (
        <div className="space-y-3">
          <ul className="divide-y divide-line">
            {data.reminders.map((r) => (
              <li key={r.customer_id} className="flex items-center justify-between py-2.5">
                <span className="font-hindi text-lg font-semibold">{r.name}</span>
                <span className="font-semibold tabular">{inr(r.balance)}</span>
              </li>
            ))}
          </ul>
          <ConfirmCard
            question={tr('{n} logon ko bhejun? {amt}', { n: data.count, amt: inr(data.total_due) })}
            busy={busy || data.count === 0}
            onYes={send}
            onNo={close}
            yesLabel={tr('Haan')}
            tone="orange"
          />
        </div>
      )}
      {sent && (
        <div className="space-y-3 text-center">
          <Send size={36} className="mx-auto text-paytm-blue" />
          <div className="font-hindi text-2xl font-bold">{tr('{n} reminder bheje', { n: sent.sent.length })}</div>
        </div>
      )}
    </Sheet>
  )
}
