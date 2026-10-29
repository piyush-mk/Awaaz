import { useState } from 'react'
import { Send } from 'lucide-react'
import { Sheet, Chip, SkeletonList, ErrorBox } from '../ui'
import ConfirmCard from '../ConfirmCard'
import useLoad from '../../../lib/useLoad'
import { previewReminders, sendReminders } from '../../../api/client'
import { useApp } from '../AppContext'
import { inr } from '../../../lib/format'

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
      showToast(`${res.sent.length} reminder bhej diye`)
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
    <Sheet open={open} onClose={close} title="Salary-day reminder">
      {loading && <SkeletonList rows={3} />}
      <ErrorBox error={error} onRetry={reload} />
      {data && !sent && (
        <div className="space-y-3">
          <div className={`rounded-xl px-3 py-2 text-sm font-medium ${data.in_salary_window ? 'bg-green-50 text-green-900' : 'bg-orange-50 text-orange-900'}`}>
            {data.window_note}
          </div>
          <div className="flex items-baseline justify-between px-1">
            <span className="text-ink-3">{data.count} customer</span>
            <span className="text-2xl font-bold tabular">{inr(data.total_due)}</span>
          </div>
          <ul className="space-y-2">
            {data.reminders.map((r) => (
              <li key={r.customer_id} className="bg-white rounded-xl border border-line p-3">
                <div className="flex items-center justify-between">
                  <span className="font-hindi text-lg font-bold">{r.name}</span>
                  <span className="font-bold tabular">{inr(r.balance)}</span>
                </div>
                <p className="mt-1 text-xs text-ink-3 whitespace-pre-line break-words line-clamp-3">{r.text}</p>
                {!r.has_phone && <Chip tone="yellow" className="mt-1">phone number nahi hai</Chip>}
              </li>
            ))}
          </ul>
          <ConfirmCard
            question={`${data.count} logon ko WhatsApp bhejun?`}
            busy={busy || data.count === 0}
            onYes={send}
            onNo={close}
            yesLabel="Haan, bhejo"
            tone="orange"
          />
        </div>
      )}
      {sent && (
        <div className="space-y-3 text-center">
          <Send size={36} className="mx-auto text-paytm-blue" />
          <div className="font-hindi text-2xl font-bold">{sent.sent.length} reminder bheje</div>
          <div className="text-sm text-ink-3">{sent.sent.filter((s) => !s.has_phone).length} ke paas phone number nahi tha (outbox mein note hua)</div>
        </div>
      )}
    </Sheet>
  )
}
