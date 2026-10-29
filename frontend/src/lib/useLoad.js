import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Load data on mount (and when deps change). Returns { data, error, loading, reload, setData }.
 * A stale response never overwrites a newer one.
 */
export default function useLoad(fn, deps = []) {
  const [state, setState] = useState({ data: null, error: null, loading: true })
  const seq = useRef(0)
  const fnRef = useRef(fn)
  fnRef.current = fn

  const run = useCallback(async ({ quiet = false } = {}) => {
    const id = ++seq.current
    if (!quiet) setState((s) => ({ ...s, loading: true, error: null }))
    try {
      const data = await fnRef.current()
      if (id === seq.current) setState({ data, error: null, loading: false })
      return data
    } catch (e) {
      if (id === seq.current) setState((s) => ({ data: quiet ? s.data : null, error: e, loading: false }))
      return null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  useEffect(() => {
    run()
  }, [run])

  const setData = useCallback((updater) => {
    setState((s) => ({ ...s, data: typeof updater === 'function' ? updater(s.data) : updater }))
  }, [])

  return { ...state, reload: run, setData }
}
