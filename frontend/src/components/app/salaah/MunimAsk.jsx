import { useCallback, useRef, useState } from 'react'
import { Send } from 'lucide-react'
import MicOrb from '../MicOrb'
import SourceChip from '../SourceChip'
import { Card, Chip, inputCls } from '../ui'
import { useApp } from '../AppContext'
import useRecorder from '../../../hooks/useRecorder'
import useLoad from '../../../lib/useLoad'
import { askMunim, getMunimExamples } from '../../../api/client'
import { speak } from '../../../lib/audio'
import { inr } from '../../../lib/format'

function fmt(v, col) {
  if (typeof v === 'number' && /amount|value|total|rupee|balance/i.test(col)) return inr(v)
  if (typeof v === 'number') return Number.isInteger(v) ? v : v.toFixed(1)
  return v ?? '-'
}

function Table({ table }) {
  if (!table?.rows?.length) return null
  return (
    <div className="mt-3 overflow-x-auto rounded-xl border border-line">
      <table className="w-full text-sm tabular">
        <thead className="bg-bg-app text-[11px] uppercase text-ink-3">
          <tr>{table.columns.map((c) => <th key={c} className="px-2.5 py-2 text-left font-semibold">{c}</th>)}</tr>
        </thead>
        <tbody>
          {table.rows.map((r, i) => (
            <tr key={i} className="border-t border-line">
              {r.map((v, j) => <td key={j} className="px-2.5 py-2">{fmt(v, table.columns[j])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Ask your munim: mic or text -> spoken answer + table. */
export default function MunimAsk() {
  const { showError } = useApp()
  const { data: ex } = useLoad(() => getMunimExamples(), [])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState(null)
  const queue = useRef(Promise.resolve())

  const ask = useCallback(
    async (job) => {
      setBusy(true)
      try {
        const r = await askMunim(job)
        setRes(r)
        speak({ spoken_text: r.spoken_text || r.answer, audio_url: r.audio_url, audio_base64: r.audio_base64 })
      } catch (e) {
        showError(e)
      } finally {
        setBusy(false)
      }
    },
    [showError],
  )
  const enqueue = useCallback((job) => {
    queue.current = queue.current.then(() => ask(job)).catch(() => {})
  }, [ask])

  const rec = useRecorder({ onAudio: (blob) => enqueue({ audio: blob }) })

  const submit = (e, phrase) => {
    e?.preventDefault?.()
    const t = (phrase ?? text).trim()
    if (!t) return
    setText('')
    enqueue({ text: t })
  }

  return (
    <div className="space-y-3">
      <Card>
        <div className="flex items-center gap-3">
          <MicOrb rec={rec} busy={busy} size={72} />
          <form onSubmit={submit} className="flex-1 flex gap-2 min-w-0">
            <input className={inputCls} placeholder="ya poochhein: aaj ki sale?" value={text} onChange={(e) => setText(e.target.value)} />
            <button type="submit" disabled={!text.trim() || busy} aria-label="Poochho" className="w-12 h-12 flex-shrink-0 rounded-xl bg-paytm-blue text-ink flex items-center justify-center disabled:opacity-50">
              <Send size={20} />
            </button>
          </form>
        </div>
        <div className="text-xs text-ink-3 mt-2 h-4">{rec.error || (busy ? 'Soch raha hoon...' : rec.recording ? 'Chhodein ya dobara tap karein' : 'Dabayein aur poochhein')}</div>
        <div className="mt-2 flex flex-wrap gap-2">
          {(ex?.examples || []).slice(0, 5).map((q) => (
            <button key={q} onClick={() => submit(null, q)} disabled={busy} className="min-h-[44px] px-3 rounded-full bg-bg-app text-sm font-medium text-ink-3 text-left">{q}</button>
          ))}
        </div>
      </Card>

      {res && (
        <Card>
          <div className="flex items-start gap-2">
            <div className="flex-1 min-w-0">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-3">Aapne poochha</div>
              <div className="font-hindi text-base font-bold">&ldquo;{res.transcript || res.question}&rdquo;</div>
            </div>
            <SourceChip source={res.source} latency={res.latency_ms} demo={res.tts_source === 'fixture' && res.source === 'fixture'} />
          </div>
          <p className="mt-2 font-hindi text-xl font-bold leading-snug">{res.answer}</p>
          {res.understood === false && <Chip tone="yellow" className="mt-2">samajh nahi aaya</Chip>}
          {(res.tables?.length ? res.tables : res.table ? [res.table] : []).map((t, i) => <Table key={i} table={t} />)}
        </Card>
      )}
    </div>
  )
}
