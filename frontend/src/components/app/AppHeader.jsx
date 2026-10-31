import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { ExternalLink, Keyboard, Lightbulb, MoreVertical } from 'lucide-react'
import { useApp } from './AppContext'
import { Sheet } from './ui'
import { useVoice } from './VoiceContext'
import { lang, setLang } from '../../lib/i18n'
import { tr } from '../../lib/i18n'

const TITLES = { counter: tr('Counter'), godown: tr('Godown'), khata: tr('Khata'), hisaab: tr('Hisaab'), salaah: tr('Salaah') }

const LINKS = [
  { to: '/soundbox', label: 'Soundbox' },
  { to: '/wa', label: tr('WhatsApp') },
  { to: '/status', label: 'Status' },
]

export default function AppHeader() {
  const { storeName, connected, demo } = useApp()
  const { openType } = useVoice()
  const { pathname } = useLocation()
  const [menu, setMenu] = useState(false)
  const room = pathname.split('/')[2]
  const title = TITLES[room]

  return (
    <header className="bg-white flex-shrink-0 px-4 pt-[max(env(safe-area-inset-top),6px)]">
      <div className="h-12 flex items-center gap-1">
        <div className="min-w-0 flex-1">
          <h1 className="font-hindi text-[22px] font-semibold leading-none truncate">{title ? tr(title) : storeName}</h1>
        </div>
        {demo === 'fixtures' && (
          <span className="rounded-full bg-orange-100 text-orange-800 text-[11px] font-semibold px-2 py-0.5 flex-shrink-0">demo</span>
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
        <button onClick={openType} aria-label={tr('Type karein')} className="w-11 h-11 rounded-full flex items-center justify-center flex-shrink-0">
          <Keyboard size={22} />
        </button>
        <Link
          to="/app/salaah"
          aria-label={tr('Salaah')}
          aria-current={room === 'salaah' ? 'page' : undefined}
          className={`w-11 h-11 rounded-full flex items-center justify-center flex-shrink-0 ${room === 'salaah' ? 'bg-sky-100 text-sky-800' : 'text-ink'}`}
        >
          <Lightbulb size={22} />
        </Link>
        <button onClick={() => setMenu(true)} aria-label={tr('Aur')} className="w-11 h-11 -mr-2 rounded-full flex items-center justify-center flex-shrink-0">
          <MoreVertical size={22} />
        </button>
      </div>
      <Sheet open={menu} onClose={() => setMenu(false)} title={storeName}>
        <div className="text-sm text-ink-3 mb-1">{tr('Bhasha')}</div>
        <div className="grid grid-cols-2 gap-2 mb-4" role="group" aria-label={tr('Bhasha')}>
          {[['hi', 'हिंदी'], ['en', 'English']].map(([id, label]) => (
            <button key={id} onClick={() => setLang(id)} aria-pressed={lang === id} className={`min-h-[48px] rounded-xl text-base font-semibold ${lang === id ? 'bg-ink text-white' : 'bg-bg-app text-ink'}`}>{label}</button>
          ))}
        </div>
        <div className="text-sm text-ink-3 mb-1">{tr('Doosri screen')}</div>
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
