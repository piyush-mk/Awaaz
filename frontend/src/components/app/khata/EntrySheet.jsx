import { useEffect, useState } from 'react'
import { MessageCircle, ShieldCheck } from 'lucide-react'
import { Sheet, Field, inputCls, Btn, Chip } from '../ui'
import ConfirmCard from '../ConfirmCard'
import { addKhataEntry, approvePostpaid, offerPostpaid } from '../../../api/client'
import { useApp } from '../AppContext'
import { inr } from '../../../lib/format'
import { speak } from '../../../lib/audio'

/** Give udhaar (credit) or receive a payment, with confirm card, WhatsApp text and the simulated Postpaid offer. */
export default function EntrySheet({ open, kind, customer, onClose, onChanged }) {
  const { showError } = useApp()
  const [step, setStep] = useState('form') // form | confirm | result
  const [amount, setAmount] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [offer, setOffer] = useState(null)

  useEffect(() => {
    if (open) {
      setStep('form')
      setAmount('')
      setNote('')
      setResult(null)
      setOffer(null)
    }
  }, [open, kind])

  const amt = Number(amount) || 0
  const credit = kind === 'credit'
  const after = credit ? customer.balance + amt : customer.balance - amt
  const overLimit = credit && (after > customer.credit_limit || after > (customer.suggested_limit || Infinity))

  const submit = async () => {
    setBusy(true)
    try {
      const res = await addKhataEntry({ customer_id: customer.id, kind, amount: amt, note: note || undefined })
      setResult(res)
      setStep('result')
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
    <Sheet open={open} onClose={onClose} title={credit ? 'Udhaar diya' : 'Paisa mila'}>
      <div className="text-center mb-3">
        <div className="font-hindi text-xl font-bold">{customer.name}</div>
        <div className="text-sm text-ink-3">Abhi baaki {inr(customer.balance)}</div>
      </div>

      {step === 'form' && (
        <div className="space-y-3">
          <Field label="Kitne rupaye?">
            <input className={`${inputCls} text-3xl font-bold tabular text-center !min-h-[64px]`} inputMode="decimal" autoFocus placeholder="0" value={amount} onChange={(e) => setAmount(e.target.value)} />
          </Field>
          <div className="flex gap-2">
            {[100, 200, 500, 1000].map((q) => (
              <button key={q} onClick={() => setAmount(String(q))} className="flex-1 min-h-[44px] rounded-xl bg-bg-app font-semibold tabular">{q}</button>
            ))}
          </div>
          <Field label="Note (optional)">
            <input className={inputCls} value={note} onChange={(e) => setNote(e.target.value)} placeholder={credit ? 'ration, dudh...' : 'cash diya'} />
          </Field>
          <Btn size="lg" className="w-full" disabled={amt <= 0} onClick={() => setStep('confirm')}>Aage</Btn>
        </div>
      )}

      {step === 'confirm' && (
        <ConfirmCard
          question={credit ? `${customer.name} ke khate mein ${inr(amt)} likhun?` : `${customer.name} se ${inr(amt)} jama karun?`}
          warn={
            overLimit
              ? `Baaki ${inr(after)} ho jayega. Limit ${inr(customer.credit_limit)}, suggested ${inr(customer.suggested_limit)}. ${customer.limit_reason || ''}`
              : null
          }
          busy={busy}
          onYes={submit}
          onNo={() => setStep('form')}
          tone={credit ? 'orange' : 'blue'}
        >
          <div className="tabular text-ink-3">Baaki {inr(customer.balance)} se <b className="text-ink text-lg">{inr(Math.max(after, 0))}</b> ho jayega</div>
          <div className="mt-1 text-xs text-ink-3">Customer ko WhatsApp jayega</div>
        </ConfirmCard>
      )}

      {step === 'result' && result && (
        <div className="space-y-3">
          <div className="rounded-2xl bg-bg-app p-4 text-center">
            <div className="font-hindi text-xl font-bold">{credit ? 'Khate mein likh diya' : 'Jama ho gaya'}</div>
            <div className="text-ink-3 tabular">Baaki {inr(result.balance_before)} se <b className="text-ink">{inr(result.balance_after)}</b></div>
          </div>
          {result.whatsapp && (
            <div className="rounded-2xl bg-[#DCF8C6] p-3">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-green-900 mb-1">
                <MessageCircle size={14} /> WhatsApp {result.whatsapp.status} {result.whatsapp.channel === 'sim' ? '(simulator)' : ''}
              </div>
              <p className="text-sm text-ink">{result.whatsapp.text}</p>
            </div>
          )}
          {result.warning?.over_limit && (
            <div className="rounded-2xl bg-orange-50 p-3">
              <div className="font-hindi font-bold text-orange-900">{result.warning.message_hi}</div>
              {result.warning.postpaid_available && !offer && (
                <Btn variant="accent" className="w-full mt-3" busy={busy} onClick={makeOffer}>Paytm Postpaid offer bhejein</Btn>
              )}
            </div>
          )}
          {offer && (
            <div className="rounded-2xl bg-white border-2 border-paytm-blue p-3 space-y-2">
              <div className="flex items-center gap-2">
                <ShieldCheck size={18} className="text-paytm-blue" />
                <b>Paytm Postpaid</b>
                <Chip tone="orange">simulated</Chip>
              </div>
              <p className="font-hindi text-base">{offer.message_hi}</p>
              {offer.status === 'offered' ? (
                <Btn className="w-full" busy={busy} onClick={approve}>Customer ki taraf se approve (simulated)</Btn>
              ) : (
                <div className="rounded-xl bg-green-50 px-3 py-2 text-green-900 font-semibold">
                  Approve ho gaya. Dukaan ko {inr(offer.amount)} abhi mil gaye (simulated).
                </div>
              )}
            </div>
          )}
          <Btn variant="navy" className="w-full" onClick={onClose}>Theek hai</Btn>
        </div>
      )}
    </Sheet>
  )
}
