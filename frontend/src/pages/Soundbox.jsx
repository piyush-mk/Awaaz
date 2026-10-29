import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { BadgeIndianRupee, Maximize2, Mic, Send, Trash2, Volume2, VolumeX, Wifi, WifiOff } from 'lucide-react'
import FullPage, { CYAN, INK, ORANGE, SOFT } from '../components/sb/FullPage'
import useMic from '../components/sb/useMic'
import useSoundbox from '../components/sb/useSoundbox'
import {
  Banners,
  BillView,
  BriefView,
  IdleView,
  PaidView,
  ProposalCard,
  QrView,
} from '../components/sb/SoundboxViews'
import useSpeech from '../hooks/useSpeech'
import { api, getAdminStatus, sendUtterance, sessionFromUrl, simulatePayment } from '../api/sideClient'

const CSS = `
@keyframes sbBar{0%,100%{transform:scaleY(.16)}50%{transform:scaleY(1)}}
.sb-bar{animation:sbBar 1s ease-in-out infinite;transform-origin:center}
@keyframes sbPop{0%{transform:scale(.4);opacity:0}70%{transform:scale(1.12)}100%{transform:scale(1);opacity:1}}
.sb-pop{animation:sbPop .45s ease-out both}
@keyframes sbSlide{from{transform:translateY(8px);opacity:0}to{transform:none;opacity:1}}
.sb-slide{animation:sbSlide .25s ease-out both}
@keyframes sbRing{0%{box-shadow:0 0 0 0 rgba(255,138,31,.6)}100%{box-shadow:0 0 0 38px rgba(255,138,31,0)}}
.sb-ring{animation:sbRing 1.2s ease-out infinite}
@keyframes sbBreath{0%,100%{box-shadow:0 0 0 0 rgba(0,185,245,.45)}50%{box-shadow:0 0 0 22px rgba(0,185,245,0)}}
.sb-breath{animation:sbBreath 2.6s ease-in-out infinite}
@media (prefers-reduced-motion:reduce){.sb-bar,.sb-ring,.sb-pop,.sb-slide,.sb-breath{animation:none}.sb-bar{transform:scaleY(.6)}}
`

const PHRASES = [
  'do maggi ek surf excel chaar colgate',
  'bhaiya do maggi ek surf aur bees rupaye ki cheeni',
  'verma ji ke khate mein paanch sau',
  'teen sau cash diya do sau paytm baaki khate mein',
  'bas kitna hua',
  'kurkure nahi hai',
]

function Clock() {
  const [t, setT] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setT(new Date()), 20000)
    return () => clearInterval(id)
  }, [])
  return <span className="tabular-nums">{t.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false })}</span>
}

export default function Soundbox() {
  const params = useMemo(() => new URLSearchParams(window.location.search), [])
  const kiosk = params.get('kiosk') === '1'
  const sessionId = sessionFromUrl() || 'default'

  const speech = useSpeech()
  const sb = useSoundbox({ speak: speech.speak, cancelSpeech: speech.cancel })
  const [store, setStore] = useState('Ramesh General Store')
  const [busy, setBusy] = useState(false)
  const [typed, setTyped] = useState('')
  const [sendingProposal, setSendingProposal] = useState(false)
  const unlockBtn = useRef(null)

  useEffect(() => {
    getAdminStatus()
      .then((s) => s.store && setStore(s.store))
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (!speech.unlocked) unlockBtn.current?.focus()
  }, [speech.unlocked])

  const fail = useCallback((e) => sb.banner(e.message || 'Request fail ho gaya', 'error'), [sb])

  const submit = useCallback(
    async (args) => {
      setBusy(true)
      speech.cancel()
      try {
        await sendUtterance({ sessionId, ...args })
      } catch (e) {
        fail(e)
      } finally {
        setBusy(false)
      }
    },
    [sessionId, speech, fail],
  )

  const mic = useMic({ onRecorded: (blob, filename) => submit({ audio: blob, filename }) })

  const orderId = sb.checkout?.order_id && !sb.checkout.complete ? sb.checkout.order_id : null

  const payNow = async () => {
    if (!orderId) return
    try {
      await simulatePayment(orderId)
    } catch (e) {
      fail(e)
    }
  }

  const newBill = async () => {
    try {
      await api(`/api/cart/${encodeURIComponent(sessionId)}`, { method: 'DELETE' })
      sb.goIdle()
    } catch (e) {
      fail(e)
    }
  }

  const resolveProposal = async (verb) => {
    if (!sb.proposal) return
    setSendingProposal(true)
    try {
      await api(`/api/actions/${sb.proposal.id}/${verb}`, { method: 'POST' })
      sb.dismissProposal()
    } catch (e) {
      fail(e)
    } finally {
      setSendingProposal(false)
    }
  }

  const sendTyped = (e) => {
    e.preventDefault()
    const text = typed.trim()
    if (!text) return
    setTyped('')
    submit({ text })
  }

  const recording = mic.recording
  const { mode } = sb
  const status = recording ? 'RECORDING' : busy ? 'PROCESSING' : speech.speaking ? 'SPEAKING' : sb.connected ? 'LISTENING' : 'OFFLINE'

  return (
    <FullPage background={SOFT}>
      <style>{CSS}</style>

      {!speech.unlocked && (
        <div className="fixed inset-0 z-50 grid place-items-center" style={{ background: 'rgba(14,27,51,.82)' }}>
          <button
            ref={unlockBtn}
            type="button"
            onClick={speech.enable}
            className="flex min-h-[64px] flex-col items-center gap-1 rounded-3xl px-10 py-6 text-center shadow-2xl"
            style={{ background: CYAN, color: INK }}
          >
            <Volume2 size={44} aria-hidden="true" />
            <span className="text-3xl font-bold">Tap to enable sound</span>
            <span className="text-xl font-semibold" lang="hi">आवाज़ चालू करने के लिए टैप करें</span>
          </button>
        </div>
      )}

      <div className="mx-auto flex min-h-full w-full max-w-[1160px] flex-col items-center justify-center gap-3 px-4 py-4">
        {!kiosk && (
          <header className="flex w-full items-center justify-between gap-3">
            <div>
              <div className="text-xl font-bold">Awaaz Soundbox</div>
              <div className="text-sm" style={{ color: '#4A5873' }}>
                Emulator · session <code>{sessionId}</code> · events: {sb.connected ? 'connected' : 'reconnecting'}
              </div>
            </div>
            <nav className="flex flex-wrap items-center gap-2 text-sm font-semibold">
              <Link className="min-h-[44px] inline-flex items-center rounded-lg px-3 hover:bg-white" to="/app">Phone app</Link>
              <Link className="min-h-[44px] inline-flex items-center rounded-lg px-3 hover:bg-white" to="/wa">WhatsApp</Link>
              <Link className="min-h-[44px] inline-flex items-center rounded-lg px-3 hover:bg-white" to="/status">Status</Link>
              <a
                className="inline-flex min-h-[44px] items-center gap-1.5 rounded-lg px-3 hover:bg-white"
                href={`${window.location.pathname}?kiosk=1${sessionFromUrl() ? `&session=${encodeURIComponent(sessionFromUrl())}` : ''}`}
              >
                <Maximize2 size={16} aria-hidden="true" /> Kiosk
              </a>
            </nav>
          </header>
        )}

        {/* device */}
        <div
          className="w-full rounded-[44px] p-4 sm:p-5"
          style={{
            background: 'linear-gradient(160deg,#1B2A4A 0%,#0E1B33 55%,#0A1325 100%)',
            boxShadow: '0 30px 60px -20px rgba(14,27,51,.55), inset 0 1px 0 rgba(255,255,255,.08)',
          }}
        >
          <div className="mb-3 flex h-11 items-center justify-between rounded-2xl bg-black px-4 text-sm text-white/90">
            <div className="flex items-center gap-2 font-semibold tracking-[0.16em]">
              <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: sb.connected ? '#34C759' : '#FF6B5F' }} aria-hidden="true" />
              PAYTM AI SOUNDBOX
            </div>
            <div className="hidden truncate px-3 font-medium sm:block">{store}</div>
            <div className="flex items-center gap-3">
              <span className="hidden text-xs font-semibold tracking-wider text-white/70 md:inline">{status}</span>
              {sb.connected ? <Wifi size={18} aria-label="Connected" /> : <WifiOff size={18} aria-label="Offline" />}
              <button
                type="button"
                onClick={() => speech.setMuted(!speech.muted)}
                className="grid h-8 w-8 place-items-center rounded-full hover:bg-white/15"
                aria-label={speech.muted ? 'Awaaz chalu karein' : 'Awaaz band karein'}
                aria-pressed={speech.muted}
              >
                {speech.muted ? <VolumeX size={18} /> : <Volume2 size={18} />}
              </button>
              <Clock />
            </div>
          </div>

          <div className="flex flex-col gap-4 lg:flex-row">
            <div className="flex min-w-0 flex-1 flex-col">
              {sb.proposal && (
                <ProposalCard
                  proposal={sb.proposal}
                  busy={sendingProposal}
                  onConfirm={() => resolveProposal('confirm')}
                  onCancel={() => resolveProposal('cancel')}
                />
              )}
              <div
                className="relative min-h-[420px] flex-1 overflow-hidden rounded-[28px] bg-white p-5 sm:p-7"
                style={{ height: kiosk ? 'min(76vh,720px)' : 'min(57vh,540px)' }}
              >
                <div key={mode} className="sb-slide h-full">
                  {mode === 'idle' && (
                    <IdleView
                      store={store}
                      connected={sb.connected}
                      tally={sb.tally}
                      listening={recording}
                      processing={busy}
                      heard={sb.heard}
                    />
                  )}
                  {mode === 'bill' && <BillView cart={sb.cart} heard={sb.heard} />}
                  {mode === 'qr' && sb.checkout && <QrView checkout={sb.checkout} heard={sb.heard} />}
                  {mode === 'paid' && sb.paid && <PaidView paid={sb.paid} />}
                  {mode === 'brief' && sb.brief && <BriefView brief={sb.brief} onClose={sb.goIdle} />}
                </div>
              </div>
              <div className="mt-3 min-h-[40px]">
                <Banners banners={sb.banners} />
              </div>
            </div>

            {/* the Paytm button */}
            <div className="flex shrink-0 flex-row items-center justify-center gap-5 lg:w-[220px] lg:flex-col lg:gap-4">
              <button
                type="button"
                onPointerDown={mic.pressStart}
                onPointerUp={mic.pressEnd}
                onPointerCancel={mic.pressEnd}
                onPointerLeave={mic.pressEnd}
                onClick={mic.keyboardToggle}
                aria-pressed={recording}
                aria-label={recording ? 'Recording band karke bhejein' : 'Dabakar bolein'}
                className={`grid h-[168px] w-[168px] select-none place-items-center rounded-full outline-none focus-visible:ring-4 focus-visible:ring-white ${
                  recording ? 'sb-ring' : 'sb-breath'
                }`}
                style={{
                  background: recording ? ORANGE : CYAN,
                  color: INK,
                  touchAction: 'none',
                  boxShadow: 'inset 0 -10px 24px rgba(0,0,0,.18), inset 0 6px 14px rgba(255,255,255,.35)',
                }}
              >
                <span className="flex flex-col items-center">
                  <Mic size={64} strokeWidth={2.4} aria-hidden="true" />
                  <span className="mt-1 text-lg font-bold tabular-nums">{recording ? `${mic.seconds}s` : 'BOLO'}</span>
                </span>
              </button>
              <div className="flex flex-col items-center gap-2 text-center">
                <div className="text-lg font-bold text-white" lang="hi">
                  {recording ? 'छोड़ें या टैप करें' : 'दबाकर बोलिए'}
                </div>
                <div className="text-sm text-white/80">{recording ? 'Release / tap to send' : 'Hold to talk, or tap'}</div>
                {mic.error && <div className="max-w-[200px] text-sm font-semibold" style={{ color: '#FFB4A8' }} role="alert">{mic.error}</div>}
                {!kiosk && (
                  <button
                    type="button"
                    onClick={payNow}
                    disabled={!orderId}
                    className="mt-1 inline-flex min-h-[48px] items-center gap-2 rounded-xl border-2 px-4 text-base font-bold text-white transition-colors enabled:hover:bg-white/15 disabled:opacity-40"
                    style={{ borderColor: 'rgba(255,255,255,.55)' }}
                  >
                    <BadgeIndianRupee size={20} aria-hidden="true" /> Payment aa gaya
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>

        {!kiosk && (
          <section className="w-full" aria-label="Typed utterance">
            <form onSubmit={sendTyped} className="flex w-full gap-2">
              <label htmlFor="sb-typed" className="sr-only">Type what the customer says</label>
              <input
                id="sb-typed"
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
                placeholder="Type like speech: do maggi ek surf excel chaar colgate"
                className="min-h-[48px] flex-1 rounded-xl border-2 bg-white px-4 text-lg"
                style={{ borderColor: '#B8C2D1' }}
                autoComplete="off"
              />
              <button
                type="submit"
                disabled={busy || !typed.trim()}
                className="inline-flex min-h-[48px] items-center gap-2 rounded-xl px-5 text-lg font-bold disabled:opacity-50"
                style={{ background: INK, color: '#fff' }}
              >
                <Send size={18} aria-hidden="true" /> Bhejo
              </button>
              <button
                type="button"
                onClick={newBill}
                className="inline-flex min-h-[48px] items-center gap-2 rounded-xl border-2 px-4 text-base font-semibold hover:bg-white"
                style={{ borderColor: '#B8C2D1' }}
                title="Cart saaf karke naya bill"
              >
                <Trash2 size={18} aria-hidden="true" /> Naya bill
              </button>
            </form>
            <div className="mt-2 flex flex-wrap gap-2">
              {PHRASES.map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => submit({ text: p })}
                  disabled={busy}
                  className="min-h-[44px] rounded-full border px-4 text-base font-medium hover:bg-white disabled:opacity-50"
                  style={{ borderColor: '#B8C2D1' }}
                >
                  {p}
                </button>
              ))}
            </div>
          </section>
        )}
      </div>
    </FullPage>
  )
}
