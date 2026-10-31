import { useEffect, useState } from 'react'
import { Check, MessageCircle, ShieldCheck } from 'lucide-react'
import { Sheet, inputCls, Btn, Chip } from '../ui'
import { addKhataEntry, approvePostpaid, offerPostpaid } from '../../../api/client'
import { useApp } from '../AppContext'
import { inr } from '../../../lib/format'
import { nameOf } from '../../../lib/i18n'
import { speak } from '../../../lib/audio'
import { tr } from '../../../lib/i18n'

/** Give udhaar or receive a payment. The button names the exact amount, so it is its own confirmation. */
export default function EntrySheet({ open, kind, customer, onClose, onChanged }) {
  const { showError } = useApp()
  const [amount, setAmount] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [offer, setOffer] = useState(null)

  useEffect(() => {
    if (open) {
      setAmount('')
      setResult(null)
      setOffer(null)
    }
  }, [open, kind])

  const amt = Number(amount) || 0
  const credit = kind === 'credit'
  const after = credit ? customer.balance + amt : customer.balance - amt
  const overLimit = credit && amt > 0 && after > customer.credit_limit

  const submit = async () => {
    setBusy(true)
    try {
      const res = await addKhataEntry({ customer_id: customer.id, kind, amount: amt })
      setResult(res)
      onChanged?.()
      if (res.warning?.over_limit) speak({ spoken_text: res.warning.message_hi })
    } catch (e) {
      showError(e)
    } finally {
      setBusy(false)
    }
  }

  const makeOffer = async () => {
    setBusy(true)
    try {
      setOffer(await offerPostpaid({ customer_id: customer.id, amount: amt }))
    } catch (e) {
      showError(e)
    } finally {
      setBusy(false)
    }
  }
  const approve = async () => {
    setBusy(true)
    try {
      setOffer(await approvePostpaid(offer.offer_id))
      onChanged?.()
    } catch (e) {
      showError(e)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Sheet open={open} onClose={onClose} title={nameOf(customer)}>
      {!result && (
        <div className="space-y-3">
          <input className={`${inputCls} text-4xl font-semibold tabular text-center !min-h-[72px]`} aria-label={tr('Kitne rupaye')} inputMode="decimal" autoFocus placeholder="₹0" value={amount} onChange={(e) => setAmount(e.target.value)} />
          <div className="flex gap-2">
            {[100, 200, 500, 1000].map((q) => (
              <button key={q} onClick={() => setAmount(String(q))} className="flex-1 min-h-[44px] rounded-xl bg-bg-app font-semibold tabular">{q}</button>
            ))}
          </div>
          {overLimit && <div className="rounded-xl bg-orange-50 px-3 py-2 text-sm font-medium text-orange-900">{tr('Limit {amt} se upar: baaki {after}', { amt: inr(customer.credit_limit), after: inr(after) })}</div>}
          <Btn size="lg" variant="navy" className="w-full" busy={busy} disabled={amt <= 0} onClick={submit}>
            {credit ? tr('Udhaar likho') : tr('Jama karo')}{amt > 0 ? ` ${inr(amt)}` : ''}
          </Btn>
        </div>
      )}

      {result && (
        <div className="space-y-3">
          <div className="text-center">
            <div className="mx-auto w-14 h-14 rounded-full bg-green-700 flex items-center justify-center" role="img" aria-label={credit ? tr('Khate mein likh diya') : tr('Jama ho gaya')}><Check size={30} className="text-white" strokeWidth={3} /></div>
            <div className="mt-2 text-[34px] leading-none font-semibold tabular">{inr(result.balance_after)}</div>
            {result.whatsapp && <div className="mt-2 inline-flex items-center gap-1.5 text-sm text-green-800"><MessageCircle size={14} /> {tr('WhatsApp bheja')}</div>}
          </div>
          {result.warning?.postpaid_available && !offer && (
            <Btn variant="accent" className="w-full" busy={busy} onClick={makeOffer}>{tr('Paytm Postpaid offer')}</Btn>
          )}
          {offer && (
            <div className="rounded-2xl bg-bg-app p-3 space-y-2">
              <div className="flex items-center gap-2">
                <ShieldCheck size={18} className="text-paytm-blue-dark" />
                <b className="font-semibold">Paytm Postpaid</b>
                <Chip tone="orange">{tr('simulated')}</Chip>
              </div>
              {offer.status === 'offered' ? (
                <Btn className="w-full" busy={busy} onClick={approve}>{tr('Customer approve (simulated)')}</Btn>
              ) : (
                <div className="font-semibold text-green-800">{tr('Approve ho gaya: {amt} mil gaye', { amt: inr(offer.amount) })}</div>
              )}
            </div>
          )}
          <Btn variant="navy" className="w-full" onClick={onClose}>{tr('Theek hai')}</Btn>
        </div>
      )}
    </Sheet>
  )
}
