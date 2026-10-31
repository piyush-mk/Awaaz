import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import useEvents from '../../hooks/useEvents'
import useCounterSession from '../../hooks/useCounterSession'
import Toast from '../Toast'
import { getSpeechManager } from '../../lib/speechManager'
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
  'khata_updated',
  'khata_confirmed',
  'khata_disputed',
  'khata_imported',
  'khata_reminders_sent',
  'postpaid_offered',
  'postpaid_approved',
  'reorder_sent',
  'galla_closed',
  'brief_ready',
  'demo_reset',
  'speech_ready',
]

export function AppProvider({ children }) {
  const { sessionId, rotate } = useCounterSession()
  const [toast, setToast] = useState(null)
  const [storeName, setStoreName] = useState('Ramesh General Store')
  const [demo, setDemo] = useState(null)
  const listeners = useRef(new Map())
  const speech = useMemo(() => getSpeechManager(), [])
  const sessionRef = useRef(sessionId)
  sessionRef.current = sessionId

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
  const connected = useEvents('store', handlers, { skipHistory: true })

  // One speech manager for the whole phone app. Phrases (instant acks) are fetched now and warmed after the
  // first touch. `speech_ready` finishes a reply whose audio was still being generated: it is spoken when it
  // belongs to this device's counter, has no session, or is a key this device is waiting for (other rooms
  // use their own session ids).
  useEffect(() => {
    speech.init()
    const off = subscribe('speech_ready', (d) => {
      if (!d || d.session_id === undefined || d.session_id === null || d.session_id === '' || d.session_id === sessionRef.current || speech.hasPending(d.key)) {
        speech.speechReady(d)
      }
    })
    return () => {
      off()
      speech.cancel()
    }
  }, [speech, subscribe])

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
    () => ({ sessionId, rotateSession: rotate, showToast, showError, subscribe, connected, storeName, demo, speech }),
    [sessionId, rotate, showToast, showError, subscribe, connected, storeName, demo, speech],
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
