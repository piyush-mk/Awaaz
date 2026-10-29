import { useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertCircle,
  BookOpen,
  Check,
  CheckCheck,
  Clock,
  ExternalLink,
  FileText,
  Pause,
  Play,
  Receipt,
  Wallet,
} from 'lucide-react'
import { localUrl } from '../../api/sideClient'
import { speakWithFallback } from '../../lib/audio'
import { hhmm, parseBody, upiDetails, waveHeights } from './waUtils'

export const WA = {
  header: '#008069',
  headerDark: '#006652',
  chat: '#EFE7DD',
  mine: '#D9FDD3',
  theirs: '#FFFFFF',
  ink: '#111B21',
  sub: '#4B5A62',
  read: '#2A9BD1',
}

const STATUS_INFO = {
  queued: { label: 'Queued in simulator', Icon: Clock, color: '#667781' },
  sent: { label: 'Sent', Icon: Check, color: '#667781' },
  delivered: { label: 'Delivered', Icon: CheckCheck, color: '#667781' },
  read: { label: 'Read', Icon: CheckCheck, color: WA.read },
  failed: { label: 'Failed', Icon: AlertCircle, color: '#C0261C' },
}

export function Ticks({ status, error }) {
  const info = STATUS_INFO[status]
  if (!info) return null
  const { Icon } = info
  const tip = status === 'failed' && error ? `Failed: ${error}` : info.label
  return (
    <span className="inline-flex items-center" title={tip} aria-label={tip}>
      <Icon size={15} style={{ color: info.color }} aria-hidden="true" />
    </span>
  )
}

function LinkCard({ card }) {
  if (card.kind === 'upi') {
    const d = upiDetails(card.url)
    return (
      <a
        href={card.url}
        className="mt-1 flex min-h-[44px] items-center gap-3 rounded-lg border px-3 py-2 no-underline hover:bg-black/5"
        style={{ borderColor: 'rgba(0,0,0,.12)', color: WA.ink }}
      >
        <Wallet size={22} style={{ color: WA.headerDark }} aria-hidden="true" />
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-semibold">{d.amount ? `UPI se ₹${Number(d.amount).toLocaleString('en-IN')} bharein` : 'UPI payment link'}</span>
          <span className="block truncate text-xs" style={{ color: WA.sub }}>{d.name || d.vpa}</span>
        </span>
        <ExternalLink size={16} aria-hidden="true" />
      </a>
    )
  }
  const isReceipt = card.kind === 'receipt'
  const Icon = isReceipt ? Receipt : BookOpen
  return (
    <a
      href={localUrl(card.url)}
      target="_blank"
      rel="noreferrer"
      className="mt-1 flex min-h-[44px] items-center gap-3 rounded-lg border px-3 py-2 no-underline hover:bg-black/5"
      style={{ borderColor: 'rgba(0,0,0,.12)', color: WA.ink }}
    >
      <Icon size={22} style={{ color: WA.headerDark }} aria-hidden="true" />
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-semibold">{isReceipt ? 'GST receipt' : 'Khata passbook'}</span>
        <span className="block truncate text-xs" style={{ color: WA.sub }}>{card.url.replace(/^https?:\/\//, '')}</span>
      </span>
      <ExternalLink size={16} aria-hidden="true" />
    </a>
  )
}

function VoiceNote({ msg }) {
  const url = localUrl(msg.media_ref)
  const [playing, setPlaying] = useState(false)
  const [progress, setProgress] = useState(0)
  const [duration, setDuration] = useState(0)
  const audioRef = useRef(null)
  const heights = useMemo(() => waveHeights(msg.id), [msg.id])

  useEffect(
    () => () => {
      audioRef.current?.pause()
      try {
        window.speechSynthesis?.cancel()
      } catch {
        /* ignore */
      }
    },
    [],
  )

  const toggle = async () => {
    if (playing) {
      audioRef.current?.pause()
      try {
        window.speechSynthesis?.cancel()
      } catch {
        /* ignore */
      }
      setPlaying(false)
      return
    }
    if (url) {
      if (!audioRef.current) {
        const a = new Audio(url)
        a.onloadedmetadata = () => Number.isFinite(a.duration) && setDuration(a.duration)
        a.ontimeupdate = () => a.duration && setProgress(a.currentTime / a.duration)
        a.onended = () => {
          setPlaying(false)
          setProgress(0)
        }
        a.onerror = () => {
          // file missing or unsupported: read the transcript instead
          audioRef.current = null
          setPlaying(true)
          speakWithFallback(msg.body, null, 'hi').finally(() => setPlaying(false))
        }
        audioRef.current = a
      }
      try {
        await audioRef.current.play()
        setPlaying(true)
      } catch {
        setPlaying(false)
      }
    } else if (msg.body) {
      setPlaying(true)
      await speakWithFallback(msg.body, null, 'hi')
      setPlaying(false)
    }
  }

  const playedBars = Math.round(progress * heights.length)
  return (
    <div className="flex min-w-[220px] items-center gap-2.5 py-1">
      <button
        type="button"
        onClick={toggle}
        className="grid h-11 w-11 shrink-0 place-items-center rounded-full"
        style={{ background: WA.header, color: '#fff' }}
        aria-label={playing ? 'Voice note rok dein' : 'Voice note sunein'}
      >
        {playing ? <Pause size={20} aria-hidden="true" /> : <Play size={20} aria-hidden="true" />}
      </button>
      <div className="flex h-8 flex-1 items-center gap-[2px]" aria-hidden="true">
        {heights.map((h, i) => (
          <span
            key={i}
            style={{
              width: 3,
              height: h,
              borderRadius: 2,
              background: i < playedBars || (playing && !url) ? WA.header : '#8A9AA3',
              opacity: playing && !url ? 0.5 + ((i % 3) * 0.25) : 1,
            }}
          />
        ))}
      </div>
      <span className="w-10 text-right text-xs tabular-nums" style={{ color: WA.sub }}>
        {duration ? `${Math.floor(duration / 60)}:${String(Math.round(duration % 60)).padStart(2, '0')}` : url ? '' : 'TTS'}
      </span>
    </div>
  )
}

/** One chat bubble. `mine` decides side/colour; ticks show on shop-sent (direction out) messages. */
export default function Bubble({ msg, mine }) {
  const { text, cards } = useMemo(() => parseBody(msg.type === 'audio' ? '' : msg.body), [msg.body, msg.type])
  const out = msg.direction === 'out'
  const failed = msg.status === 'failed'
  return (
    <div className={`flex ${mine ? 'justify-end' : 'justify-start'}`}>
      <div
        className="max-w-[86%] rounded-lg px-2.5 py-1.5 shadow-sm"
        style={{ background: mine ? WA.mine : WA.theirs, color: WA.ink, borderTopRightRadius: mine ? 2 : undefined, borderTopLeftRadius: mine ? undefined : 2 }}
      >
        {msg.type === 'audio' && (
          <>
            <VoiceNote msg={msg} />
            {msg.body && (
              <div className="mt-0.5 border-t pt-1 text-sm italic" style={{ borderColor: 'rgba(0,0,0,.1)', color: WA.sub }}>
                <span className="not-italic font-semibold">Transcript: </span>
                {msg.body}
              </div>
            )}
          </>
        )}

        {msg.type === 'image' && msg.media_ref && (
          <a href={localUrl(msg.media_ref)} target="_blank" rel="noreferrer" className="block">
            <img
              src={localUrl(msg.media_ref)}
              alt="Photo bheji gayi"
              className="mb-1 max-h-72 w-full rounded-md object-cover"
              loading="lazy"
            />
          </a>
        )}
        {(msg.type === 'doc' || msg.type === 'document') && (
          <div className="mb-1 flex items-center gap-2 rounded-md bg-black/5 px-2 py-2 text-sm">
            <FileText size={20} aria-hidden="true" />
            <span className="truncate">{(msg.media_ref || 'document').split('/').pop()}</span>
          </div>
        )}

        {msg.type !== 'audio' && text && (
          <div className="whitespace-pre-wrap break-words text-[15px] leading-snug" lang="hi">
            {text}
          </div>
        )}
        {cards.map((c) => (
          <LinkCard key={c.url} card={c} />
        ))}

        <div className="mt-0.5 flex items-center justify-end gap-1.5 text-[11px]" style={{ color: WA.sub }}>
          {msg.channel === 'wa' && <span title="Delivered through Meta WhatsApp Cloud API">Meta</span>}
          <span className="tabular-nums">{hhmm(msg.created_at)}</span>
          {out && <Ticks status={msg.status} error={msg.error} />}
        </div>
        {failed && (
          <div
            className="mt-1 flex items-start gap-1.5 rounded px-2 py-1 text-xs font-medium"
            style={{ background: '#FDE7E5', color: '#8A1B12' }}
            role="alert"
          >
            <AlertCircle size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
            <span>{msg.error || 'Message deliver nahi hua (simulator mein rakha gaya)'}</span>
          </div>
        )}
      </div>
    </div>
  )
}
