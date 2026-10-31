import { NavLink } from 'react-router-dom'
import { Store, Warehouse, BookOpen, BarChart3 } from 'lucide-react'
import MicOrb from './MicOrb'
import { useVoice } from './VoiceContext'
import { tr } from '../../lib/i18n'

// Four rooms and the mic. Salaah opens from the header.
const LEFT = [
  { to: '/app/counter', icon: Store, label: tr('Counter') },
  { to: '/app/godown', icon: Warehouse, label: tr('Godown') },
]
const RIGHT = [
  { to: '/app/khata', icon: BookOpen, label: tr('Khata') },
  { to: '/app/hisaab', icon: BarChart3, label: tr('Hisaab') },
]

function Room({ to, icon: Icon, label }) {
  return (
    <NavLink
      to={to}
      aria-label={tr(label)}
      className={({ isActive }) =>
        `flex-1 min-h-[68px] flex flex-col items-center justify-center gap-1 transition-colors ${isActive ? 'text-ink' : 'text-ink-3'}`
      }
    >
      {({ isActive }) => (
        <>
          <Icon size={22} strokeWidth={isActive ? 2.2 : 1.7} className={isActive ? 'text-paytm-blue-dark' : ''} />
          <span className={`font-hindi text-[13px] leading-none ${isActive ? 'font-bold' : 'font-medium'}`}>{tr(label)}</span>
        </>
      )}
    </NavLink>
  )
}

export default function AppNav() {
  const { rec, busy, openType } = useVoice()
  return (
    <nav className="relative z-20 flex-shrink-0 bg-white border-t border-line flex items-stretch pb-safe">
      {LEFT.map((r) => <Room key={r.to} {...r} />)}
      <div className="flex-[0_0_92px] relative">
        <div className="absolute left-1/2 -translate-x-1/2 -top-7 rounded-full p-1.5 bg-white">
          <MicOrb rec={rec} busy={busy} size={70} onUnsupported={openType} />
        </div>
      </div>
      {RIGHT.map((r) => <Room key={r.to} {...r} />)}
    </nav>
  )
}
