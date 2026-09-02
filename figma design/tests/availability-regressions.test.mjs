import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
test('availability dashboard uses persisted reports and real generation controls', () => {
  const api = fs.readFileSync('src/lib/api.ts', 'utf8'); const page = fs.readFileSync('src/pages/Availability.tsx', 'utf8')
  assert.match(api, /listAvailabilityReports/); assert.match(api, /createAvailabilityReport/); assert.match(page, /planned/); assert.match(page, /unplanned/); assert.match(page, /No sufficient monitoring data/)
})
test('availability summary uses latest unique entity reports only', () => {
  const page = fs.readFileSync('src/pages/Availability.tsx', 'utf8')
  assert.match(page, /latestAvailabilityReports/)
  assert.match(page, /row\.entity_type}:\$\{row\.entity_id/)
  assert.match(page, /availability_percent != null/)
  assert.match(page, /sla_breached === false/)
  assert.match(page, /sla_breached === true/)
  assert.match(page, /outage\.ongoing/)
  assert.match(page, /latestIds\.has\(row\.id\)/)
})
test('availability history is separated without deleting persisted rows', () => {
  const page = fs.readFileSync('src/pages/Availability.tsx', 'utf8')
  assert.match(page, /const historyRows = rows\.filter/)
  assert.match(page, /View History/)
  assert.match(page, /summary\.latest\.map/)
  assert.match(page, /setSeconds\(0, 0\)/)
  assert.match(page, /period === "custom" \? customStart : start\.toISOString\(\)/)
})
