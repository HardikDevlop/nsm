import { useDeferredValue, useMemo, useState } from 'react'

export function useDeferredSearch(initialValue = '') {
  const [search, setSearch] = useState(initialValue)
  const deferredSearch = useDeferredValue(search)
  const normalizedSearch = useMemo(() => deferredSearch.trim().toLowerCase(), [deferredSearch])

  return {
    search,
    setSearch,
    deferredSearch,
    normalizedSearch,
    hasSearch: normalizedSearch.length > 0,
  }
}
