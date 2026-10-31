import { useEffect, useRef, useState } from 'react'

/**
 * Subscribe to the server's live event stream (SSE).
 *
 *   const connected = useEvents('store', {
 *     cart_updated: (data) => setCart(data.cart),
 *     payment_received: (data) => ...,
 *   })
 *
 * `channel` is 'store' (counter, Soundbox, khata, stock) or 'wa' (WhatsApp simulator).
 * The server names each event, so a listener is attached for every key of `handlers`.
 * The browser reconnects by itself and replays missed events (Last-Event-ID).
 * Handlers can change every render; the latest ones are always used.
 * Returns true while the stream is connected.
 *
 * `skipHistory`: the server replays recent events to a brand new connection. Screens that act on events
 * (open a QR, show "paid") pass this so a page load never re-runs an old payment. Reconnects still get
 * the events they missed.
 */
const HISTORY_WINDOW_MS = 500

export default function useEvents(channel, handlers, { skipHistory = false } = {}) {
  const [connected, setConnected] = useState(false)
  const handlersRef = useRef(handlers)
  handlersRef.current = handlers
  const typesKey = Object.keys(handlers || {}).sort().join('|')

  useEffect(() => {
    const source = new EventSource(`/api/events?channel=${encodeURIComponent(channel)}`)
    source.onopen = () => setConnected(true)
    source.onerror = () => setConnected(false)

    let coldUntil = 0
    let greeted = false
    const onHello = () => {
      if (!greeted && skipHistory) coldUntil = Date.now() + HISTORY_WINDOW_MS
      greeted = true
    }
    source.addEventListener('hello', onHello)

    const types = typesKey ? typesKey.split('|') : []
    const listeners = types.map((type) => {
      const listener = (e) => {
        if (Date.now() < coldUntil) return
        let data = {}
        try {
          data = e.data ? JSON.parse(e.data) : {}
        } catch {
          return
        }
        const fn = handlersRef.current && handlersRef.current[type]
        if (fn) fn(data, e)
      }
      source.addEventListener(type, listener)
      return [type, listener]
    })

    return () => {
      listeners.forEach(([type, listener]) => source.removeEventListener(type, listener))
      source.removeEventListener('hello', onHello)
      source.close()
      setConnected(false)
    }
  }, [channel, typesKey, skipHistory])

  return connected
}
