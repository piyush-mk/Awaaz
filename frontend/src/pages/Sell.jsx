import { useState } from 'react'
import MicButton from '../components/MicButton'
import { ParsedItemCard } from '../components/ItemCard'
import Toast from '../components/Toast'
import QRCode from 'react-qr-code'
import { parseVoice, generateBill, confirmBill } from '../api/client'

// feat/voice-agent branch: wire MicButton → parseVoice → bill preview
// feat/inventory branch: stock deduction after confirmBill + payment simulation UI

export default function Sell() {
  const [items, setItems] = useState([])
  const [transcript, setTranscript] = useState('')
  const [bill, setBill] = useState(null)
  const [step, setStep] = useState('speak') // speak | review | qr | done
  const [toast, setToast] = useState(null)
  const [loading, setLoading] = useState(false)

  const handleAudio = async (blob) => {
    const res = await parseVoice(blob, null)
    setTranscript(res.transcript)
    setItems(res.items)
    setBill(null)
    setStep('review')
  }

  const handleTextSubmit = async (e) => {
    e.preventDefault()
    const res = await parseVoice(null, transcript)
    setItems(res.items)
    setBill(null)
    setStep('review')
  }

  const handleGenerateBill = async () => {
    setLoading(true)
    try {
      const b = await generateBill(items)
      setBill(b)
      setStep('qr')
    } catch (err) {
      setToast({ message: err.message, type: 'error' })
    } finally {
      setLoading(false)
    }
  }

  const handlePaymentDone = async () => {
    setLoading(true)
    try {
      await confirmBill(bill.items, bill.grand_total)
      setStep('done')
      setToast({ message: `₹${bill.grand_total} received via Paytm UPI`, type: 'success' })
    } catch (err) {
      setToast({ message: err.message, type: 'error' })
    } finally {
      setLoading(false)
    }
  }

  const reset = () => {
    setItems([])
    setTranscript('')
    setBill(null)
    setStep('speak')
  }

  return (
    <div className="p-4 space-y-4">
      {step === 'speak' && (
        <div className="card text-center py-8 space-y-4">
          <h2 className="text-xl font-bold text-gray-800">बिल बनाएं</h2>
          <p className="text-sm text-gray-500">ग्राहक का सामान बोलें</p>
          <MicButton onResult={handleAudio} color="orange" label="Bill Banao" />
          <form onSubmit={handleTextSubmit} className="flex gap-2 text-left">
            <input
              value={transcript}
              onChange={(e) => setTranscript(e.target.value)}
              placeholder="या टाइप करें... (e.g. do maggi ek surf excel)"
              className="flex-1 border border-gray-200 rounded-xl px-3 py-2 text-sm"
            />
            <button type="submit" className="btn-orange px-4 py-2 text-sm">भेजें</button>
          </form>
        </div>
      )}

      {step === 'review' && items.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-gray-600 uppercase tracking-wide">सामान की सूची</h3>
          {items.map((item) => (
            <ParsedItemCard key={item.product_id} item={item} />
          ))}
          <button onClick={handleGenerateBill} disabled={loading} className="btn-orange w-full">
            {loading ? 'बिल बन रहा है...' : 'Generate Bill & QR'}
          </button>
          <button onClick={reset} className="btn-outline w-full">फिर से बोलें</button>
        </div>
      )}

      {step === 'qr' && bill && (
        <div className="space-y-3">
          <div className="card space-y-2">
            <h3 className="font-bold text-gray-800">Bill Summary</h3>
            {bill.items.map((i) => (
              <div key={i.product_id} className="flex justify-between text-sm">
                <span>{i.name_hi} × {i.quantity}</span>
                <span>₹{i.total}</span>
              </div>
            ))}
            <div className="border-t pt-2 space-y-1">
              <div className="flex justify-between text-sm text-gray-500">
                <span>Subtotal</span><span>₹{bill.subtotal}</span>
              </div>
              <div className="flex justify-between text-sm text-gray-500">
                <span>GST</span><span>₹{bill.total_gst}</span>
              </div>
              <div className="flex justify-between font-bold text-lg">
                <span>Total</span><span className="text-paytm-blue">₹{bill.grand_total}</span>
              </div>
            </div>
          </div>

          <div className="card flex flex-col items-center gap-3">
            <div className="text-xs text-gray-500 font-medium uppercase">Paytm QR — Scan to Pay</div>
            <div className="p-3 bg-white rounded-xl border-2 border-paytm-blue">
              <QRCode value={bill.upi_string} size={180} />
            </div>
            <button onClick={handlePaymentDone} disabled={loading} className="btn-primary w-full">
              ✓ Payment Received (Simulate)
            </button>
          </div>
        </div>
      )}

      {step === 'done' && (
        <div className="card text-center py-10 space-y-3">
          <div className="text-5xl animate-checkmark">✅</div>
          <div className="text-xl font-bold text-gray-800">Payment Ho Gaya!</div>
          <div className="text-sm text-gray-500">₹{bill?.grand_total} received · Stock updated</div>
          <button onClick={reset} className="btn-primary mx-auto">नया Bill</button>
        </div>
      )}

      {toast && <Toast {...toast} onClose={() => setToast(null)} />}
    </div>
  )
}
