import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const page = await readFile(new URL('../src/pages/WindowsDevices.tsx', import.meta.url), 'utf8')
const api = await readFile(new URL('../src/lib/api.ts', import.meta.url), 'utf8')

test('Windows hardware uses saved GET and explicit manual FETCH APIs', () => {
  assert.match(api, /getWindowsHardware\(deviceId: number\)/)
  assert.match(api, /fetchWindowsHardware\(deviceId: number\)/)
  assert.match(page, /getWindowsHardware\(device\.id\)/)
  assert.match(page, /fetchWindowsHardware\(expandedDeviceId\)/)
  assert.match(page, /FETCH HARDWARE/)
})

test('Windows hardware UI preserves singleton sections and inventory arrays', () => {
  for (const field of ['computer_system', 'system_product', 'baseboard', 'bios', 'processors', 'memory_modules', 'memory_arrays']) {
    assert.ok(page.includes(field), `missing ${field}`)
  }
  assert.match(page, /hardware\.processors\.length/)
  assert.match(page, /hardware\.memory_modules\.length/)
  assert.match(page, /hardware\.memory_arrays\.length/)
  assert.doesNotMatch(page, /setInterval\([^)]*hardware|setTimeout\([^)]*hardware/)
})

test('Windows device switching resets scoped state and guards stale requests', () => {
  assert.match(page, /const detailsRequest = useRef\(0\)/)
  assert.match(page, /const requestId = \+\+detailsRequest\.current/)
  assert.match(page, /setMetrics\(\{\}\)/)
  assert.match(page, /setMetricState\(\{\}\)/)
  assert.match(page, /setMetricErrors\(\{\}\)/)
  assert.match(page, /setHardwareFetching\(false\)/)
  assert.match(page, /setSystemEvents\(\[\]\)/)
  assert.match(page, /setSystemEventsFetch\(null\)/)
  assert.match(page, /const systemEventsInFlight = useRef<string \| null>\(null\)/)
  assert.match(page, /const requestKey = `\$\{requestId\}:\$\{deviceId\}`/)
  assert.match(page, /requestId === detailsRequest\.current/)
})
