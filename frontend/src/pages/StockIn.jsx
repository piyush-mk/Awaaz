import { useState } from 'react'
import MicButton from '../components/MicButton'
import { ParsedItemCard } from '../components/ItemCard'
import Toast from '../components/Toast'
import { parseVoice, restockInventory } from '../api/client'

// feat/inventory branch: build out full inventory list + confirmed state view
// feat/voice-agent branch: wire MicButton → parseVoice → show results here

export default function StockIn() {
  const [items, setItems] = useState([])
  const [transcript, setTranscript] = useState('')
  const [toast, setToast] = useState(null)
  const [loading, setLoading] = useState(false)
  const [confirmed, setConfirmed] = useState(false)

  const handleAudio = async (blob) => {
    const res = await parseVoice(blob, null)
    setTranscript(res.transcript)
    setItems(res.items)
    setConfirmed(false)
  }

  const handleTextSubmit = async (e) => {
    e.preventDefault()
    const res = await parseVoice(null, transcript)
    setItems(res.items)
    setConfirmed(false)
  }

  const handleQtyChange = (productId, qty) => {
    setItems((prev) => prev.map((i) => i.product_id === productId ? { ...i, quantity: qty } : i))
  }

  const handleConfirm = async () => {
    setLoading(true)
    try {
      await restockInventory(items)
      setConfirmed(true)
      setToast({ message: 'Stock update ho gaya! ✓', type: 'success' })
      setItems([])
      setTranscript('')
    } catch (err) {
      setToast({ message: err.message, type: 'error' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-4 space-y-4">
      <div className="card text-center py-8 space-y-4">
        <h2 className="text-xl font-bold text-gray-800">स्टॉक इन करें</h2>
        <p className="text-sm text-gray-500">नया सामान आने पर बोलें</p>
        <MicButton onResult={handleAudio} color="blue" label="बोलो — Speak" />
      </div>

      {/* Text fallback */}
      <form onSubmit={handleTextSubmit} className="flex gap-2">
        <input
          value={transcript}
          onChange={(e) => setTranscript(e.target.value)}
          placeholder="या यहाँ टाइप करें... (e.g. das packet maggi)"
          className="flex-1 border border-gray-200 rounded-xl px-3 py-2 text-sm"
        />
        <button type="submit" className="btn-primary px-4 py-2 text-sm">भेजें</button>
      </form>

      {/* Parsed items */}
      {items.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-gray-600 uppercase tracking-wide">पहचाना गया सामान</h3>
          {items.map((item) => (
            <ParsedItemCard key={item.product_id} item={item} onQtyChange={handleQtyChange} />
          ))}
          <button
            onClick={handleConfirm}
            disabled={loading}
            className="btn-primary w-full"
          >
            {loading ? 'अपडेट हो रहा है...' : 'Confirm Stock In ✓'}
          </button>
        </div>
      )}

      {toast && <Toast {...toast} onClose={() => setToast(null)} />}
    </div>
  )
}
