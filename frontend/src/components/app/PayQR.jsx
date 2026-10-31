import { useState } from 'react'
import QRCode from 'react-qr-code'
import { ExternalLink, CheckCircle2, Banknote, BookOpen } from 'lucide-react'
import { Btn } from './ui'
import { inr, toPath } from '../../lib/format'
import { simulatePayment } from '../../api/client'
import { useApp } from './AppContext'

/** Exact-amount UPI QR for the pending part of a bill. "Payment aa gaya" settles it (simulated rail). */
export default function PayQR({ checkout, onPaid, onBack }) {
  const { showError } = useApp()
  const [busy, setBusy] = useState(false)
  const done = (checkout.payments || []).filter((p) => p.status === 'success')

  const settle = async () => {
    setBusy(true)
    try {
      onPaid(await simulatePayment(checkout.order_id))
    } catch (e) {
      showError(e)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="bg-white rounded-2xl p-4 text-center">
      <div className="text-sm text-ink-3">Bill {checkout.invoice_number}</div>
      <div className="mt-1 text-[44px] leading-none font-semibold tabular text-ink">{inr(checkout.amount_due)}</div>
      <div className="mt-2 font-hindi text-base text-ink-3">QR scan karke bharein</div>
      <div className="mt-3 inline-block rounded-2xl bg-white p-2">
        <QRCode value={checkout.upi_string} size={208} fgColor="#0E1B33" level="M" />
      </div>

      {done.length > 0 && (
        <div className="mt-3 space-y-1 text-left">
          {done.map((p) => (
            <div key={p.id} className="flex items-center gap-2 rounded-xl bg-bg-app px-3 py-2 text-sm">
              {p.mode === 'khata' ? <BookOpen size={16} /> : <Banknote size={16} />}
              <span className="capitalize">{p.mode} mein likha</span>
              <b className="ml-auto tabular">{inr(p.amount)}</b>
            </div>
          ))}
        </div>
      )}
      {checkout.khata_warning && (
        <div className="mt-3 rounded-xl bg-orange-50 px-3 py-2 text-sm font-medium text-orange-900 text-left">
          {checkout.khata_warning}
        </div>
      )}
      {checkout.spoken_text && <p className="mt-3 font-hindi text-base text-ink">{checkout.spoken_text}</p>}

      <Btn size="lg" variant="green" className="w-full mt-4" busy={busy} icon={CheckCircle2} onClick={settle}>
        Payment aa gaya
      </Btn>
      <div className="mt-2 text-[11px] text-ink-3">Demo: yeh button UPI callback ki nakal karta hai</div>
      <div className="mt-3 flex gap-2">
        <a
          href={toPath(checkout.receipt_url)}
          target="_blank"
          rel="noreferrer"
          className="flex-1 min-h-[44px] inline-flex items-center justify-center gap-1.5 rounded-xl bg-bg-app text-sm font-semibold"
        >
          <ExternalLink size={16} /> Receipt
        </a>
        <button onClick={onBack} className="flex-1 min-h-[44px] rounded-xl bg-bg-app text-sm font-semibold">
          Bina payment naya bill
        </button>
      </div>
    </div>
  )
}
