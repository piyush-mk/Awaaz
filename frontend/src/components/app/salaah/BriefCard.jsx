import { useState } from 'react'
import { Loader2, Radio, Volume2, CalendarClock, ChevronDown, RefreshCw } from 'lucide-react'
import SourceChip from '../SourceChip'
import { Btn, Card, ErrorBox, Rows, Skeleton } from '../ui'
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
  const [reading, setReading] = useState(false)

  useStoreEvent('demo_reset', () => reload({ quiet: true }))

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

  if (loading && !b) {
    return (
      <div>
        <div className="flex items-center gap-2 text-[15px] text-ink-3 mb-3"><Loader2 size={16} className="animate-spin" /> Ban rahi hai</div>
        <Skeleton className="h-48 w-full" />
      </div>
    )
  }
  if (error) return <ErrorBox error={error} onRetry={reload} />
  if (!b) return null

  const f = b.facts || {}
  const fest = f.festival
  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <Btn size="lg" variant="navy" icon={playing ? Loader2 : Volume2} className="flex-1" onClick={play}>{playing ? 'Ruko' : 'Sunein'}</Btn>
        <Btn size="lg" variant="ghost" icon={Radio} busy={sending} aria-label="Soundbox par" className="!px-4" onClick={onSoundbox} />
        <Btn size="lg" variant="ghost" icon={RefreshCw} aria-label="Naya brief" className="!px-4" onClick={() => reload()} />
      </div>
      <SourceChip source={b.source} latency={b.latency_ms} demo={b.tts_source === 'fixture' && b.source === 'fixture'} />

      {fest && (
        <Card>
          <div className="flex items-center gap-2">
            <CalendarClock size={18} className="text-paytm-orange-dark" />
            <b className="font-hindi text-lg font-semibold">{fest.name}</b>
            <span className="ml-auto text-sm font-medium text-orange-800">{fest.days_away} din</span>
          </div>
          {fest.at_risk?.length > 0 && (
            <ul className="mt-2 space-y-1">
              {fest.at_risk.map((p) => (
                <li key={p.product_id} className="flex justify-between tabular">
                  <span>{p.short_name}</span>
                  <span className="text-ink-3">{num(p.stock)} {p.unit} bacha</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      <Rows>
        <li className="flex justify-between px-4 py-3"><span>Kal ki sale</span><b className="font-semibold tabular">{inr(f.yesterday?.total)}</b></li>
        <li className="flex justify-between px-4 py-3"><span>Udhaar baaki</span><b className="font-semibold tabular">{inr(f.udhaar?.total_outstanding)}</b></li>
        <li className="flex justify-between px-4 py-3"><span>Expiry paas</span><b className="font-semibold tabular">{f.expiring?.length || 0}</b></li>
      </Rows>

      <button onClick={() => setReading((v) => !v)} aria-expanded={reading} className="w-full min-h-[44px] flex items-center justify-center gap-1 text-sm font-medium text-ink-3">
        Padhein <ChevronDown size={16} className={reading ? 'rotate-180' : ''} />
      </button>
      {reading && (
        <ul className="space-y-2">
          {(b.sentences?.length ? b.sentences : [b.text]).map((t, i) => <li key={i} className="font-hindi text-base leading-snug">{t}</li>)}
        </ul>
      )}
    </div>
  )
}
