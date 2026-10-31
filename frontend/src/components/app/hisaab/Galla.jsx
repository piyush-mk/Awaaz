import { useState } from 'react'
import { Calculator, Volume2 } from 'lucide-react'
import PhotoButton from '../PhotoButton'
import ConfirmCard from '../ConfirmCard'
import SourceChip from '../SourceChip'
import { Btn, Card, Chip, ErrorBox, Hero, SkeletonList } from '../ui'
import { useApp, useStoreEvent } from '../AppContext'
import useLoad from '../../../lib/useLoad'
import { closeGalla, getGallaExpected, scanGalla } from '../../../api/client'
import { speak } from '../../../lib/audio'
import { inr } from '../../../lib/format'
import { tr } from '../../../lib/i18n'

const DENOMS = ['2000', '500', '200', '100', '50', '20', '10']

function difference(expected, counted) {
  const d = Math.round((counted - expected) * 100) / 100
  if (d === 0) return { d, tone: 'green', text: `${inr(expected)} hona chahiye tha, ${inr(counted)} hai. Bilkul sahi.` }
  return { d, tone: d < 0 ? 'red' : 'yellow', text: `${inr(expected)} hona chahiye tha, ${inr(counted)} hai. ${inr(Math.abs(d))} ${d < 0 ? tr('kam') : tr('zyada')}.` }
}

/** Galla closing: expected cash, photo count, editable denominations, close the day. */
export default function Galla() {
  const { showError } = useApp()
  const { data: exp, loading, error, reload } = useLoad(() => getGallaExpected(), [])
  const [scan, setScan] = useState(null)
  const [counts, setCounts] = useState(null) // { '500': 8, ..., coins: 0 }
  const [busy, setBusy] = useState(false)
  const [closing, setClosing] = useState(false)
  const [result, setResult] = useState(null)

  useStoreEvent('payment_received', () => reload({ quiet: true }))
  useStoreEvent('galla_closed', () => reload({ quiet: true }))
  useStoreEvent('checkout', () => reload({ quiet: true }))
  useStoreEvent('demo_reset', () => reload({ quiet: true }))

  const startManual = () => {
    setScan(null)
    setCounts(Object.fromEntries([...DENOMS.map((d) => [d, 0]), ['coins', 0]]))
  }

  const doScan = async (files) => {
    setBusy(true)
    try {
      const res = await scanGalla(files[0])
      setScan(res)
      setCounts({ ...res.denominations })
      speak({ spoken_text: res.message_hi })
    } catch (e) {
      showError(e)
    } finally {
      setBusy(false)
    }
  }

  const counted = counts
    ? DENOMS.reduce((s, d) => s + Number(d) * (Number(counts[d]) || 0), 0) + (Number(counts.coins) || 0)
    : 0
  const expected = exp?.expected ?? scan?.expected ?? 0
  const diff = difference(expected, counted)

  const close = async () => {
    setClosing(true)
    try {
      const res = await closeGalla(Object.fromEntries(Object.entries(counts).map(([k, v]) => [k, Number(v) || 0])))
      setResult(res)
      speak({ spoken_text: res.message_hi, audio_base64: res.speech?.audio_base64, audio_url: res.speech?.url })
      reload({ quiet: true })
    } catch (e) {
      showError(e)
    } finally {
      setClosing(false)
    }
  }

  if (loading && !exp) return <SkeletonList rows={2} className="h-24" />
  if (error) return <ErrorBox error={error} onRetry={reload} />

  if (result) {
    const t = difference(result.expected, result.counted)
    return (
      <Card className="text-center">
        <div className={`font-hindi text-3xl font-semibold ${t.tone === 'green' ? 'text-green-800' : t.tone === 'red' ? 'text-red-700' : 'text-yellow-900'}`}>{t.d === 0 ? tr('Bilkul sahi') : tr(t.d < 0 ? '{amt} kam' : '{amt} zyada', { amt: inr(Math.abs(t.d)) })}</div>
        <button onClick={() => speak({ spoken_text: result.message_hi, audio_base64: result.speech?.audio_base64 })} className="mt-2 inline-flex items-center gap-1 min-h-[44px] text-paytm-blue-dark font-semibold">
          <Volume2 size={18} /> {tr('Sunein')}
        </button>
        <div className="mt-2 flex justify-center"><SourceChip source={result.source} latency={result.latency_ms} demo={result.demo_mode} /></div>
        <Btn variant="navy" className="w-full mt-4" onClick={() => { setResult(null); setCounts(null); setScan(null) }}>{tr('Theek hai')}</Btn>
      </Card>
    )
  }

  return (
    <div className="space-y-3">
      <div>
        <Hero value={inr(exp.expected)} sub={tr('Galle mein hona chahiye')} />
        {exp.already_closed && (
          <div className="mt-2 text-[15px] font-medium text-green-800">{tr('Aaj band ho chuka')}</div>
        )}
      </div>

      {!counts && (
        <div className="grid grid-cols-2 gap-3">
          <PhotoButton variant="blue" label={tr('Photo')} busy={busy} onFiles={doScan} />
          <Btn variant="ghost" icon={Calculator} onClick={startManual}>{tr('Ginein')}</Btn>
        </div>
      )}

      {counts && (
        <>
          {scan && (
            <div className="flex items-center justify-between px-1">
              <span />
              <SourceChip source={scan.source} latency={scan.latency_ms} demo={scan.demo_mode} />
            </div>
          )}
          <div className="divide-y divide-line">
            {DENOMS.map((d) => {
              const conf = scan?.denomination_confidence?.[d]
              const low = conf != null && conf < 0.8
              return (
                <div key={d} className={`flex items-center gap-3 py-2 ${low ? 'bg-yellow-50' : ''}`}>
                  <div className="w-16 font-bold tabular text-lg">{inr(d)}</div>
                  <span className="text-ink-3">x</span>
                  <input
                    inputMode="numeric"
                    value={counts[d]}
                    onChange={(e) => setCounts((c) => ({ ...c, [d]: e.target.value === '' ? '' : Number(e.target.value) }))}
                    className="w-20 min-h-[48px] rounded-lg border border-line text-center text-lg font-bold tabular"
                  />
                  <div className="flex-1 text-right tabular font-semibold">{inr(Number(d) * (Number(counts[d]) || 0))}</div>
                  {low && <Chip tone="yellow">{Math.round(conf * 100)}%</Chip>}
                </div>
              )
            })}
            <div className="flex items-center gap-3 py-2">
              <div className="w-16 font-bold">{tr('Sikke')}</div>
              <span className="text-ink-3">=</span>
              <input
                inputMode="decimal"
                value={counts.coins}
                onChange={(e) => setCounts((c) => ({ ...c, coins: e.target.value === '' ? '' : Number(e.target.value) }))}
                className="w-20 min-h-[48px] rounded-lg border border-line text-center text-lg font-bold tabular"
              />
              <div className="flex-1 text-right tabular font-semibold">{inr(Number(counts.coins) || 0)}</div>
            </div>
          </div>
          {scan?.low_confidence_flags?.map((f) => (
            <div key={f.denomination} className="rounded-xl bg-yellow-50 px-3 py-2 text-sm font-medium text-yellow-900">{f.message}</div>
          ))}

          <div className={`rounded-2xl p-4 text-center ${diff.tone === 'green' ? 'bg-green-50' : diff.tone === 'red' ? 'bg-red-50' : 'bg-yellow-50'}`}>
            <div className="text-xs text-ink-3">{tr('Gina hua')}</div>
            <div className="text-3xl font-bold tabular">{inr(counted)}</div>
            <div className={`font-hindi text-lg font-bold mt-1 ${diff.tone === 'green' ? 'text-green-800' : diff.tone === 'red' ? 'text-red-700' : 'text-yellow-900'}`}>{diff.d === 0 ? tr('Bilkul sahi') : tr(diff.d < 0 ? '{amt} kam' : '{amt} zyada', { amt: inr(Math.abs(diff.d)) })}</div>
          </div>

          <ConfirmCard question={tr('Galla band karun?')} busy={closing} onYes={close} onNo={() => { setCounts(null); setScan(null) }} yesLabel={tr('Haan')} tone="orange" />
        </>
      )}
    </div>
  )
}
