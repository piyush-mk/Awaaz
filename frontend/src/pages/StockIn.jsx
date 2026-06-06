import { useState } from 'react'
import MicButton from '../components/MicButton'
import { ParsedItemCard } from '../components/ItemCard'
import Toast from '../components/Toast'
import { parseVoice, restockInventory, textToSpeech } from '../api/client'
import { speakWithFallback } from '../lib/audio'

// feat/inventory branch: build out full inventory list + confirmed state view
// feat/voice-agent branch: wire MicButton → parseVoice → show results here

export default function StockIn() {
  const [items, setItems] = useState([])
  const [transcript, setTranscript] = useState('')
  const [toast, setToast] = useState(null)
  const [loading, setLoading] = useState(false)
  const [confirmed, setConfirmed] = useState(false)

  const handleAudio = async (blob) => {
    try {
      const res = await parseVoice(blob, null)
      setTranscript(res.transcript)
      setItems(res.items.map((item, index) => ({ ...item, ui_id: item.product_id ?? `custom-${Date.now()}-${index}` })))
      setConfirmed(false)
      setToast(null)
    } catch (err) {
      setToast({ message: err.message, type: 'error' })
    }
  }

  const handleTextSubmit = async (e) => {
    e.preventDefault()
    try {
      const res = await parseVoice(null, transcript)
      setItems(res.items.map((item, index) => ({ ...item, ui_id: item.product_id ?? `custom-${Date.now()}-${index}` })))
      setConfirmed(false)
      setToast(null)
    } catch (err) {
      setToast({ message: err.message, type: 'error' })
    }
  }

  const handleQtyChange = (itemKey, qty) => {
    setItems((prev) => prev.map((i) => (i.ui_id === itemKey ? { ...i, quantity: qty } : i)))
  }

  const handleConfirm = async () => {
    if (items.length === 0) {
      setToast({ message: 'पहले voice से items पहचानें', type: 'warning' })
      return
    }

    setLoading(true)
    try {
      await restockInventory(items)

      const speechText = 'स्टॉक अपडेट हो गया.'
      const tts = await textToSpeech(speechText, 'hi')
      await speakWithFallback(speechText, tts.audio_base64, 'hi')

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
            <ParsedItemCard key={item.ui_id ?? item.product_id} item={item} onQtyChange={handleQtyChange} />
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
