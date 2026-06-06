import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import BottomNav from './components/BottomNav'
import StockIn from './pages/StockIn'
import Sell from './pages/Sell'
import Dashboard from './pages/Dashboard'
import TestConsole from './pages/TestConsole'
import PhotoInventory from './pages/PhotoInventory'

function AppShell() {
  const location = useLocation()
  const isTest = location.pathname === '/test'

  if (isTest) {
    return (
      <Routes>
        <Route path="/test" element={<TestConsole />} />
      </Routes>
    )
  }

  return (
    <div className="flex flex-col h-full">
      <header className="paytm-header text-white px-4 pt-10 pb-4 flex-shrink-0">
        <div className="text-xs font-medium opacity-80 uppercase tracking-wider">Paytm for Business</div>
        <div className="text-lg font-bold leading-tight">Voice Business Suite</div>
        <div className="text-xs opacity-75 mt-0.5">Ramesh General Store · ID: 8847123XXX</div>
      </header>
      <main className="flex-1 overflow-y-auto pb-20">
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/stock-in" element={<StockIn />} />
          <Route path="/sell" element={<Sell />} />
          <Route path="/photo" element={<PhotoInventory />} />
          <Route path="/dashboard" element={<Dashboard />} />
        </Routes>
      </main>
      <BottomNav />
    </div>
  )
}

function App() {
  return (
    <BrowserRouter>
      <AppShell />
    </BrowserRouter>
  )
}

export default App
