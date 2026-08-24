import { useEffect, useMemo, useState } from 'react'

const DEFAULT_PAGE_SIZE = 25

export function useTablePagination<T>(items: T[], defaultPageSize = DEFAULT_PAGE_SIZE) {
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(defaultPageSize)

  const pageCount = Math.max(1, Math.ceil(items.length / pageSize))

  useEffect(() => {
    setPage((current) => Math.min(current, pageCount))
  }, [pageCount])

  const paginatedItems = useMemo(() => {
    const startIndex = (page - 1) * pageSize
    return items.slice(startIndex, startIndex + pageSize)
  }, [items, page, pageSize])

  const startItem = items.length === 0 ? 0 : ((page - 1) * pageSize) + 1
  const endItem = items.length === 0 ? 0 : Math.min(page * pageSize, items.length)

  return {
    page,
    setPage,
    pageSize,
    setPageSize,
    pageCount,
    paginatedItems,
    startItem,
    endItem,
    totalItems: items.length,
  }
}
