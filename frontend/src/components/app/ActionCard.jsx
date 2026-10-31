import { useState } from 'react'
import ConfirmCard from './ConfirmCard'
import CustomerSheet from './CustomerSheet'
import { confirmAction, cancelAction } from '../../api/client'
import { inr, qtyLabel } from '../../lib/format'
import { useApp } from './AppContext'

const QUESTIONS = {
  checkout: 'Bill banaun?',
  split_payment: 'Is tarah paisa lun?',
  add_udhaar: 'Khate mein likhun?',
  record_khata_payment: 'Khate mein jama karun?',
  restock: 'Stock mein jodun?',
  set_price: 'Daam badal dun?',
}

function Detail({ action }) {
  const p = action.payload || {}
  switch (action.kind) {
    case 'checkout':
      return (
        <div className="flex items-baseline justify-between text-ink-3 text-sm">
          {p.item_count} item <span className="font-semibold text-ink text-lg tabular">{inr(p.total)}</span>
        </div>
      )
    case 'split_payment':
      return (
        <div className="space-y-1">
          {Object.entries(p.parts || {})
            .filter(([, v]) => v > 0)
            .map(([k, v]) => (
              <div key={k} className="flex justify-between text-base">
                <span className="capitalize text-ink-3">{k === 'upi' ? 'Paytm / UPI' : k}</span>
                <span className="font-bold tabular">{inr(v)}</span>
              </div>
            ))}
          <div className="flex justify-between border-t border-line pt-1 font-bold">
            <span>Kul</span>
            <span className="tabular">{inr(p.total)}</span>
          </div>
        </div>
      )
    case 'add_udhaar':
    case 'record_khata_payment':
      return (
        <div className="space-y-1.5">
          <div className="flex items-baseline justify-between">
            <span className="font-hindi text-lg font-bold">{p.customer_name}</span>
            <span className="text-xl font-bold tabular">{inr(p.amount)}</span>
          </div>
          <div className="text-sm text-ink-3 tabular">
            Baaki {inr(Math.max(p.balance_after, 0))} ho jayega
          </div>
        </div>
      )
    case 'restock':
      return (
        <ul className="space-y-1">
          {(p.items || []).map((it) => (
            <li key={it.product_id} className="flex justify-between">
              <span className="font-hindi text-lg font-bold">{it.name_hi || it.name}</span>
              <span className="font-bold tabular">+{qtyLabel(it.quantity, it.unit)}</span>
            </li>
          ))}
        </ul>
      )
    default:
      return p.summary ? <div className="text-ink-3">{p.summary}</div> : null
  }
}

/** One proposed PendingAction with big Haan / Nahi. onResolved(response, action) after confirm or cancel. */
export default function ActionCard({ action, onResolved }) {
  const { showError } = useApp()
  const [busy, setBusy] = useState(false)
  const [pickOpen, setPickOpen] = useState(false)
  const [customer, setCustomer] = useState(null)
  const p = action.payload || {}
  const needsCustomer = action.kind === 'split_payment' && p.needs_customer && !customer

  const resolve = async (kind) => {
    setBusy(true)
    try {
      const body = customer ? { customer_id: customer.id } : undefined
      const res = kind === 'confirm' ? await confirmAction(action.id, body) : await cancelAction(action.id)
      onResolved?.(res, action, kind)
    } catch (e) {
      showError(e)
    } finally {
      setBusy(false)
    }
  }

  const warn =
    action.kind === 'add_udhaar' && p.over_limit
      ? `Limit ${inr(p.credit_limit)} se upar`
      : null

  return (
    <>
      <ConfirmCard
        question={QUESTIONS[action.kind] || p.summary || 'Karun?'}
        source={action.source}
        latency={action.latency_ms}
        demo={action.source === 'fixture'}
        warn={warn}
        busy={busy}
        onNo={() => resolve('cancel')}
        onYes={() => (needsCustomer ? setPickOpen(true) : resolve('confirm'))}
        yesLabel={needsCustomer ? 'Customer chuniye' : 'Haan'}
        tone={action.kind === 'add_udhaar' || action.kind === 'split_payment' ? 'orange' : 'blue'}
      >
        <Detail action={action} />
        {customer && <div className="mt-2 text-sm text-ink-3">Khata: <b className="text-ink">{customer.name}</b></div>}
      </ConfirmCard>
      <CustomerSheet
        open={pickOpen}
        onClose={() => setPickOpen(false)}
        onPick={(c) => {
          setCustomer(c)
          setPickOpen(false)
        }}
        title="Kiske khate mein?"
      />
    </>
  )
}
