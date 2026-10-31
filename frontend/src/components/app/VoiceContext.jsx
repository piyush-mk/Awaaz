import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { Send, Square, X } from 'lucide-react'
import ActionCard from './ActionCard'
import SourceChip from './SourceChip'
import { Chip, Sheet, Spinner, inputCls } from './ui'
import { useApp } from './AppContext'
import useRecorder from '../../hooks/useRecorder'
import { askShop, sendUtterance } from '../../api/client'
import { speak } from '../../lib/audio'
import { inr } from '../../lib/format'
import { tr } from '../../lib/i18n'

const ASK_EXAMPLES = ['aaj ki sale kitni hai', 'is hafte sabse zyada kya bika', 'verma ji ka kitna baaki hai']

/** What the mic does in each room. Examples are shown translated but sent like this: the parser knows these forms. */
const ROOMS = {
  counter: { context: 'counter', hint: 'do maggi, ek surf excel', examples: ['do maggi ek surf excel chaar colgate', 'bees rupaye ki cheeni', 'bas kitna hua'] },
  godown: { context: 'stock', hint: 'das packet maggi, paanch kilo chawal', examples: ['das packet maggi paanch kilo chawal', 'aashirvaad atta teen bag tata namak chaar packet'] },
  khata: { context: 'khata', hint: 'Verma ji ke khate mein 500', examples: ['verma ji ke khate mein paanch sau', 'verma ji ne do sau diye'] },
  hisaab: { context: 'ask', hint: 'aaj sabse zyada kya bika?', examples: ASK_EXAMPLES },
  salaah: { context: 'ask', hint: 'verma ji ka kitna baaki hai?', examples: ASK_EXAMPLES },
}

const roomFor = (pathname) => ROOMS[pathname.split('/')[2]] || ROOMS.counter

const Ctx = createContext(null)

export function useVoice() {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useVoice must be used inside <VoiceProvider>')
  return ctx
}

/** While the calling screen is mounted, it handles every utterance itself (the Counter does). */
export function useVoiceHandler(handler) {
  const { setHandler } = useVoice()
  const ref = useRef(handler)
  ref.current = handler
  useEffect(() => {
    const fn = (job) => ref.current(job)
    setHandler(fn)
    return () => setHandler(null)
  }, [setHandler])
}

function AnswerTable({ table }) {
  if (!table?.rows?.length) return null
  const fmt = (v, col) => {
    if (typeof v === 'number' && /amount|value|total|rupee|balance/i.test(col)) return inr(v)
    if (typeof v === 'number') return Number.isInteger(v) ? v : v.toFixed(1)
    return v ?? '-'
  }
  return (
    <div className="mt-3 overflow-x-auto">
      <table className="w-full text-sm tabular">
        <thead className="text-xs text-ink-3">
          <tr>{table.columns.map((c) => <th key={c} className="py-1.5 pr-3 text-left font-medium">{c}</th>)}</tr>
        </thead>
        <tbody>
          {table.rows.map((r, i) => (
            <tr key={i} className="border-t border-line">
              {r.map((v, j) => <td key={j} className="py-2 pr-3">{fmt(v, table.columns[j])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** What was heard and what happened: the answer, or Haan / Nahi cards. */
function ResultSheet({ result, onClose, onActionDone }) {
  const { showToast } = useApp()
  if (!result) return null
  const { transcript, spoken, understood, tables, source, latency, demo, actions } = result
  return (
    <Sheet open onClose={onClose} title={<span data-heard className="italic font-normal text-lg">&ldquo;{transcript}&rdquo;</span>}>
      <SourceChip source={source} latency={latency} demo={demo} />
      {spoken && !actions?.length && <p className="mt-1 font-hindi text-xl font-semibold leading-snug">{spoken}</p>}
      {understood === false && <Chip tone="yellow" className="mt-2">{tr('samajh nahi aaya')}</Chip>}
      {(tables || []).map((t, i) => <AnswerTable key={i} table={t} />)}
      <div className="mt-3 space-y-3">
        {(actions || []).map((a) => (
          <ActionCard
            key={a.id}
            action={a}
            onResolved={(res, action, kind) => {
              onActionDone(action.id)
              if (kind === 'confirm') {
                showToast(tr('Ho gaya'))
                speak(res)
              }
            }}
          />
        ))}
      </div>
    </Sheet>
  )
}

/** Type instead of speak: for a noisy shop, or a phone without a mic. */
function TypeSheet({ open, room, busy, onClose, onSubmit }) {
  const [text, setText] = useState('')
  const send = (e, phrase) => {
    e?.preventDefault?.()
    const t = (phrase ?? text).trim()
    if (!t) return
    setText('')
    onSubmit(t)
  }
  return (
    <Sheet open={open} onClose={onClose} title={tr('Likhein')}>
      <form onSubmit={send} className="flex gap-2">
        <input
          className={inputCls}
          aria-label={tr('Type karein')}
          placeholder={tr(room.hint)}
          value={text}
          onChange={(e) => setText(e.target.value)}
          autoFocus
        />
        <button
          type="submit"
          disabled={!text.trim() || busy}
          aria-label={tr('Bhejein')}
          className="w-12 h-12 flex-shrink-0 rounded-xl bg-paytm-blue text-ink flex items-center justify-center disabled:opacity-50"
        >
          <Send size={20} />
        </button>
      </form>
      <ul className="mt-3 divide-y divide-line">
        {room.examples.map((ex) => (
          <li key={ex}>
            <button onClick={() => send(null, ex)} className="w-full min-h-[48px] text-left font-hindi text-base text-ink-3">
              &ldquo;{tr(ex)}&rdquo;
            </button>
          </li>
        ))}
      </ul>
    </Sheet>
  )
}

/** Full-screen listening view: bars follow the real microphone level. */
function Listening({ rec, thinking, room, onStop, onCancel }) {
  const lvl = Math.min(1, rec.level * 9)
  const bars = 21
  return (
    <div className="listen-in absolute inset-0 z-30 bg-ink text-white flex flex-col" role="status" aria-live="polite">
      <div className="flex items-center justify-between px-4 pt-4 min-h-[60px]">
        <span className="text-base text-white/70">{thinking ? tr('Samajh raha hoon') : tr('Sun raha hoon')}</span>
        {!thinking && (
          <button onClick={onCancel} aria-label={tr('Radd karein')} className="w-11 h-11 rounded-full bg-white/10 flex items-center justify-center">
            <X size={20} />
          </button>
        )}
      </div>
      <div className="flex-1 flex flex-col items-center justify-center px-6">
        <div className={`flex items-center justify-center gap-[5px] h-44 ${thinking ? 'listen-think' : ''}`} aria-hidden="true">
          {Array.from({ length: bars }, (_, i) => {
            const shape = Math.sin(((i + 1) / (bars + 1)) * Math.PI)
            const wobble = 0.65 + 0.35 * Math.sin(i * 2.4)
            const h = thinking ? 10 + 26 * shape : 10 + 150 * shape * wobble * lvl
            return <span key={i} className="w-[6px] rounded-full bg-paytm-blue transition-[height] duration-75" style={{ height: h }} />
          })}
        </div>
      </div>
      <div className="pb-10 flex flex-col items-center min-h-[150px] justify-end">
        {thinking ? (
          <Spinner size={32} className="text-paytm-blue" />
        ) : (
          <>
            <button onClick={onStop} aria-label={tr('Bhejein')} className="w-[84px] h-[84px] rounded-full bg-accent text-ink flex items-center justify-center">
              <Square size={28} fill="currentColor" />
            </button>
          </>
        )}
      </div>
    </div>
  )
}

/**
 * One microphone for the whole app. The mic in the nav works in every room: the room decides what the
 * speech means (bill, stock, khata, or a question), and anything that changes money or stock still waits
 * for Haan.
 */
export function VoiceProvider({ children }) {
  const { sessionId, showError, showToast } = useApp()
  const { pathname } = useLocation()
  const room = roomFor(pathname)
  const roomRef = useRef(room)
  roomRef.current = room

  const [busy, setBusy] = useState(false)
  const [spokenPtt, setSpokenPtt] = useState(false)
  const [result, setResult] = useState(null)
  const [typeOpen, setTypeOpen] = useState(false)
  const handler = useRef(null)
  const queue = useRef(Promise.resolve())

  const setHandler = useCallback((fn) => {
    handler.current = fn
  }, [])

  const askRoom = useCallback(async (job) => {
    const r = await askShop(job)
    setResult({
      transcript: r.transcript || r.question,
      spoken: r.answer,
      understood: r.understood,
      tables: r.tables?.length ? r.tables : r.table ? [r.table] : [],
      source: r.source,
      latency: r.latency_ms,
      demo: r.tts_source === 'fixture' && r.source === 'fixture',
    })
    speak({ spoken_text: r.spoken_text || r.answer, audio_url: r.audio_url, audio_base64: r.audio_base64 })
  }, [])

  const agentRoom = useCallback(
    async (job, context) => {
      const res = await sendUtterance({ ...job, context, sessionId: `${sessionId}-${context}` })
      setResult({
        transcript: res.transcript,
        spoken: res.spoken_text,
        source: res.source,
        latency: res.latency_ms,
        demo: res.demo_mode && res.source === 'fixture',
        actions: (res.actions || []).filter((a) => a.status === 'proposed'),
      })
      speak(res)
    },
    [sessionId],
  )

  const submit = useCallback(
    (job) => {
      queue.current = queue.current
        .then(async () => {
          setBusy(true)
          try {
            if (handler.current) await handler.current(job)
            else if (roomRef.current.context === 'ask') await askRoom(job)
            else await agentRoom(job, roomRef.current.context)
          } catch (e) {
            showError(e)
          } finally {
            setBusy(false)
            setSpokenPtt(false)
          }
        })
        .catch(() => {})
    },
    [agentRoom, askRoom, showError],
  )

  const rec = useRecorder({
    onAudio: (blob, meta) => {
      if (meta.mode === 'ptt') setSpokenPtt(true)
      submit({ audio: blob, filename: meta.filename })
    },
  })

  useEffect(() => {
    if (rec.error) showToast(rec.error, 'error')
  }, [rec.error, showToast])

  const closeType = useCallback(() => setTypeOpen(false), [])
  const openType = useCallback(() => setTypeOpen(true), [])

  const value = useMemo(
    () => ({ rec, busy, room, submit, setHandler, openType }),
    [rec, busy, room, submit, setHandler, openType],
  )

  return (
    <Ctx.Provider value={value}>
      {children}
      {(rec.recording || spokenPtt) && (
        <Listening rec={rec} thinking={!rec.recording} room={room} onStop={rec.stopPTT} onCancel={rec.cancelPTT} />
      )}
      {busy && !spokenPtt && (
        <div className="absolute left-1/2 -translate-x-1/2 bottom-[104px] z-20 rounded-full bg-ink text-white text-sm px-4 py-2 flex items-center gap-2" role="status">
          <Spinner size={14} /> {tr('Samajh raha hoon')}
        </div>
      )}
      <TypeSheet
        open={typeOpen}
        room={room}
        busy={busy}
        onClose={closeType}
        onSubmit={(text) => {
          closeType()
          submit({ text })
        }}
      />
      <ResultSheet
        result={result}
        onClose={() => setResult(null)}
        onActionDone={(id) =>
          setResult((r) => {
            if (!r) return r
            const actions = r.actions.filter((a) => a.id !== id)
            return actions.length ? { ...r, actions } : null
          })
        }
      />
    </Ctx.Provider>
  )
}
