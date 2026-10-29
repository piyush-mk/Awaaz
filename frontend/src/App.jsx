import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import BottomNav from './components/BottomNav'
import AppRoot from './pages/app/AppRoot'
import StockIn from './pages/StockIn'
import Sell from './pages/Sell'
import Dashboard from './pages/Dashboard'
import PhotoInventory from './pages/PhotoInventory'

// Full-width side screens (owned by another agent): Soundbox emulator, WhatsApp simulator, status, test console.
const Soundbox = lazy(() => import('./pages/Soundbox'))
const WhatsAppSim = lazy(() => import('./pages/WhatsAppSim'))
const StatusPage = lazy(() => import('./pages/StatusPage'))
const TestConsole = lazy(() => import('./pages/TestConsole'))

function FullWidthFallback() {
  return <div className="p-8 text-center text-sm text-gray-500">Loading...</div>
}

// The old v1 screens, kept reachable (not in the nav) inside the 430px phone frame.
function LegacyShell({ children }) {
  return (
    <div className="phone-shell">
      <header className="paytm-header text-white px-4 pt-10 pb-4 flex-shrink-0">
        <div className="text-xs font-medium opacity-80 uppercase tracking-wider">Paytm for Business</div>
        <div className="text-lg font-bold leading-tight">Voice Business Suite (v1)</div>
        <a href="/app" className="text-xs underline opacity-90">Naye app par jaayein</a>
      </header>
      <main className="flex-1 overflow-y-auto pb-20">
        {children}
      </main>
      <BottomNav />
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<FullWidthFallback />}>
        <Routes>
          <Route path="/" element={<Navigate to="/app" replace />} />
          <Route path="/app/*" element={<AppRoot />} />
          <Route path="/soundbox" element={<Soundbox />} />
          <Route path="/wa" element={<WhatsAppSim />} />
          <Route path="/status" element={<StatusPage />} />
          <Route path="/test" element={<TestConsole />} />
          <Route path="/stock-in" element={<LegacyShell><StockIn /></LegacyShell>} />
          <Route path="/sell" element={<LegacyShell><Sell /></LegacyShell>} />
          <Route path="/photo" element={<LegacyShell><PhotoInventory /></LegacyShell>} />
          <Route path="/dashboard" element={<LegacyShell><Dashboard /></LegacyShell>} />
          <Route path="*" element={<Navigate to="/app" replace />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  )
}
