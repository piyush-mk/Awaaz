import { useState, useRef } from 'react'
import { Camera, Upload, CheckCircle, AlertTriangle, RefreshCw, Package } from 'lucide-react'
import { parsePhoto, restockInventory } from '../api/client'

const STATUS_COLOR = { high: 'text-green-600', medium: 'text-yellow-600', low: 'text-red-500' }

export default function PhotoInventory() {
  const [preview, setPreview]   = useState(null)
  const [imageFile, setImageFile] = useState(null)
  const [items, setItems]       = useState([])
  const [transcript, setTranscript] = useState('')
  const [demoMode, setDemoMode] = useState(false)
  const [phase, setPhase]       = useState('capture')  // capture | review | done
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState('')
  const [restockResult, setRestockResult] = useState(null)
  const fileRef  = useRef()
  const cameraRef = useRef()

  function onFile(file) {
    if (!file) return
    setImageFile(file)
    setPreview(URL.createObjectURL(file))
    setPhase('captured')
    setError('')
    setItems([])
  }

  async function analyse() {
    if (!imageFile) return
    setLoading(true)
    setError('')
    try {
      const res = await parsePhoto(imageFile)
      setItems(res.items || [])
      setTranscript(res.transcript || '')
      setDemoMode(res.demo_mode || false)
      setPhase('review')
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  function updateQty(idx, qty) {
    setItems(prev => prev.map((item, i) => i === idx ? { ...item, quantity: qty } : item))
  }

  async function applyRestock() {
    setLoading(true)
    setError('')
    try {
      const payload = items.map(it => ({ product_id: it.product_id, quantity: it.quantity }))
      const res = await restockInventory(payload)
      setRestockResult(res)
      setPhase('done')
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  function reset() {
    setPreview(null)
    setImageFile(null)
    setItems([])
    setTranscript('')
    setDemoMode(false)
    setPhase('capture')
    setError('')
    setRestockResult(null)
  }

  return (
    <div className="p-4 space-y-4 max-w-[430px] mx-auto">
      <div>
        <h1 className="text-lg font-bold text-gray-900">फोटो से स्टॉक</h1>
        <p className="text-xs text-gray-500">Photo Inventory — shelf scan</p>
      </div>

      {/* Capture area */}
      {(phase === 'capture' || phase === 'captured') && (
        <div className="space-y-3">
          {preview ? (
            <div className="relative rounded-xl overflow-hidden border-2 border-paytm-blue">
              <img src={preview} alt="shelf" className="w-full object-cover max-h-64" />
              {demoMode && (
                <span className="absolute top-2 right-2 bg-yellow-400 text-yellow-900 text-xs font-bold px-2 py-0.5 rounded-full">DEMO</span>
              )}
            </div>
          ) : (
            <div
              className="w-full h-48 rounded-xl border-2 border-dashed border-gray-300 flex flex-col items-center justify-center gap-2 bg-gray-50 cursor-pointer"
              onClick={() => fileRef.current?.click()}
            >
              <Camera size={36} className="text-gray-400" />
              <span className="text-sm text-gray-500">शेल्फ की फोटो लें</span>
              <span className="text-xs text-gray-400">Tap to open camera / gallery</span>
            </div>
          )}

          <div className="flex gap-2">
            <button
              onClick={() => { cameraRef.current?.click() }}
              className="flex-1 flex items-center justify-center gap-2 py-3 bg-paytm-blue text-white rounded-xl font-semibold text-sm"
            >
              <Camera size={18} />
              Camera
            </button>
            <button
              onClick={() => fileRef.current?.click()}
              className="flex-1 flex items-center justify-center gap-2 py-3 border-2 border-paytm-blue text-paytm-blue rounded-xl font-semibold text-sm"
            >
              <Upload size={18} />
              Gallery
            </button>
          </div>

          <input ref={cameraRef} type="file" accept="image/*" capture="environment" className="hidden"
            onChange={e => onFile(e.target.files[0])} />
          <input ref={fileRef} type="file" accept="image/*" className="hidden"
            onChange={e => onFile(e.target.files[0])} />

          {phase === 'captured' && (
            <button
              onClick={analyse}
              disabled={loading}
              className="w-full py-3 bg-green-600 text-white rounded-xl font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-60"
            >
              {loading ? <RefreshCw size={18} className="animate-spin" /> : <Package size={18} />}
              {loading ? 'AI analysing shelf…' : 'Detect Products →'}
            </button>
          )}
        </div>
      )}

      {/* Review detected items */}
      {phase === 'review' && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <p className="font-semibold text-gray-800">{items.length} products detected</p>
              <p className="text-xs text-gray-400 font-mono truncate">{transcript}</p>
            </div>
            {demoMode && (
              <span className="bg-yellow-100 text-yellow-800 text-xs font-bold px-2 py-0.5 rounded-full">DEMO</span>
            )}
          </div>

          {preview && (
            <img src={preview} alt="shelf" className="w-full object-cover max-h-40 rounded-lg border border-gray-200" />
          )}

          <div className="space-y-2">
            {items.map((item, idx) => (
              <div key={item.product_id} className="flex items-center gap-3 bg-gray-50 rounded-xl px-3 py-2.5 border border-gray-200">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-gray-900 truncate">{item.name}</p>
                  <p className="text-xs text-gray-400">{item.name_hi} · ₹{item.price}/{item.unit}</p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => updateQty(idx, Math.max(0, item.quantity - 1))}
                    className="w-7 h-7 rounded-full bg-gray-200 text-gray-700 font-bold text-sm flex items-center justify-center"
                  >−</button>
                  <span className="w-8 text-center font-bold text-gray-900">{item.quantity}</span>
                  <button
                    onClick={() => updateQty(idx, item.quantity + 1)}
                    className="w-7 h-7 rounded-full bg-paytm-blue text-white font-bold text-sm flex items-center justify-center"
                  >+</button>
                </div>
              </div>
            ))}
          </div>

          <div className="flex gap-2 pt-1">
            <button onClick={reset} className="flex-1 py-3 border border-gray-300 text-gray-600 rounded-xl font-semibold text-sm">
              Retake
            </button>
            <button
              onClick={applyRestock}
              disabled={loading || items.length === 0}
              className="flex-1 py-3 bg-paytm-blue text-white rounded-xl font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-60"
            >
              {loading ? <RefreshCw size={16} className="animate-spin" /> : <CheckCircle size={16} />}
              Update Stock
            </button>
          </div>
        </div>
      )}

      {/* Done */}
      {phase === 'done' && restockResult && (
        <div className="space-y-4">
          <div className="bg-green-50 border border-green-200 rounded-xl p-4 text-center">
            <CheckCircle size={32} className="text-green-600 mx-auto mb-2" />
            <p className="font-bold text-green-800 text-lg">Stock Updated!</p>
            <p className="text-xs text-green-600">{restockResult.restocked?.length || items.length} products restocked</p>
          </div>

          {restockResult.low_stock_alerts?.length > 0 && (
            <div className="bg-red-50 border border-red-200 rounded-xl p-3 flex gap-2">
              <AlertTriangle size={18} className="text-red-500 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-xs font-bold text-red-800">Low Stock Alerts</p>
                {restockResult.low_stock_alerts.map(a => (
                  <p key={a.product_id} className="text-xs text-red-700">{a.name}: only {a.quantity} left</p>
                ))}
              </div>
            </div>
          )}

          <button onClick={reset} className="w-full py-3 bg-paytm-blue text-white rounded-xl font-bold text-sm flex items-center justify-center gap-2">
            <Camera size={18} />
            Scan Another Shelf
          </button>
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-3 text-xs text-red-700 flex gap-2">
          <AlertTriangle size={16} className="flex-shrink-0" />
          {error}
        </div>
      )}
    </div>
  )
}
