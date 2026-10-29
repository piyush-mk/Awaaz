import { useApp } from './AppContext'

const LINKS = [
  { to: '/soundbox', label: 'Soundbox' },
  { to: '/wa', label: 'WhatsApp' },
  { to: '/status', label: 'Status' },
]

export default function AppHeader() {
  const { storeName, connected, demo } = useApp()
  return (
    <header className="bg-ink text-white px-4 pt-[max(env(safe-area-inset-top),14px)] pb-3 flex-shrink-0">
      <div className="flex items-center gap-2">
        <div className="min-w-0 flex-1">
          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-paytm-blue">Awaaz . Paytm for Business</div>
          <div className="font-hindi text-lg font-bold leading-tight truncate">{storeName}</div>
        </div>
        {demo === 'fixtures' && (
          <span className="rounded-full bg-accent/20 text-accent text-[11px] font-semibold px-2 py-0.5">demo data</span>
        )}
        <span
          className="flex items-center gap-1.5 text-[11px] text-white/70"
          title={connected ? 'Live updates connected' : 'Live updates reconnecting'}
        >
          <span className={`w-2.5 h-2.5 rounded-full ${connected ? 'bg-stock-green' : 'bg-stock-red animate-pulse'}`} />
          {connected ? 'live' : 'offline'}
        </span>
      </div>
      <div className="mt-2 flex gap-2">
        {LINKS.map((l) => (
          <a
            key={l.to}
            href={l.to}
            target="_blank"
            rel="noreferrer"
            className="flex-1 min-h-[36px] flex items-center justify-center rounded-lg bg-white/10 text-xs font-semibold text-white active:bg-white/20"
          >
            {l.label}
          </a>
        ))}
      </div>
    </header>
  )
}
