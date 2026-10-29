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
 */
export default function useEvents(channel, handlers) {
  const [connected, setConnected] = useState(false)
  const handlersRef = useRef(handlers)
  handlersRef.current = handlers
  const typesKey = Object.keys(handlers || {}).sort().join('|')

  useEffect(() => {
    const source = new EventSource(`/api/events?channel=${encodeURIComponent(channel)}`)
    source.onopen = () => setConnected(true)
    source.onerror = () => setConnected(false)

    const types = typesKey ? typesKey.split('|') : []
    const listeners = types.map((type) => {
      const listener = (e) => {
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
      source.close()
      setConnected(false)
    }
  }, [channel, typesKey])

  return connected
}
