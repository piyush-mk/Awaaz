import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { AppProvider } from '../../components/app/AppContext'
import { VoiceProvider } from '../../components/app/VoiceContext'
import AppHeader from '../../components/app/AppHeader'
import AppNav from '../../components/app/AppNav'
import { SkeletonList } from '../../components/app/ui'
import Counter from './Counter'
import Godown from './Godown'
import Khata from './Khata'
import Salaah from './Salaah'

// recharts is heavy: load Hisaab on demand
const Hisaab = lazy(() => import('./Hisaab'))

function Loading() {
  return (
    <div className="p-4">
      <SkeletonList rows={4} />
    </div>
  )
}

/** The merchant phone: header, rooms, bottom nav with the mic. Rendered under /app/*. */
export default function AppRoot() {
  return (
    <AppProvider>
      <div className="phone-shell">
        <VoiceProvider>
          <AppHeader />
          <main className="flex-1 min-h-0 overflow-y-auto app-scroll">
            <Suspense fallback={<Loading />}>
              <Routes>
                <Route index element={<Navigate to="counter" replace />} />
                <Route path="counter" element={<Counter />} />
                <Route path="godown" element={<Godown />} />
                <Route path="khata/*" element={<Khata />} />
                <Route path="hisaab" element={<Hisaab />} />
                <Route path="salaah" element={<Salaah />} />
                <Route path="*" element={<Navigate to="/app/counter" replace />} />
              </Routes>
            </Suspense>
          </main>
          <AppNav />
        </VoiceProvider>
      </div>
    </AppProvider>
  )
}
