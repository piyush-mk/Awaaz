import { useState, useEffect, useRef, useCallback } from 'react'
import {
  getInventory, getAlerts, getDashboard, getTransactions,
  parseVoice, restockInventory, editInventory,
  generateBill, confirmBill, textToSpeech,
} from '../api/client'

const DEMO_PHRASES = [
  { label: 'D1', text: 'do maggi ek surf excel chaar colgate' },
  { label: 'D2', text: 'das packet maggi paanch kilo chawal do litre tel' },
  { label: 'D3', text: 'aashirvaad atta teen bag tata namak chaar packet' },
  { label: 'D4', text: 'paanch dettol sabun teen vim bar do parle g' },
  { label: 'D5', text: 'ek patanjali shahad do colgate' },
]

const STATUS = { high: '#16a34a', medium: '#ca8a04', low: '#dc2626' }
const ts = () => new Date().toLocaleTimeString('en-IN', { hour12: false })

// ── Styles ────────────────────────────────────────────────────────────────────
const S = {
  page:    { fontFamily: 'system-ui, sans-serif', background: '#f1f5f9', minHeight: '100vh', padding: 0, margin: 0, maxWidth: '100%' },
  topbar:  { background: '#1e293b', color: '#fff', padding: '10px 20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' },
  body:    { display: 'grid', gridTemplateColumns: '420px 1fr', gap: 0, height: 'calc(100vh - 45px)' },
  left:    { background: '#fff', borderRight: '1px solid #e2e8f0', display: 'flex', flexDirection: 'column', overflow: 'hidden' },
  right:   { display: 'flex', flexDirection: 'column', overflow: 'hidden' },
  tabs:    { display: 'flex', borderBottom: '1px solid #e2e8f0', background: '#f8fafc' },
  tab:     (active) => ({ padding: '10px 16px', fontSize: 13, fontWeight: 600, cursor: 'pointer', border: 'none', background: 'none', borderBottom: active ? '2px solid #3b82f6' : '2px solid transparent', color: active ? '#3b82f6' : '#64748b' }),
  panel:   { padding: 16, flex: 1, overflowY: 'auto' },
  section: { marginBottom: 20 },
  label:   { fontSize: 11, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6, display: 'block' },
  input:   { width: '100%', border: '1px solid #e2e8f0', borderRadius: 6, padding: '8px 10px', fontSize: 13, boxSizing: 'border-box', background: '#f8fafc' },
  btn:     (c = '#3b82f6') => ({ background: c, color: '#fff', border: 'none', borderRadius: 6, padding: '8px 16px', fontSize: 13, fontWeight: 600, cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap' }),
  ghost:   { background: '#f1f5f9', color: '#334155', border: '1px solid #e2e8f0', borderRadius: 6, padding: '6px 12px', fontSize: 12, fontWeight: 600, cursor: 'pointer' },
  chip:    (c) => ({ background: c + '15', color: c, border: `1px solid ${c}40`, borderRadius: 4, padding: '2px 8px', fontSize: 11, fontWeight: 700 }),
  table:   { width: '100%', borderCollapse: 'collapse', fontSize: 12 },
  th:      { padding: '7px 10px', textAlign: 'left', background: '#f8fafc', borderBottom: '1px solid #e2e8f0', fontSize: 11, fontWeight: 700, color: '#64748b', textTransform: 'uppercase' },
  td:      (highlight) => ({ padding: '7px 10px', borderBottom: '1px solid #f1f5f9', background: highlight ? '#fef2f2' : 'transparent', fontSize: 12 }),
  logWrap: { flex: 1, overflowY: 'auto', background: '#0f172a', padding: 14, fontFamily: 'monospace' },
  logEntry:(ok) => ({ marginBottom: 14, borderLeft: `3px solid ${ok ? '#22c55e' : '#ef4444'}`, paddingLeft: 10 }),
  divider: { border: 'none', borderTop: '1px solid #e2e8f0', margin: '16px 0' },
}

export default function TestConsole() {
  const [tab, setTab]               = useState('flow')
  const [inventory, setInventory]   = useState([])
  const [log, setLog]               = useState([])
  const [parsedItems, setParsedItems] = useState([])
  const [bill, setBill]             = useState(null)
  const [transcript, setTranscript] = useState(DEMO_PHRASES[0].text)
  const [editId, setEditId]         = useState(1)
  const [editQty, setEditQty]       = useState('')
  const [ttsText, setTtsText]       = useState('Bill ban gaya. 294 rupee. QR code scan karein.')
  const [loading, setLoading]       = useState({})
  const logRef = useRef(null)

  const refreshInventory = useCallback(async () => {
    const inv = await getInventory()
    setInventory(inv)
  }, [])

  useEffect(() => { refreshInventory() }, [refreshInventory])
  useEffect(() => { if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight }, [log])

  const setLoad = (key, val) => setLoading(l => ({ ...l, [key]: val }))

  const run = useCallback(async (key, method, path, apiFn, body = null) => {
    setLoad(key, true)
    try {
      const res = await apiFn()
      setLog(l => [...l, { time: ts(), method, path, body, res, ok: true }])
      return res
    } catch (e) {
      setLog(l => [...l, { time: ts(), method, path, body, res: { error: e.message }, ok: false }])
      return null
    } finally {
      setLoad(key, false)
    }
  }, [])

  // ── Handlers ──────────────────────────────────────────────────────────────
  const doParse = async () => {
    const res = await run('parse', 'POST', '/api/voice/parse', () => parseVoice(null, transcript), { transcript })
    if (res) setParsedItems(res.items)
  }
  const doRestock = async () => {
    if (!parsedItems.length) return
    const res = await run('restock', 'POST', '/api/inventory/restock', () => restockInventory(parsedItems), { items: parsedItems })
    if (res) { await refreshInventory(); setParsedItems([]) }
  }
  const doGenBill = async () => {
    if (!parsedItems.length) return
    const res = await run('genbill', 'POST', '/api/bill/generate', () => generateBill(parsedItems), { items: parsedItems })
    if (res) setBill(res)
  }
  const doConfirmBill = async () => {
    if (!bill) return
    const res = await run('confirmbill', 'POST', '/api/bill/confirm', () => confirmBill(bill.items, bill.grand_total), { grand_total: bill.grand_total })
    if (res) { await refreshInventory(); setBill(null); setParsedItems([]) }
  }
  const doManualEdit = async () => {
    const qty = parseInt(editQty)
    if (isNaN(qty) || qty < 0) return
    const res = await run('edit', 'PUT', `/api/inventory/${editId}`, () => editInventory(Number(editId), qty), { product_id: editId, quantity: qty })
    if (res) await refreshInventory()
  }
  const doAlerts = () => run('alerts', 'GET', '/api/alerts', getAlerts)
  const doDash   = () => run('dash', 'GET', '/api/dashboard', getDashboard)
  const doTxns   = () => run('txns', 'GET', '/api/transactions', () => getTransactions(10))
  const doTTS    = async () => {
    const res = await run('tts', 'POST', '/api/voice/tts', () => textToSpeech(ttsText), { text: ttsText })
    if (res?.audio_base64) new Audio(`data:audio/mp3;base64,${res.audio_base64}`).play()
  }

  // ── Sub-renders ────────────────────────────────────────────────────────────
  function TabFlow() {
    return (
      <div style={S.panel}>
        {/* Step 1 */}
        <div style={S.section}>
          <span style={S.label}>Step 1 — Voice Parse</span>
          <div style={{ display: 'flex', gap: 6, marginBottom: 8, flexWrap: 'wrap' }}>
            {DEMO_PHRASES.map(p => (
              <button key={p.label} style={S.ghost} onClick={() => setTranscript(p.text)}>{p.label}</button>
            ))}
          </div>
          <input style={{ ...S.input, marginBottom: 8 }} value={transcript} onChange={e => setTranscript(e.target.value)} placeholder="Type Hinglish..." />
          <button style={S.btn()} onClick={doParse} disabled={loading.parse}>
            {loading.parse ? '...' : '▶ Parse'}
          </button>

          {parsedItems.length > 0 && (
            <div style={{ marginTop: 12, background: '#f0fdf4', borderRadius: 8, padding: 10 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: '#166534', marginBottom: 8 }}>
                ✅ {parsedItems.length} items parsed
              </div>
              {parsedItems.map(i => (
                <div key={i.product_id} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, padding: '4px 0', borderBottom: '1px solid #dcfce7' }}>
                  <span style={{ fontFamily: 'sans-serif' }}>{i.name_hi} <span style={{ color: '#86efac' }}>({i.name})</span></span>
                  <span style={{ fontWeight: 700 }}>× {i.quantity} {i.unit} · ₹{i.price}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <hr style={S.divider} />

        {/* Step 2 */}
        <div style={S.section}>
          <span style={S.label}>Step 2 — Choose action</span>
          <div style={{ display: 'flex', gap: 8 }}>
            <button style={S.btn('#16a34a')} onClick={doRestock} disabled={!parsedItems.length || loading.restock}>
              {loading.restock ? '...' : '📦 Restock'}
            </button>
            <button style={S.btn('#d97706')} onClick={doGenBill} disabled={!parsedItems.length || loading.genbill}>
              {loading.genbill ? '...' : '🧾 Make Bill'}
            </button>
          </div>
          {!parsedItems.length && <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 6 }}>Parse items first</div>}
        </div>

        {bill && (
          <>
            <hr style={S.divider} />
            <div style={S.section}>
              <span style={S.label}>Step 3 — Bill Preview</span>
              <div style={{ background: '#fffbeb', borderRadius: 8, padding: 10, marginBottom: 10 }}>
                {bill.items.map(i => (
                  <div key={i.product_id} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, padding: '3px 0' }}>
                    <span>{i.name_hi} × {i.quantity}</span>
                    <span>₹{i.subtotal} + ₹{i.gst_amount} GST = <b>₹{i.total}</b></span>
                  </div>
                ))}
                <div style={{ borderTop: '1px solid #fde68a', marginTop: 8, paddingTop: 8, fontWeight: 700, fontSize: 13, display: 'flex', justifyContent: 'space-between' }}>
                  <span>Grand Total</span><span style={{ color: '#d97706' }}>₹{bill.grand_total}</span>
                </div>
              </div>
              <button style={S.btn('#dc2626')} onClick={doConfirmBill} disabled={loading.confirmbill}>
                {loading.confirmbill ? '...' : '✅ Confirm Payment — deduct stock'}
              </button>
            </div>
          </>
        )}
      </div>
    )
  }

  function TabInventory() {
    return (
      <div style={S.panel}>
        <span style={S.label}>Manual Stock Correction</span>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 100px', gap: 8, marginBottom: 10 }}>
          <select style={S.input} value={editId} onChange={e => setEditId(e.target.value)}>
            {inventory.map(i => (
              <option key={i.product_id} value={i.product_id}>
                [{i.product_id}] {i.name} — {i.quantity} {i.unit}
              </option>
            ))}
          </select>
          <input style={S.input} type="number" min="0" value={editQty} onChange={e => setEditQty(e.target.value)} placeholder="New qty" />
        </div>
        <button style={S.btn('#7c3aed')} onClick={doManualEdit} disabled={!editQty || loading.edit}>
          {loading.edit ? '...' : '✏️ Update Quantity'}
        </button>
      </div>
    )
  }

  function TabReads() {
    return (
      <div style={S.panel}>
        <span style={S.label}>Read Endpoints</span>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <button style={S.btn('#0891b2')} onClick={doAlerts} disabled={loading.alerts}>GET /api/alerts</button>
          <button style={S.btn('#0891b2')} onClick={doDash}   disabled={loading.dash}>GET /api/dashboard</button>
          <button style={S.btn('#0891b2')} onClick={doTxns}   disabled={loading.txns}>GET /api/transactions</button>
        </div>
        <hr style={S.divider} />
        <span style={S.label}>TTS Test</span>
        <input style={{ ...S.input, marginBottom: 8 }} value={ttsText} onChange={e => setTtsText(e.target.value)} />
        <button style={S.btn('#059669')} onClick={doTTS} disabled={loading.tts}>
          {loading.tts ? '...' : '🔊 Speak'}
        </button>
        <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 6 }}>Plays audio if SARVAM_API_KEY is set in .env</div>
      </div>
    )
  }

  // ── Main render ────────────────────────────────────────────────────────────
  return (
    <div style={S.page}>
      {/* Top bar */}
      <div style={S.topbar}>
        <span style={{ fontWeight: 700, fontSize: 14 }}>🛠 Paytm Voice Suite — Test Console</span>
        <div style={{ display: 'flex', gap: 8 }}>
          <button style={S.ghost} onClick={refreshInventory}>↻ Refresh</button>
          <button style={{ ...S.ghost, color: '#ef4444' }} onClick={() => setLog([])}>Clear Log</button>
        </div>
      </div>

      <div style={S.body}>
        {/* LEFT — Controls */}
        <div style={S.left}>
          <div style={S.tabs}>
            {[['flow', '▶ Flow'], ['inventory', '📦 Inventory'], ['reads', '📋 Reads']].map(([key, lbl]) => (
              <button key={key} style={S.tab(tab === key)} onClick={() => setTab(key)}>{lbl}</button>
            ))}
          </div>
          {tab === 'flow'      && <TabFlow />}
          {tab === 'inventory' && <TabInventory />}
          {tab === 'reads'     && <TabReads />}
        </div>

        {/* RIGHT — Inventory + Log */}
        <div style={S.right}>
          {/* Inventory table */}
          <div style={{ padding: '12px 16px', borderBottom: '1px solid #e2e8f0', background: '#fff', overflowX: 'auto' }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: '#64748b', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Live Inventory · {inventory.filter(i => i.status === 'low').length} low stock
            </div>
            <table style={S.table}>
              <thead>
                <tr>{['ID', 'हिंदी', 'Name', 'Qty', 'Unit', 'Threshold', 'Status', 'Value'].map(h => (
                  <th key={h} style={S.th}>{h}</th>
                ))}</tr>
              </thead>
              <tbody>
                {inventory.map(item => (
                  <tr key={item.product_id}>
                    <td style={S.td(item.status==='low')}>{item.product_id}</td>
                    <td style={{ ...S.td(item.status==='low'), fontFamily: 'sans-serif' }}>{item.name_hi}</td>
                    <td style={S.td(item.status==='low')}>{item.name}</td>
                    <td style={{ ...S.td(item.status==='low'), fontWeight: 700 }}>{item.quantity}</td>
                    <td style={S.td(item.status==='low')}>{item.unit}</td>
                    <td style={{ ...S.td(item.status==='low'), color: '#94a3b8' }}>{item.threshold}</td>
                    <td style={S.td(item.status==='low')}>
                      <span style={S.chip(STATUS[item.status])}>{item.status}</span>
                    </td>
                    <td style={S.td(item.status==='low')}>₹{(item.quantity * item.price).toFixed(0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Command log */}
          <div style={S.logWrap} ref={logRef}>
            {log.length === 0
              ? <div style={{ color: '#475569', fontSize: 12 }}>Command log will appear here...</div>
              : log.map((e, i) => (
                <div key={i} style={S.logEntry(e.ok)}>
                  <div style={{ color: e.ok ? '#86efac' : '#fca5a5', fontSize: 12, fontWeight: 700, marginBottom: 2 }}>
                    [{e.time}] {e.method} {e.path}
                  </div>
                  {e.body && (
                    <pre style={{ color: '#93c5fd', fontSize: 11, margin: '0 0 2px 0', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                      REQ {JSON.stringify(e.body, null, 2)}
                    </pre>
                  )}
                  <pre style={{ color: e.ok ? '#d1fae5' : '#fecaca', fontSize: 11, margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                    RES {JSON.stringify(e.res, null, 2)}
                  </pre>
                </div>
              ))
            }
          </div>
        </div>
      </div>
    </div>
  )
}
