import { useState } from 'react'
import { Loader2, Radio, Volume2, CalendarClock, Sparkles } from 'lucide-react'
import SourceChip from '../SourceChip'
import { Btn, Chip, ErrorBox, Skeleton } from '../ui'
import { useApp, useStoreEvent } from '../AppContext'
import useLoad from '../../../lib/useLoad'
import { getBrief, playBrief } from '../../../api/client'
import { speak, stopSpeaking } from '../../../lib/audio'
import { inr, num } from '../../../lib/format'

export default function BriefCard() {
  const { showToast, showError } = useApp()
  const { data: b, loading, error, reload } = useLoad(() => getBrief(), [])
  const [playing, setPlaying] = useState(false)
  const [sending, setSending] = useState(false)

  useStoreEvent('brief_ready', () => {})

  const play = async () => {
    if (playing) {
      stopSpeaking()
      setPlaying(false)
      return
    }
    setPlaying(true)
    await speak(b)
    setPlaying(false)
  }

  const onSoundbox = async () => {
    setSending(true)
    try {
      await playBrief()
      showToast('Soundbox par bhej diya')
    } catch (e) {
      showError(e)
    } finally {
      setSending(false)
    }
  }

  if (loading && !b) return <Skeleton className="h-64 w-full" />
  if (error) return <ErrorBox error={error} onRetry={reload} />
  if (!b) return null

  const f = b.facts || {}
  const fest = f.festival
  return (
    <div className="rounded-2xl bg-ink text-white p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-paytm-blue">Subah ki salaah</div>
          <div className="font-hindi text-xl font-bold">{f.weekday}, {b.date}</div>
        </div>
        <SourceChip source={b.source} latency={b.latency_ms} demo={b.tts_source === 'fixture' && b.source === 'fixture'} />
      </div>

      <ul className="mt-3 space-y-2">
        {(b.sentences?.length ? b.sentences : [b.text]).map((s, i) => (
          <li key={i} className="font-hindi text-lg leading-snug">{s}</li>
        ))}
      </ul>

      {fest && (
        <div className="mt-3 rounded-xl bg-white/10 p-3">
          <div className="flex items-center gap-2">
            <CalendarClock size={18} className="text-accent" />
            <b className="font-hindi text-lg">{fest.name}</b>
            <Chip tone="orange" className="ml-auto">{fest.days_away} din baaki</Chip>
          </div>
          {fest.at_risk?.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {fest.at_risk.map((p) => (
                <span key={p.product_id} className="rounded-full bg-accent/20 text-accent px-2.5 py-0.5 text-xs font-semibold">
                  {p.short_name}: {num(p.stock)} {p.unit} . {p.multiplier}x
                </span>
              ))}
            </div>
          )}
          {fest.last_year_note && <p className="mt-2 text-xs text-white/60">Pichhle saal: {fest.last_year_note}</p>}
        </div>
      )}

      <div className="mt-3 grid grid-cols-3 gap-2 text-center">
        <div className="rounded-xl bg-white/10 p-2">
          <div className="text-[10px] text-white/60">Kal ki sale</div>
          <div className="font-bold tabular">{inr(f.yesterday?.total)}</div>
        </div>
        <div className="rounded-xl bg-white/10 p-2">
          <div className="text-[10px] text-white/60">Udhaar baaki</div>
          <div className="font-bold tabular">{inr(f.udhaar?.total_outstanding)}</div>
        </div>
        <div className="rounded-xl bg-white/10 p-2">
          <div className="text-[10px] text-white/60">Expire hoga</div>
          <div className="font-bold tabular">{f.expiring?.length || 0} item</div>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3">
        <Btn variant="primary" icon={playing ? Loader2 : Volume2} onClick={play}>{playing ? 'Ruko' : 'Sunein'}</Btn>
        <Btn variant="accent" icon={Radio} busy={sending} onClick={onSoundbox}>Soundbox par</Btn>
      </div>
      <button onClick={() => reload()} className="mt-2 w-full min-h-[44px] flex items-center justify-center gap-1 text-xs text-white/60">
        <Sparkles size={14} /> {b.tts_source ? `awaaz: ${b.tts_source === 'fixture' ? 'browser voice' : b.tts_source}` : ''} . naya brief
      </button>
    </div>
  )
}
