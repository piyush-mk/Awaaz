import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import useEvents from '../../hooks/useEvents'
import useCounterSession from '../../hooks/useCounterSession'
import Toast from '../Toast'
import { getStatus } from '../../api/client'
import { errMessage } from '../../lib/format'

const AppCtx = createContext(null)

// Server events on the `store` channel that the merchant screens react to.
const EVENT_TYPES = [
  'cart_updated',
  'checkout',
  'payment_received',
  'action_proposed',
  'action_resolved',
  'stock_updated',
  'wa_order',
  'wa_order_updated',
  'khata_disputed',
  'khata_imported',
  'galla_closed',
  'brief_ready',
]

export function AppProvider({ children }) {
  const { sessionId, rotate } = useCounterSession()
  const [toast, setToast] = useState(null)
  const [storeName, setStoreName] = useState('Ramesh General Store')
  const [demo, setDemo] = useState(null)
  const listeners = useRef(new Map())

  const showToast = useCallback((message, type = 'success') => setToast({ message, type, id: Date.now() }), [])
  const showError = useCallback((e) => setToast({ message: errMessage(e), type: 'error', id: Date.now() }), [])
  const closeToast = useCallback(() => setToast(null), [])

  const subscribe = useCallback((type, fn) => {
    if (!listeners.current.has(type)) listeners.current.set(type, new Set())
    listeners.current.get(type).add(fn)
    return () => listeners.current.get(type)?.delete(fn)
  }, [])

  const handlers = useMemo(
    () =>
      Object.fromEntries(
        EVENT_TYPES.map((type) => [
          type,
          (data) => listeners.current.get(type)?.forEach((fn) => fn(data)),
        ]),
      ),
    [],
  )
  const connected = useEvents('store', handlers)

  useEffect(() => {
    let alive = true
    getStatus()
      .then((s) => {
        if (!alive) return
        if (s.store) setStoreName(s.store)
        setDemo(s.demo_mode?.effective || null)
      })
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [])

  const value = useMemo(
    () => ({ sessionId, rotateSession: rotate, showToast, showError, subscribe, connected, storeName, demo }),
    [sessionId, rotate, showToast, showError, subscribe, connected, storeName, demo],
  )

  return (
    <AppCtx.Provider value={value}>
      {children}
      {toast && <Toast key={toast.id} message={toast.message} type={toast.type} onClose={closeToast} />}
    </AppCtx.Provider>
  )
}

export function useApp() {
  const ctx = useContext(AppCtx)
  if (!ctx) throw new Error('useApp must be used inside <AppProvider>')
  return ctx
}

/** Run `fn` for every server event of `type` (latest fn is always used). */
export function useStoreEvent(type, fn) {
  const { subscribe } = useApp()
  const ref = useRef(fn)
  ref.current = fn
  useEffect(() => subscribe(type, (data) => ref.current(data)), [subscribe, type])
}
