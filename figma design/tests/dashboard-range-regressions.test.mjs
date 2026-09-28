import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'

const page = fs.readFileSync('src/pages/Dashboard.tsx', 'utf8')
const api = fs.readFileSync('src/lib/api.ts', 'utf8')

test('dashboard time ranges map to the overview API window', () => {
  assert.match(page, /range === "1H" \? 1 : range === "6H" \? 6 : range === "12H" \? 12 : range === "7D" \? 168 : 24/)
  assert.match(api, /overview\?hours=\$\{hours\}/)
})

test('manual dashboard refresh bypasses the overview cache', () => {
  assert.match(page, /load\(false, true\)/)
  assert.match(api, /force_refresh=true/)
})
