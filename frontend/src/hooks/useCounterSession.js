import { useCallback, useState } from 'react'

const KEY = 'awaaz.counter.session'

function makeId() {
  const rnd = Math.random().toString(36).slice(2, 8)
  return `app-${rnd}`
}

function read() {
  try {
    return window.localStorage.getItem(KEY)
  } catch {
    return null
  }
}

function write(id) {
  try {
    window.localStorage.setItem(KEY, id)
  } catch {
    // private window: the id lives for this page load only
  }
}

/**
 * A stable session id for this phone's counter. It is the cart id on the server, so a reload keeps the
 * same open bill and every spoken utterance lands on the same cart.
 */
export default function useCounterSession() {
  const [sessionId, setSessionId] = useState(() => {
    const existing = read()
    if (existing) return existing
    const fresh = makeId()
    write(fresh)
    return fresh
  })

  const rotate = useCallback(() => {
    const fresh = makeId()
    write(fresh)
    setSessionId(fresh)
    return fresh
  }, [])

  return { sessionId, rotate }
}
