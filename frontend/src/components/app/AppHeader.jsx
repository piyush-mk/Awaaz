import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { ExternalLink, Lightbulb, MoreVertical } from 'lucide-react'
import { useApp } from './AppContext'
import { Sheet } from './ui'

const TITLES = { godown: 'गोदाम', khata: 'खाता', hisaab: 'हिसाब', salaah: 'सलाह' }

const LINKS = [
  { to: '/soundbox', label: 'Soundbox' },
  { to: '/wa', label: 'WhatsApp' },
  { to: '/status', label: 'Status' },
]

export default function AppHeader() {
  const { storeName, connected, demo } = useApp()
  const { pathname } = useLocation()
  const [menu, setMenu] = useState(false)
  const room = pathname.split('/')[2]
  const title = TITLES[room]

  return (
    <header className="bg-white flex-shrink-0 px-4 pt-[max(env(safe-area-inset-top),6px)]">
      <div className="h-12 flex items-center gap-1">
        <div className="min-w-0 flex-1">
          {title ? (
            <h1 className="font-hindi text-[22px] font-semibold leading-none">{title}</h1>
          ) : (
            <h1 className="text-[17px] font-semibold truncate">{storeName}</h1>
          )}
        </div>
        {demo === 'fixtures' && (
          <span className="rounded-full bg-orange-100 text-orange-800 text-[11px] font-semibold px-2 py-0.5 flex-shrink-0">demo data</span>
        )}
        <span
          role="status"
          className="flex items-center gap-1.5 text-xs font-medium text-red-700 px-2 flex-shrink-0"
          title={connected ? 'Live updates connected' : 'Live updates reconnecting'}
        >
          <span className={`w-2 h-2 rounded-full ${connected ? 'bg-green-600' : 'bg-red-600 animate-pulse'}`} />
          {!connected && 'offline'}
          <span className="sr-only">{connected ? 'live' : ''}</span>
        </span>
        <Link
          to="/app/salaah"
          aria-label="Salaah"
          aria-current={room === 'salaah' ? 'page' : undefined}
          className={`w-11 h-11 rounded-full flex items-center justify-center flex-shrink-0 ${room === 'salaah' ? 'bg-sky-100 text-sky-800' : 'text-ink'}`}
        >
          <Lightbulb size={22} />
        </Link>
        <button onClick={() => setMenu(true)} aria-label="Aur" className="w-11 h-11 -mr-2 rounded-full flex items-center justify-center flex-shrink-0">
          <MoreVertical size={22} />
        </button>
      </div>
      <Sheet open={menu} onClose={() => setMenu(false)} title="Doosri screen">
        <ul className="divide-y divide-line">
          {LINKS.map((l) => (
            <li key={l.to}>
              <a href={l.to} target="_blank" rel="noreferrer" className="min-h-[52px] flex items-center justify-between text-base font-semibold">
                {l.label}
                <ExternalLink size={18} className="text-ink-3" />
              </a>
            </li>
          ))}
        </ul>
      </Sheet>
    </header>
  )
}
