import { NavLink } from 'react-router-dom'
import { Store, Warehouse, BookOpen, BarChart3, Lightbulb } from 'lucide-react'

// The five rooms of the shop
const ROOMS = [
  { to: '/app/counter', icon: Store, hi: 'काउंटर', en: 'Counter' },
  { to: '/app/godown', icon: Warehouse, hi: 'गोदाम', en: 'Godown' },
  { to: '/app/khata', icon: BookOpen, hi: 'खाता', en: 'Khata' },
  { to: '/app/hisaab', icon: BarChart3, hi: 'हिसाब', en: 'Hisaab' },
  { to: '/app/salaah', icon: Lightbulb, hi: 'सलाह', en: 'Salaah' },
]

export default function AppNav() {
  return (
    <nav className="flex-shrink-0 bg-white border-t border-line flex pb-safe">
      {ROOMS.map(({ to, icon: Icon, hi, en }) => (
        <NavLink
          key={to}
          to={to}
          className={({ isActive }) =>
            `relative flex-1 min-h-[60px] flex flex-col items-center justify-center gap-0.5 transition-colors ${
              isActive ? 'text-ink' : 'text-ink-3/70'
            }`
          }
        >
          {({ isActive }) => (
            <>
              {isActive && <span className="absolute top-0 h-[3px] w-10 rounded-b-full bg-paytm-blue" />}
              <Icon size={22} strokeWidth={isActive ? 2.4 : 1.7} className={isActive ? 'text-paytm-blue' : ''} />
              <span className="font-hindi text-[13px] font-bold leading-none">{hi}</span>
              <span className="text-[10px] leading-none opacity-70">{en}</span>
            </>
          )}
        </NavLink>
      ))}
    </nav>
  )
}
