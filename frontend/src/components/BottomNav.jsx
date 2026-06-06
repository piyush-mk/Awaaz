import { NavLink } from 'react-router-dom'
import { Warehouse, ShoppingCart, LayoutDashboard } from 'lucide-react'

const tabs = [
  { to: '/stock-in', icon: Warehouse, label: 'Stock In', labelHi: 'स्टॉक इन' },
  { to: '/sell', icon: ShoppingCart, label: 'Sell', labelHi: 'बेचें' },
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard', labelHi: 'डैशबोर्ड' },
]

export default function BottomNav() {
  return (
    <nav className="fixed bottom-0 left-1/2 -translate-x-1/2 w-full max-w-[430px] bg-white border-t border-gray-200 flex z-50 safe-area-inset-bottom">
      {tabs.map(({ to, icon: Icon, label, labelHi }) => (
        <NavLink
          key={to}
          to={to}
          className={({ isActive }) =>
            `flex-1 flex flex-col items-center justify-center py-2 gap-0.5 touch-target transition-colors ${
              isActive ? 'text-paytm-blue' : 'text-gray-400'
            }`
          }
        >
          {({ isActive }) => (
            <>
              <Icon size={22} strokeWidth={isActive ? 2.5 : 1.8} />
              <span className="text-[10px] font-semibold">{labelHi}</span>
              <span className="text-[9px] opacity-60">{label}</span>
              {isActive && (
                <span className="absolute top-0 w-8 h-0.5 bg-paytm-blue rounded-b-full" />
              )}
            </>
          )}
        </NavLink>
      ))}
    </nav>
  )
}
