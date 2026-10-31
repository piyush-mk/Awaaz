import { useState } from 'react'
import QRCode from 'react-qr-code'
import { CheckCircle2 } from 'lucide-react'
import { Btn } from './ui'
import { inr } from '../../lib/format'
import { simulatePayment } from '../../api/client'
import { useApp } from './AppContext'
import { tr } from '../../lib/i18n'

/** Exact-amount UPI QR for the pending part of a bill. "Payment aa gaya" settles it (simulated rail). */
export default function PayQR({ checkout, onPaid, onBack }) {
  const { showError } = useApp()
  const [busy, setBusy] = useState(false)

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
      <div className="text-[44px] leading-none font-semibold tabular text-ink">{inr(checkout.amount_due)}</div>
      <div className="mt-4 inline-block">
        <QRCode value={checkout.upi_string} size={224} fgColor="#0E1B33" level="M" />
      </div>
      {checkout.khata_warning && <div className="mt-3 rounded-xl bg-orange-50 px-3 py-2 text-sm font-medium text-orange-900">{checkout.khata_warning}</div>}
      <Btn size="lg" variant="green" className="w-full mt-4" busy={busy} icon={CheckCircle2} onClick={settle}>
        {tr('Payment aa gaya')}
      </Btn>
      <div className="mt-1 text-xs text-ink-3">{tr('demo payment')}</div>
      <button onClick={onBack} className="mt-1 min-h-[44px] w-full text-sm font-semibold text-ink-3">{tr('Radd karein')}</button>
    </div>
  )
}
