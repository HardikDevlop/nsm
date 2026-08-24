import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * useAutoRefresh – runs `fetchFn` immediately on mount, then again every
 * `intervalMs` milliseconds.  Returns { loading, error, refresh } so callers
 * can also trigger a manual refresh.
 *
 * Pass `intervalMs = 0` to disable the interval (one-shot fetch only).
 */
export function useAutoRefresh<T>(
  fetchFn: () => Promise<T>,
  onData: (data: T) => void,
  intervalMs = 15000,
) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const fnRef = useRef(fetchFn)
  const cbRef = useRef(onData)

  // keep refs fresh without re-scheduling intervals
  useEffect(() => { fnRef.current = fetchFn }, [fetchFn])
  useEffect(() => { cbRef.current = onData }, [onData])

  const refresh = useCallback(async () => {
    setError(null)
    try {
      const data = await fnRef.current()
      cbRef.current(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data')
    } finally {
      setLoading(false)
    }
  }, [])

  // initial load
  useEffect(() => {
    let cancelled = false
    async function run() {
      setError(null)
      try {
        const data = await fnRef.current()
        if (!cancelled) cbRef.current(data)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load data')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void run()
    return () => { cancelled = true }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // interval polling
  useEffect(() => {
    if (!intervalMs) return
    const id = setInterval(() => {
      if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return
      void refresh()
    }, intervalMs)
    return () => clearInterval(id)
  }, [intervalMs, refresh])

  return { loading, error, refresh }
}
