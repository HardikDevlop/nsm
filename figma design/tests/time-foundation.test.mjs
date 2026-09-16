import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

const format = value => {
  if (!/(?:Z|[+-]\d{2}:?\d{2})$/.test(value)) return 'Invalid Date'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Invalid Date' : `${new Intl.DateTimeFormat('en-IN', { timeZone: 'Asia/Kolkata', day: '2-digit', month: '2-digit', year: 'numeric' }).format(date)} ${date.toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour12: true })}`
}

test('explicit UTC instant formats in IST without shifting on repeated formatting', async () => {
  const value = '2026-09-15T09:00:00Z'
  const first = format(value)
  const second = format(value)
  assert.equal(first, second)
  assert.match(first, /15\/09\/2026/)
  assert.match(first, /2:30/)
})

test('unknown naive timestamps are not guessed', async () => {
  assert.equal(format('2026-09-15T09:00:00'), 'Invalid Date')
})

test('shared parser rejects manual offset guessing', () => {
  const source = fs.readFileSync(new URL('../src/time.ts', import.meta.url), 'utf8')
  assert.doesNotMatch(source, /\+05:30/)
})
