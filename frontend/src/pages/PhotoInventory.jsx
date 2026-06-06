import { useState, useRef } from 'react'
import { Camera, Upload, CheckCircle, AlertTriangle, RefreshCw, Package } from 'lucide-react'
import { parsePhoto, restockInventory, addProduct } from '../api/client'

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
  const [addedItems, setAddedItems] = useState(new Set())
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
      const catalogItems = items.filter(it => it.product_id > 0)
      const res = await restockInventory(catalogItems)
      setRestockResult(res)
      setPhase('done')
    } catch (e) {
      setError(typeof e.message === 'string' ? e.message : 'Restock failed')
    } finally {
      setLoading(false)
    }
  }

  async function handleAddProduct(item, idx) {
    try {
      await addProduct(item.name, item.quantity)
      setAddedItems(prev => new Set([...prev, idx]))
    } catch (e) {
      setError(e.message)
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
    setAddedItems(new Set())
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
              <p className="font-semibold text-gray-800">
                {items.filter(i => i.product_id > 0).length} in catalog
                {items.filter(i => i.product_id === 0).length > 0 && ` · ${items.filter(i => i.product_id === 0).length} other`}
              </p>
              <p className="text-xs text-gray-400 truncate">{transcript}</p>
            </div>
            {demoMode && (
              <span className="bg-yellow-100 text-yellow-800 text-xs font-bold px-2 py-0.5 rounded-full">DEMO</span>
            )}
          </div>

          {preview && (
            <img src={preview} alt="shelf" className="w-full object-cover max-h-40 rounded-lg border border-gray-200" />
          )}

          <div className="space-y-2">
            {items.map((item, idx) => {
              const inCatalog = item.product_id > 0
              return (
                <div key={idx} className={`flex items-center gap-3 rounded-xl px-3 py-2.5 border ${inCatalog ? 'bg-gray-50 border-gray-200' : 'bg-yellow-50 border-yellow-200'}`}>
                  <div className="flex-1 min-w-0">
                    <p className={`text-sm font-semibold truncate ${inCatalog ? 'text-gray-900' : 'text-yellow-800'}`}>{item.name}</p>
                    <p className="text-xs text-gray-400">
                      {inCatalog ? `${item.name_hi} · ₹${item.price}/${item.unit}` : 'Not in catalog — detected only'}
                    </p>
                  </div>
                  {inCatalog ? (
                    <div className="flex items-center gap-2">
                      <button onClick={() => updateQty(idx, Math.max(0, item.quantity - 1))}
                        className="w-7 h-7 rounded-full bg-gray-200 text-gray-700 font-bold text-sm flex items-center justify-center">−</button>
                      <span className="w-8 text-center font-bold text-gray-900">{item.quantity}</span>
                      <button onClick={() => updateQty(idx, item.quantity + 1)}
                        className="w-7 h-7 rounded-full bg-paytm-blue text-white font-bold text-sm flex items-center justify-center">+</button>
                    </div>
                  ) : (
                    <span className="text-xs text-yellow-700 font-semibold">×{item.quantity}</span>
                  )}
                </div>
              )
            })}
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
        <div className="space-y-3">
          <div className="bg-green-50 border border-green-200 rounded-xl p-4 text-center">
            <CheckCircle size={32} className="text-green-600 mx-auto mb-2" />
            <p className="font-bold text-green-800 text-lg">Stock Updated!</p>
            <p className="text-xs text-green-600">
              {restockResult.updated?.length || items.filter(i => i.product_id > 0).length} catalog items restocked
            </p>
          </div>

          {items.filter(i => i.product_id === 0).length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Detected — not in catalog</p>
              {items.filter(i => i.product_id === 0).map((item, i) => {
                const origIdx = items.indexOf(item)
                const added = addedItems.has(origIdx)
                return (
                  <div key={i} className="flex items-center gap-3 bg-yellow-50 border border-yellow-200 rounded-xl px-3 py-2.5">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-yellow-800 truncate">{item.name}</p>
                      <p className="text-xs text-yellow-600">×{item.quantity} detected</p>
                    </div>
                    <button
                      onClick={() => handleAddProduct(item, origIdx)}
                      disabled={added}
                      className={`text-xs font-bold px-3 py-1.5 rounded-lg ${added ? 'bg-green-100 text-green-700' : 'bg-paytm-blue text-white'}`}
                    >
                      {added ? '✓ Added' : '+ Add'}
                    </button>
                  </div>
                )
              })}
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
