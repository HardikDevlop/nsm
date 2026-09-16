export const IST_TIME_ZONE = 'Asia/Kolkata'

/** Parse an explicit API instant once. Unknown naive strings are rejected. */
export function parseISTDate(value: string | number | Date): Date {
  if (value instanceof Date) return value
  if (typeof value === 'string' && !/(?:Z|[+-]\d{2}:?\d{2})$/.test(value)) return new Date('invalid')
  return new Date(value)
}

export function formatISTDate(value: string | number | Date | null | undefined): string {
  if (value == null || value === '') return '—'
  const date = parseISTDate(value)
  if (Number.isNaN(date.getTime())) return String(value)
  const parts = new Intl.DateTimeFormat('en-IN', {
    timeZone: IST_TIME_ZONE,
    day: '2-digit', month: '2-digit', year: 'numeric',
  }).formatToParts(date)
  const get = (type: string) => parts.find(part => part.type === type)?.value ?? ''
  return `${get('day')}-${get('month')}-${get('year')}`
}

export function formatIST(value: string | number | Date | null | undefined): string {
  if (value == null || value === '') return '—'
  const date = parseISTDate(value)
  return Number.isNaN(date.getTime()) ? String(value) : `${formatISTDate(date)} ${date.toLocaleTimeString('en-IN', { timeZone: IST_TIME_ZONE, hour12: true })}`
}

export function formatISTTime(value: string | number | Date | null | undefined, hour12 = true): string {
  if (value == null || value === '') return '—'
  const date = parseISTDate(value)
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleTimeString('en-IN', { timeZone: IST_TIME_ZONE, hour12, hour: '2-digit', minute: '2-digit' })
}
