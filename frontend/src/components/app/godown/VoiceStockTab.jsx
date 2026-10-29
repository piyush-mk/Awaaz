import { useCallback, useRef, useState } from 'react'
import { Keyboard, Send } from 'lucide-react'
import MicOrb from '../MicOrb'
import ActionCard from '../ActionCard'
import SourceChip from '../SourceChip'
import { Card, inputCls } from '../ui'
import { useApp } from '../AppContext'
import useRecorder from '../../../hooks/useRecorder'
import { sendUtterance } from '../../../api/client'
import { speak } from '../../../lib/audio'

const EXAMPLES = ['das packet maggi paanch kilo chawal do litre tel', 'aashirvaad atta teen bag tata namak chaar packet']

/** Stock in by voice: speak what arrived, confirm the restock card. Uses its own session so the bill is untouched. */
export default function VoiceStockTab() {
  const { sessionId, showError, showToast } = useApp()
  const stockSession = `${sessionId}-stock`
  const [busy, setBusy] = useState(false)
  const [last, setLast] = useState(null)
  const [actions, setActions] = useState([])
  const [text, setText] = useState('')
  const [showText, setShowText] = useState(true)
  const queue = useRef(Promise.resolve())

  const submit = useCallback(
    async (job) => {
      setBusy(true)
      try {
        const res = await sendUtterance({ ...job, context: 'stock', sessionId: stockSession })
        setLast(res)
        setActions((cur) => {
          const open = (res.actions || []).filter((a) => a.status === 'proposed')
          return [...cur.filter((c) => !open.some((o) => o.id === c.id)), ...open]
        })
        speak(res)
      } catch (e) {
        showError(e)
      } finally {
        setBusy(false)
      }
    },
    [showError, stockSession],
  )
  const enqueue = useCallback((job) => {
    queue.current = queue.current.then(() => submit(job)).catch(() => {})
  }, [submit])

  const rec = useRecorder({ onAudio: (blob, meta) => enqueue({ audio: blob, filename: meta.filename }) })

  const sendText = (e, phrase) => {
    e?.preventDefault?.()
    const t = (phrase ?? text).trim()
    if (!t) return
    setText('')
    enqueue({ text: t })
  }

  return (
    <div className="space-y-3">
      <Card className="text-center">
        <div className="font-hindi text-2xl font-bold">Kya maal aaya? Bolein.</div>
        <div className="text-sm text-ink-3 mb-4">&ldquo;das packet maggi, paanch kilo chawal&rdquo;</div>
        <div className="flex justify-center"><MicOrb rec={rec} busy={busy} /></div>
        <div className="text-xs text-ink-3 mt-2 h-4">{rec.error || (busy ? 'Samajh raha hoon...' : rec.recording ? 'Chhodein ya dobara tap karein' : 'Dabayein aur bolein')}</div>
        <button onClick={() => setShowText((v) => !v)} className="mt-2 inline-flex items-center gap-1 text-sm text-ink-3 min-h-[44px]">
          <Keyboard size={16} /> ya type karein
        </button>
        {showText && (
          <form onSubmit={sendText} className="mt-1 flex gap-2">
            <input className={inputCls} placeholder="das packet maggi" value={text} onChange={(e) => setText(e.target.value)} />
            <button type="submit" disabled={!text.trim() || busy} aria-label="Bhejein" className="w-12 h-12 flex-shrink-0 rounded-xl bg-paytm-blue text-ink flex items-center justify-center disabled:opacity-50">
              <Send size={20} />
            </button>
          </form>
        )}
        <div className="mt-3 flex flex-col gap-2">
          {EXAMPLES.map((ex) => (
            <button key={ex} onClick={() => sendText(null, ex)} className="min-h-[44px] rounded-xl bg-bg-app px-3 text-left font-hindi text-sm text-ink-3">
              &ldquo;{ex}&rdquo;
            </button>
          ))}
        </div>
      </Card>

      {last && (
        <Card>
          <div className="flex items-start gap-2">
            <div className="flex-1">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-3">Aapne kaha</div>
              <div className="font-hindi text-lg font-bold">&ldquo;{last.transcript}&rdquo;</div>
            </div>
            <SourceChip source={last.source} latency={last.latency_ms} demo={last.demo_mode && last.source === 'fixture'} />
          </div>
          {last.spoken_text && <p className="font-hindi text-base text-ink-3 mt-1">{last.spoken_text}</p>}
        </Card>
      )}

      {actions.map((a) => (
        <ActionCard
          key={a.id}
          action={a}
          onResolved={(res, action, kind) => {
            setActions((cur) => cur.filter((x) => x.id !== action.id))
            if (kind === 'confirm') {
              showToast(res.spoken_text || 'Stock update ho gaya')
              speak(res)
            }
          }}
        />
      ))}
    </div>
  )
}
