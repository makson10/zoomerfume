import { useEffect, useState } from 'react'

/**
 * Call `load(key)` on mount and again when `key` changes. A result that arrives after
 * that, or after unmount, is ignored. `error` is the last failure, if any.
 */
export function useLoad<T, K>(load: (key: K) => Promise<T>, key?: K) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<unknown>(null)

  useEffect(() => {
    let ignore = false
    load(key as K).then(
      (loaded) => {
        if (ignore) return
        setData(loaded)
        setError(null)
      },
      (failure: unknown) => {
        if (!ignore) setError(failure)
      },
    )
    return () => {
      ignore = true
    }
  }, [load, key])

  return { data, error }
}
