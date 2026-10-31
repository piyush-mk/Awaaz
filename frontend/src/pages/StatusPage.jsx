import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertTriangle,
  CheckCircle2,
  Database,
  ExternalLink,
  MessageCircle,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  XCircle,
  Zap,
} from 'lucide-react'
import FullPage, { CYAN, INK, SOFT } from '../components/sb/FullPage'
import { getAdminHealth, getAdminStatus, getChecklist, resetDemo } from '../api/sideClient'

// state -> label, background, text colour (text kept >= 4.5:1 on its background)
const STATES = {
  live: { label: 'LIVE', bg: '#DDF5E4', fg: '#0F5A2A', dot: '#1E9E4A' },
  fallback: { label: 'FALLBACK', bg: '#FFF1CC', fg: '#5C4300', dot: '#E0A100' },
  fixture: { label: 'FIXTURE', bg: '#E1F3FB', fg: '#0B4A66', dot: '#00A3DB' },
  missing_key: { label: 'MISSING KEY', bg: '#FFE0DE', fg: '#8C1A12', dot: '#E5392D' },
}

const NAMES = {
  sarvam_stt: ['Sarvam STT', 'Saaras: speech to text'],
  sarvam_tts: ['Sarvam TTS', 'Bulbul: text to speech'],
  sarvam_chat: ['Sarvam Chat', 'LLM: cart tools, brief, munim'],
  sarvam_vision: ['Sarvam Vision', 'Bills, parchi, khata page, galla'],
  openrouter_chat: ['OpenRouter, text and tools', 'Backup when Sarvam chat fails'],
  openrouter_vision: ['OpenRouter, vision', 'Backup when Sarvam vision fails'],
  whatsapp: ['WhatsApp', 'Meta Cloud API or simulator'],
  db: ['Database', 'SQLite'],
}
const ORDER = ['sarvam_stt', 'sarvam_tts', 'sarvam_chat', 'sarvam_vision', 'openrouter_chat', 'openrouter_vision', 'whatsapp', 'db']

const DOCS_URL = typeof window !== 'undefined' && window.location.port === '5173' ? `http://${window.location.hostname}:8000/docs` : '/docs'

function StateBadge({ state }) {
  const s = STATES[state] || { label: String(state || '?').toUpperCase(), bg: '#E5E9EF', fg: '#27364D', dot: '#6B7A90' }
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-bold tracking-wide" style={{ background: s.bg, color: s.fg }}>
      <span className="inline-block h-2 w-2 rounded-full" style={{ background: s.dot }} aria-hidden="true" />
      {s.label}
    </span>
  )
}

function ProviderCard({ id, svc, pinged }) {
  const [title, sub] = NAMES[id] || [id, '']
  const s = STATES[svc.state] || {}
  return (
    <article className="flex flex-col rounded-2xl bg-white p-4 shadow-sm" style={{ borderTop: `5px solid ${s.dot || '#6B7A90'}` }}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="text-lg font-bold leading-tight">{title}</h3>
          <p className="text-sm" style={{ color: '#4A5873' }}>{sub}</p>
        </div>
        <StateBadge state={svc.state} />
      </div>
      <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        <dt style={{ color: '#4A5873' }}>Serving</dt>
        <dd className="font-semibold">{svc.effective}</dd>
        <dt style={{ color: '#4A5873' }}>Key / config</dt>
        <dd className="font-semibold">{svc.configured ? 'set' : 'not set'}</dd>
        {svc.model && (
          <>
            <dt style={{ color: '#4A5873' }}>Model</dt>
            <dd className="truncate font-mono text-[13px]">{svc.model}</dd>
          </>
        )}
        {typeof svc.credits_remaining === 'number' && (
          <>
            <dt style={{ color: '#4A5873' }}>Credit</dt>
            <dd className="font-semibold tabular-nums">{`$${svc.credits_remaining.toFixed(2)} credit left`}</dd>
          </>
        )}
        <dt style={{ color: '#4A5873' }}>Last latency</dt>
        <dd className="font-semibold tabular-nums">{svc.last_latency_ms != null ? `${svc.last_latency_ms} ms` : pinged ? 'n/a' : 'not pinged'}</dd>
        {svc.last_checked && (
          <>
            <dt style={{ color: '#4A5873' }}>Checked</dt>
            <dd className="tabular-nums">{String(svc.last_checked).replace('T', ' ')}</dd>
          </>
        )}
      </dl>
      {svc.last_error && (
        <div className="mt-3 flex items-start gap-2 rounded-lg px-3 py-2 text-sm font-medium" style={{ background: '#FFE0DE', color: '#7A150E' }}>
          <AlertTriangle size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
          <span className="break-words">{svc.last_error}</span>
        </div>
      )}
    </article>
  )
}

function Stat({ label, value, hint }) {
  return (
    <div className="rounded-2xl bg-white p-4 shadow-sm">
      <div className="text-xs font-semibold uppercase tracking-wider" style={{ color: '#4A5873' }}>{label}</div>
      <div className="mt-1 break-words text-2xl font-bold leading-tight">{value}</div>
      {hint && <div className="mt-1 text-sm" style={{ color: '#4A5873' }}>{hint}</div>}
    </div>
  )
}

function ConfirmDialog({ open, title, body, confirmLabel, busy, onConfirm, onCancel }) {
  const ref = useRef(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (open && !el.open) el.showModal?.()
    if (!open && el.open) el.close?.()
  }, [open])
  return (
    <dialog
      ref={ref}
      onCancel={(e) => {
        e.preventDefault()
        onCancel()
      }}
      className="w-[min(92vw,460px)] rounded-2xl p-0 shadow-2xl backdrop:bg-black/50"
    >
      <div className="p-6">
        <h2 className="text-xl font-bold">{title}</h2>
        <p className="mt-2 text-base" style={{ color: '#33415C' }}>{body}</p>
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" onClick={onCancel} className="min-h-[44px] rounded-xl border-2 px-5 text-base font-semibold" style={{ borderColor: '#B8C2D1' }}>
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className="min-h-[44px] rounded-xl px-5 text-base font-bold text-white disabled:opacity-60"
            style={{ background: '#B3261E' }}
          >
            {busy ? 'Ho raha hai...' : confirmLabel}
          </button>
        </div>
      </div>
    </dialog>
  )
}

export default function StatusPage() {
  const [status, setStatus] = useState(null)
  const [health, setHealth] = useState(null)
  const [checklist, setChecklist] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [liveBusy, setLiveBusy] = useState(false)
  const [confirmReset, setConfirmReset] = useState(false)
  const [resetBusy, setResetBusy] = useState(false)
  const [notice, setNotice] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [s, h, c] = await Promise.all([getAdminStatus(), getAdminHealth(false), getChecklist()])
      setStatus(s)
      setHealth(h)
      setChecklist(c)
      setError('')
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    const id = setInterval(load, 20000)
    return () => clearInterval(id)
  }, [load])

  const liveCheck = async () => {
    setLiveBusy(true)
    try {
      const [h, c] = await Promise.all([getAdminHealth(true), getChecklist()])
      setHealth(h)
      setChecklist(c)
      setError('')
      setNotice(h.pinged?.length ? `Live check: ${h.pinged.join(', ')} ping hue.` : 'Live check: koi provider ping nahi hua (key nahi hai ya DEMO_MODE=on).')
    } catch (e) {
      setError(e.message)
    } finally {
      setLiveBusy(false)
    }
  }

  const doReset = async () => {
    setResetBusy(true)
    try {
      await resetDemo()
      setNotice('Demo data reset ho gaya. Ramesh General Store dobara seed hua.')
      setConfirmReset(false)
      await load()
    } catch (e) {
      setError(e.message)
      setConfirmReset(false)
    } finally {
      setResetBusy(false)
    }
  }

  const services = health?.services || {}
  const ids = [...ORDER.filter((k) => services[k]), ...Object.keys(services).filter((k) => !ORDER.includes(k))]
  const dm = status?.demo_mode
  const counts = status?.counts || health?.db || {}
  const ready = checklist?.ready

  return (
    <FullPage background={SOFT}>
      <div className="mx-auto max-w-[1180px] px-4 py-6 sm:px-6">
        <header className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-3xl font-bold">Awaaz status</h1>
            <p className="text-base" style={{ color: '#4A5873' }}>
              Providers, demo mode and the pre-demo checklist. {status?.time_ist}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={load}
              disabled={loading}
              className="inline-flex min-h-[44px] items-center gap-2 rounded-xl border-2 bg-white px-4 text-base font-semibold disabled:opacity-60"
              style={{ borderColor: '#B8C2D1' }}
            >
              <RefreshCw size={18} className={loading ? 'animate-spin' : ''} aria-hidden="true" /> Refresh
            </button>
            <button
              type="button"
              onClick={liveCheck}
              disabled={liveBusy}
              className="inline-flex min-h-[44px] items-center gap-2 rounded-xl px-4 text-base font-bold disabled:opacity-60"
              style={{ background: CYAN, color: INK }}
            >
              <Zap size={18} aria-hidden="true" /> {liveBusy ? 'Pinging...' : 'Live check'}
            </button>
            <button
              type="button"
              onClick={() => setConfirmReset(true)}
              className="inline-flex min-h-[44px] items-center gap-2 rounded-xl px-4 text-base font-bold text-white"
              style={{ background: '#B3261E' }}
            >
              <RotateCcw size={18} aria-hidden="true" /> Reset demo data
            </button>
          </div>
        </header>

        {error && (
          <div className="mt-4 flex items-start gap-2 rounded-xl px-4 py-3 text-base font-medium" style={{ background: '#FFE0DE', color: '#7A150E' }} role="alert">
            <XCircle size={20} className="mt-0.5 shrink-0" aria-hidden="true" /> {error}
          </div>
        )}
        {notice && (
          <div className="mt-4 flex items-start gap-2 rounded-xl px-4 py-3 text-base font-medium" style={{ background: '#E1F3FB', color: '#0B4A66' }} role="status">
            <CheckCircle2 size={20} className="mt-0.5 shrink-0" aria-hidden="true" /> {notice}
          </div>
        )}

        <nav className="mt-4 flex flex-wrap gap-2" aria-label="Open screens">
          {[
            ['/app', 'Phone app'],
            ['/soundbox', 'Soundbox'],
            ['/wa', 'WhatsApp sim'],
            ['/test', 'Test console'],
          ].map(([to, label]) => (
            <Link key={to} to={to} className="inline-flex min-h-[44px] items-center gap-2 rounded-xl bg-white px-4 text-base font-semibold shadow-sm hover:shadow-md">
              {label}
            </Link>
          ))}
          <a href={DOCS_URL} target="_blank" rel="noreferrer" className="inline-flex min-h-[44px] items-center gap-2 rounded-xl bg-white px-4 text-base font-semibold shadow-sm hover:shadow-md">
            API docs <ExternalLink size={16} aria-hidden="true" />
          </a>
        </nav>

        <section className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-4" aria-label="Summary">
          <Stat
            label="DEMO_MODE"
            value={dm ? dm.setting : '...'}
            hint={dm ? `Effective: ${dm.effective}. ${dm.note}` : ''}
          />
          <Stat label="Build" value={status?.build?.commit || 'unknown'} hint={status ? `${status.app} v${status.version}` : ''} />
          <Stat label="Store" value={status?.store || '...'} hint={status?.config?.upi_vpa ? `UPI ${status.config.upi_vpa}` : ''} />
          <Stat
            label="Data"
            value={`${counts.products ?? '-'} products`}
            hint={`${counts.customers ?? '-'} customers, ${counts.invoices ?? '-'} invoices (${counts.invoices_today ?? '-'} today)`}
          />
        </section>

        <h2 className="mb-3 mt-8 flex items-center gap-2 text-xl font-bold">
          <ShieldCheck size={22} aria-hidden="true" /> Providers
          {health && (
            <span className="text-base font-medium" style={{ color: '#4A5873' }}>
              {health.live_checked ? 'live-checked' : 'config only (press Live check to ping)'} · overall {health.status}
            </span>
          )}
        </h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {ids.map((id) => (
            <ProviderCard key={id} id={id} svc={services[id]} pinged={health?.live_checked} />
          ))}
        </div>

        <div className="mt-8 grid gap-6 lg:grid-cols-[1.4fr_1fr]">
          <section aria-label="Demo checklist">
            <h2 className="mb-3 flex flex-wrap items-center gap-2 text-xl font-bold">
              <CheckCircle2 size={22} aria-hidden="true" /> Demo checklist
              {checklist && (
                <span
                  className="rounded-full px-3 py-1 text-sm font-bold"
                  style={{ background: ready ? '#DDF5E4' : '#FFE0DE', color: ready ? '#0F5A2A' : '#8C1A12' }}
                >
                  {ready ? 'READY' : 'NOT READY'} · {checklist.passed}/{checklist.total} pass
                </span>
              )}
            </h2>
            <ul className="divide-y rounded-2xl bg-white shadow-sm" style={{ borderColor: '#E3E8EF' }}>
              {(checklist?.items || []).map((it) => (
                <li key={it.id} className="flex items-start gap-3 px-4 py-3" style={{ borderColor: '#E3E8EF' }}>
                  {it.ok ? (
                    <CheckCircle2 size={22} className="mt-0.5 shrink-0" style={{ color: '#1E8E3E' }} aria-label="pass" />
                  ) : (
                    <XCircle size={22} className="mt-0.5 shrink-0" style={{ color: it.level === 'advisory' ? '#B87500' : '#C0261C' }} aria-label="fail" />
                  )}
                  <div className="min-w-0 flex-1">
                    <div className="text-base font-semibold">
                      {it.label}
                      {it.level === 'advisory' && (
                        <span className="ml-2 rounded px-1.5 py-0.5 text-xs font-bold" style={{ background: '#ECF0F4', color: '#33415C' }}>advisory</span>
                      )}
                    </div>
                    <div className="text-sm tabular-nums" style={{ color: '#4A5873' }}>
                      expected {String(it.expected)} · actual {String(it.actual)}
                    </div>
                  </div>
                </li>
              ))}
              {!checklist && <li className="px-4 py-6 text-base" style={{ color: '#4A5873' }}>Loading...</li>}
            </ul>
          </section>

          <section aria-label="Configuration">
            <h2 className="mb-3 flex items-center gap-2 text-xl font-bold">
              <Database size={22} aria-hidden="true" /> Configuration
            </h2>
            <div className="rounded-2xl bg-white p-4 shadow-sm">
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
                {status &&
                  [
                    ['Sarvam key', status.config.sarvam_key ? 'set' : 'not set'],
                    ['OpenRouter key', status.config.openrouter_key ? 'set (backup AI)' : 'not set'],
                    ['WhatsApp', status.config.whatsapp_configured ? 'configured (live)' : 'simulator'],
                    ['WA app secret', status.config.wa_app_secret ? 'set' : 'not set'],
                    ['Public URL', status.config.public_base_url],
                    ['STT model', status.config.models.stt],
                    ['LLM model', status.config.models.llm],
                    ['TTS model', `${status.config.models.tts} (${status.config.models.speaker})`],
                    ['Vision model', status.config.models.vision],
                    ['OpenRouter chat model', status.config.openrouter_model],
                    ['OpenRouter vision model', status.config.openrouter_vision_model],
                  ].map(([k, v]) => (
                    <div key={k} className="contents">
                      <dt style={{ color: '#4A5873' }}>{k}</dt>
                      <dd className="break-all font-semibold">{v}</dd>
                    </div>
                  ))}
              </dl>
              {status?.next_steps?.length > 0 && (
                <div className="mt-4 rounded-xl px-3 py-2.5 text-sm" style={{ background: '#FFF1CC', color: '#5C4300' }}>
                  <div className="mb-1 flex items-center gap-1.5 font-bold">
                    <MessageCircle size={15} aria-hidden="true" /> Next steps
                  </div>
                  <ul className="list-disc pl-5">
                    {status.next_steps.map((n) => (
                      <li key={n}>{n}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </section>
        </div>
      </div>

      <ConfirmDialog
        open={confirmReset}
        title="Reset demo data?"
        body="Yeh sab database drop karke Ramesh General Store ka demo scenario dobara seed karega: bills, khata, messages, stock sab pehle jaisa. Rehearsal ke beech ke liye hai."
        confirmLabel="Haan, reset karo"
        busy={resetBusy}
        onConfirm={doReset}
        onCancel={() => setConfirmReset(false)}
      />
    </FullPage>
  )
}
