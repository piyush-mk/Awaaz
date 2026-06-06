import { useState, useEffect, useRef, useCallback } from 'react'
import {
  getInventory, getAlerts, getDashboard, getTransactions,
  parseVoice, restockInventory, editInventory,
  generateBill, confirmBill, textToSpeech,
} from '../api/client'

// ─── Demo phrases straight from CLAUDE.md ───────────────────────────────────
const DEMO_PHRASES = [
  "do maggi ek surf excel chaar colgate",
  "das packet maggi paanch kilo chawal do litre tel",
  "aashirvaad atta teen bag tata namak chaar packet",
  "paanch dettol sabun teen vim bar do parle g",
  "ek patanjali shahad do colgate",
]

const STATUS_COLOR = { high: '#22c55e', medium: '#ca8a04', low: '#ef4444' }

// ─── Tiny helpers ────────────────────────────────────────────────────────────
function ts() {
  return new Date().toLocaleTimeString('en-IN', { hour12: false })
}

function LogEntry({ entry }) {
  const ok = !entry.error
  return (
    <div style={{ borderLeft: `3px solid ${ok ? '#22c55e' : '#ef4444'}`, paddingLeft: 8, marginBottom: 10 }}>
      <div style={{ fontSize: 11, color: '#888' }}>[{entry.time}] <b>{entry.method}</b> {entry.path}</div>
      {entry.body && (
        <pre style={{ fontSize: 11, color: '#555', margin: '2px 0', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
          REQ: {JSON.stringify(entry.body, null, 2)}
        </pre>
      )}
      <pre style={{ fontSize: 11, color: ok ? '#166534' : '#991b1b', margin: '2px 0', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
        {ok ? '✅' : '❌'} {JSON.stringify(entry.res, null, 2)}
      </pre>
    </div>
  )
}

// ─── Main component ──────────────────────────────────────────────────────────
export default function TestConsole() {
  const [inventory, setInventory] = useState([])
  const [log, setLog] = useState([])
  const [parsedItems, setParsedItems] = useState([])
  const [bill, setBill] = useState(null)
  const [transcript, setTranscript] = useState(DEMO_PHRASES[0])
  const [editId, setEditId] = useState(1)
  const [editQty, setEditQty] = useState('')
  const [ttsText, setTtsText] = useState('Bill ban gaya. 294 rupee. QR code scan karein.')
  const logRef = useRef(null)

  const refreshInventory = useCallback(async () => {
    const inv = await getInventory()
    setInventory(inv)
  }, [])

  useEffect(() => { refreshInventory() }, [refreshInventory])
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [log])

  // ── Generic API runner that logs everything ──────────────────────────────
  const run = useCallback(async (label, method, path, apiFn, body = null) => {
    try {
      const res = await apiFn()
      setLog((l) => [...l, { time: ts(), method, path, body, res, error: false, label }])
      return res
    } catch (e) {
      const res = { error: e.message }
      setLog((l) => [...l, { time: ts(), method, path, body, res, error: true, label }])
      return null
    }
  }, [])

  // ─── Handlers ─────────────────────────────────────────────────────────────
  const handleVoiceParse = async () => {
    const res = await run('Voice Parse', 'POST', '/api/voice/parse', () => parseVoice(null, transcript), { transcript })
    if (res) setParsedItems(res.items)
  }

  const handleRestock = async () => {
    if (!parsedItems.length) return alert('Run Voice Parse first')
    const res = await run('Restock', 'POST', '/api/inventory/restock', () => restockInventory(parsedItems), { items: parsedItems })
    if (res) await refreshInventory()
  }

  const handleGenerateBill = async () => {
    if (!parsedItems.length) return alert('Run Voice Parse first')
    const res = await run('Generate Bill', 'POST', '/api/bill/generate', () => generateBill(parsedItems), { items: parsedItems })
    if (res) setBill(res)
  }

  const handleConfirmBill = async () => {
    if (!bill) return alert('Generate Bill first')
    const res = await run('Confirm Bill', 'POST', '/api/bill/confirm', () => confirmBill(bill.items, bill.grand_total), { grand_total: bill.grand_total })
    if (res) { await refreshInventory(); setBill(null) }
  }

  const handleManualEdit = async () => {
    const qty = parseInt(editQty)
    if (isNaN(qty) || qty < 0) return alert('Enter a valid quantity')
    const res = await run('Manual Edit', 'PUT', `/api/inventory/${editId}`, () => editInventory(Number(editId), qty, 'test_correction'), { product_id: editId, quantity: qty })
    if (res) await refreshInventory()
  }

  const handleAlerts = async () => {
    await run('Alerts', 'GET', '/api/alerts', () => getAlerts())
  }

  const handleDashboard = async () => {
    await run('Dashboard', 'GET', '/api/dashboard', () => getDashboard())
  }

  const handleTransactions = async () => {
    await run('Transactions', 'GET', '/api/transactions', () => getTransactions(10))
  }

  const handleTTS = async () => {
    const res = await run('TTS', 'POST', '/api/voice/tts', () => textToSpeech(ttsText), { text: ttsText })
    if (res?.audio_base64) {
      const audio = new Audio(`data:audio/mp3;base64,${res.audio_base64}`)
      audio.play()
    }
  }

  // ─── Render ────────────────────────────────────────────────────────────────
  const col = { display: 'flex', flexDirection: 'column', gap: 6 }
  const box = { background: '#f8f8f8', border: '1px solid #e0e0e0', borderRadius: 8, padding: 12 }
  const btn = (color = '#1e40af') => ({
    background: color, color: '#fff', border: 'none', borderRadius: 6,
    padding: '6px 12px', cursor: 'pointer', fontSize: 13, fontWeight: 600,
  })
  const input = { border: '1px solid #ccc', borderRadius: 6, padding: '5px 8px', fontSize: 13, width: '100%', boxSizing: 'border-box' }
  const label = { fontSize: 12, color: '#555', fontWeight: 600, marginBottom: 2, display: 'block' }

  return (
    <div style={{ fontFamily: 'monospace', padding: 16, maxWidth: 1200, margin: '0 auto', background: '#fff', minHeight: '100vh' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <h2 style={{ margin: 0, fontSize: 18 }}>🛠 Backend Test Console</h2>
        <div style={{ display: 'flex', gap: 8 }}>
          <button style={btn('#16a34a')} onClick={refreshInventory}>↻ Refresh Inventory</button>
          <button style={btn('#dc2626')} onClick={() => setLog([])}>Clear Log</button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>

        {/* ── LEFT: Controls ─────────────────────────────────────────────── */}
        <div style={col}>

          {/* Voice Parse */}
          <div style={box}>
            <b style={{ fontSize: 13 }}>1. Voice Parse → /api/voice/parse</b>
            <div style={{ ...col, marginTop: 8 }}>
              <span style={label}>Hinglish transcript (text mode)</span>
              <input style={input} value={transcript} onChange={e => setTranscript(e.target.value)} />
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 4 }}>
                {DEMO_PHRASES.map((p, i) => (
                  <button key={i} style={{ ...btn('#6b7280'), fontSize: 11, padding: '3px 8px' }} onClick={() => setTranscript(p)}>
                    Demo {i + 1}
                  </button>
                ))}
              </div>
              <button style={btn()} onClick={handleVoiceParse}>▶ Parse</button>
            </div>
            {parsedItems.length > 0 && (
              <div style={{ marginTop: 8, fontSize: 12 }}>
                <b>Parsed items ({parsedItems.length}):</b>
                <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 4 }}>
                  <thead>
                    <tr style={{ background: '#e5e7eb' }}>
                      {['ID', 'Name (Hindi)', 'Qty', 'Unit', 'Price', 'GST%'].map(h => (
                        <th key={h} style={{ padding: '3px 6px', textAlign: 'left', fontSize: 11 }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {parsedItems.map(item => (
                      <tr key={item.product_id} style={{ borderBottom: '1px solid #e5e7eb' }}>
                        <td style={{ padding: '3px 6px', fontSize: 11 }}>{item.product_id}</td>
                        <td style={{ padding: '3px 6px', fontSize: 11 }}>{item.name_hi}</td>
                        <td style={{ padding: '3px 6px', fontSize: 11 }}>{item.quantity}</td>
                        <td style={{ padding: '3px 6px', fontSize: 11 }}>{item.unit}</td>
                        <td style={{ padding: '3px 6px', fontSize: 11 }}>₹{item.price}</td>
                        <td style={{ padding: '3px 6px', fontSize: 11 }}>{item.gst_rate}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Restock */}
          <div style={box}>
            <b style={{ fontSize: 13 }}>2. Restock → POST /api/inventory/restock</b>
            <div style={{ marginTop: 6, fontSize: 12, color: '#555' }}>Uses parsed items from step 1</div>
            <button style={{ ...btn('#16a34a'), marginTop: 8 }} onClick={handleRestock}>▶ Restock</button>
          </div>

          {/* Generate Bill */}
          <div style={box}>
            <b style={{ fontSize: 13 }}>3. Generate Bill → POST /api/bill/generate</b>
            <div style={{ marginTop: 6, fontSize: 12, color: '#555' }}>Uses parsed items from step 1</div>
            <button style={{ ...btn('#d97706'), marginTop: 8 }} onClick={handleGenerateBill}>▶ Generate Bill</button>
            {bill && (
              <div style={{ marginTop: 8, fontSize: 12 }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ background: '#fef3c7' }}>
                      {['Item', 'Qty', 'Subtotal', 'GST', 'Total'].map(h => (
                        <th key={h} style={{ padding: '3px 6px', textAlign: 'left', fontSize: 11 }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {bill.items.map(i => (
                      <tr key={i.product_id} style={{ borderBottom: '1px solid #e5e7eb' }}>
                        <td style={{ padding: '3px 6px', fontSize: 11 }}>{i.name_hi}</td>
                        <td style={{ padding: '3px 6px', fontSize: 11 }}>{i.quantity}</td>
                        <td style={{ padding: '3px 6px', fontSize: 11 }}>₹{i.subtotal}</td>
                        <td style={{ padding: '3px 6px', fontSize: 11 }}>₹{i.gst_amount}</td>
                        <td style={{ padding: '3px 6px', fontSize: 11, fontWeight: 600 }}>₹{i.total}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div style={{ marginTop: 6, textAlign: 'right', fontSize: 13 }}>
                  Subtotal: ₹{bill.subtotal} | GST: ₹{bill.total_gst} | <b>Grand Total: ₹{bill.grand_total}</b>
                </div>
              </div>
            )}
          </div>

          {/* Confirm Bill */}
          <div style={box}>
            <b style={{ fontSize: 13 }}>4. Confirm Bill → POST /api/bill/confirm</b>
            <div style={{ marginTop: 6, fontSize: 12, color: '#555' }}>Deducts inventory + creates sale transactions</div>
            <button style={{ ...btn('#dc2626'), marginTop: 8 }} onClick={handleConfirmBill}>▶ Confirm (Simulate Payment)</button>
          </div>

          {/* Manual Edit */}
          <div style={box}>
            <b style={{ fontSize: 13 }}>5. Manual Edit → PUT /api/inventory/:id</b>
            <div style={{ ...col, marginTop: 8 }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                <div>
                  <span style={label}>Product ID (1–10)</span>
                  <select style={input} value={editId} onChange={e => setEditId(e.target.value)}>
                    {inventory.map(i => (
                      <option key={i.product_id} value={i.product_id}>
                        {i.product_id} – {i.name} ({i.quantity} {i.unit})
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <span style={label}>New Quantity</span>
                  <input style={input} type="number" min="0" value={editQty} onChange={e => setEditQty(e.target.value)} placeholder="e.g. 15" />
                </div>
              </div>
              <button style={btn('#7c3aed')} onClick={handleManualEdit}>▶ Update</button>
            </div>
          </div>

          {/* Misc */}
          <div style={box}>
            <b style={{ fontSize: 13 }}>6. Misc Reads</b>
            <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
              <button style={btn('#0891b2')} onClick={handleAlerts}>GET /alerts</button>
              <button style={btn('#0891b2')} onClick={handleDashboard}>GET /dashboard</button>
              <button style={btn('#0891b2')} onClick={handleTransactions}>GET /transactions</button>
            </div>
          </div>

          {/* TTS */}
          <div style={box}>
            <b style={{ fontSize: 13 }}>7. TTS → POST /api/voice/tts</b>
            <div style={{ ...col, marginTop: 8 }}>
              <input style={input} value={ttsText} onChange={e => setTtsText(e.target.value)} />
              <button style={btn('#059669')} onClick={handleTTS}>▶ Speak (plays audio if API key set)</button>
            </div>
          </div>
        </div>

        {/* ── RIGHT: Inventory + Log ──────────────────────────────────────── */}
        <div style={col}>

          {/* Live Inventory */}
          <div style={box}>
            <b style={{ fontSize: 13 }}>📦 Live Inventory (auto-refreshes after each action)</b>
            <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 8, fontSize: 12 }}>
              <thead>
                <tr style={{ background: '#e5e7eb' }}>
                  {['ID', 'Hindi', 'Name', 'Qty', 'Unit', 'Threshold', 'Status', '₹Value'].map(h => (
                    <th key={h} style={{ padding: '4px 6px', textAlign: 'left', fontSize: 11 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {inventory.map(item => (
                  <tr key={item.product_id} style={{ borderBottom: '1px solid #e5e7eb', background: item.status === 'low' ? '#fef2f2' : 'transparent' }}>
                    <td style={{ padding: '4px 6px' }}>{item.product_id}</td>
                    <td style={{ padding: '4px 6px', fontFamily: 'sans-serif' }}>{item.name_hi}</td>
                    <td style={{ padding: '4px 6px' }}>{item.name}</td>
                    <td style={{ padding: '4px 6px', fontWeight: 700 }}>{item.quantity}</td>
                    <td style={{ padding: '4px 6px' }}>{item.unit}</td>
                    <td style={{ padding: '4px 6px', color: '#888' }}>{item.threshold}</td>
                    <td style={{ padding: '4px 6px', color: STATUS_COLOR[item.status], fontWeight: 600 }}>{item.status}</td>
                    <td style={{ padding: '4px 6px' }}>₹{(item.quantity * item.price).toFixed(0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Command Log */}
          <div style={{ ...box, flex: 1 }}>
            <b style={{ fontSize: 13 }}>📋 Command Log ({log.length} entries)</b>
            <div
              ref={logRef}
              style={{ marginTop: 8, height: 420, overflowY: 'auto', background: '#1e1e1e', borderRadius: 6, padding: 10 }}
            >
              {log.length === 0 && (
                <div style={{ color: '#666', fontSize: 12 }}>No commands yet. Run something on the left.</div>
              )}
              {log.map((entry, i) => (
                <div key={i} style={{ marginBottom: 12 }}>
                  <div style={{ color: entry.error ? '#f87171' : '#86efac', fontSize: 12, fontWeight: 700 }}>
                    [{entry.time}] {entry.method} {entry.path} {entry.error ? '❌' : '✅'}
                  </div>
                  {entry.body && (
                    <pre style={{ color: '#93c5fd', fontSize: 11, margin: '2px 0 0 0', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                      REQ → {JSON.stringify(entry.body, null, 2)}
                    </pre>
                  )}
                  <pre style={{ color: entry.error ? '#fca5a5' : '#d1fae5', fontSize: 11, margin: '2px 0 0 0', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                    RES ← {JSON.stringify(entry.res, null, 2)}
                  </pre>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
