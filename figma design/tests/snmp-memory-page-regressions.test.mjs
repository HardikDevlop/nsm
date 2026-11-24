import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'

const page = await readFile(new URL('../src/features/snmp/pages/SNMPMemoryMonitoring.tsx', import.meta.url), 'utf8')
const genericPage = await readFile(new URL('../src/features/snmp/pages/SNMPGenericModulePage.tsx', import.meta.url), 'utf8')
const hooks = await readFile(new URL('../src/features/snmp/hooks/useSnmpQueries.ts', import.meta.url), 'utf8')
const card = await readFile(new URL('../src/features/snmp/components/SNMPCollectorDataCard.tsx', import.meta.url), 'utf8')
const api = await readFile(new URL('../src/lib/api.ts', import.meta.url), 'utf8')

test('memory page disables monitoring snapshot and uses latest-memory only', () => {
  assert.doesNotMatch(page, /useMonitoringData/)
  assert.match(page, /useLatestMemory\(id\)/)
  assert.match(page, /latestMemory\?\.supported/)
  assert.match(page, /caps\?\.memory === true/)
  assert.match(page, /const history: any\[\] = \[\]/)
  assert.match(page, /timestamp: latestMemory\?\.last_poll/)
})

test('memory query is device-isolated and refreshes every 15 seconds', () => {
  assert.match(hooks, /latestMemory: \(deviceId: number\) => \['snmp', 'metrics', 'memory', deviceId\]/)
  assert.match(hooks, /queryKey: snmpKeys\.latestMemory\(deviceId!\)/)
  assert.match(hooks, /refetchInterval: 15000/)
  assert.match(hooks, /refetchOnWindowFocus: true/)
  assert.match(hooks, /refetchOnReconnect: true/)
})

test('latest memory API preserves numeric and source metadata fields', () => {
  assert.match(api, /export interface LatestMemory \{[\s\S]*memory_source: string \| null[\s\S]*memory_source_error: string \| null/)
  assert.match(api, /getLatestMemory\(deviceId: number\)[\s\S]*`\/snmp\/devices\/\$\{deviceId\}\/memory\/latest`/)
})

test('memory card renders source semantics, controlled reason, stale state, and N/A', () => {
  assert.match(card, /Unknown \/ not recorded/)
  assert.match(card, /Canonical Linux MemAvailable/)
  assert.match(card, /UCD-SNMP legacy\/fallback/)
  assert.match(card, /HOST-RESOURCES RAM/)
  assert.match(card, /Vendor-defined RAM/)
  assert.match(card, /STALE SAMPLE/)
  assert.match(card, /value == null \? "N\/A"/)
  assert.match(card, /memory_source_error/)
  assert.doesNotMatch(card, /total_bytes.*\-.*free_bytes.*utilization_percent/)
})

test('other modules retain monitoring-data behavior', () => {
  assert.match(genericPage, /useMonitoringData\(id, !isMacTable && !isMemory\)/)
  assert.match(genericPage, /: dbModule\n    \? \{/) 
})
