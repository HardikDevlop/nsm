import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'

const apiSource = await readFile(new URL('../src/lib/api.ts', import.meta.url), 'utf8')
const queryProviderSource = await readFile(new URL('../src/lib/queryProvider.tsx', import.meta.url), 'utf8')
const snmpHooksSource = await readFile(new URL('../src/features/snmp/hooks/useSnmpQueries.ts', import.meta.url), 'utf8')

test('cancellable GET requests still use the shared API cache and in-flight dedupe', () => {
  assert.match(apiSource, /const canCache = method === "GET" && !init\.body/)
  assert.match(apiSource, /inflightRequests\.get\(key\)/)
  assert.match(apiSource, /GET deduplication are independent concerns/i)
})

test('global query defaults avoid mount and focus refetch storms', () => {
  assert.match(queryProviderSource, /refetchOnWindowFocus:\s*false/)
  assert.match(queryProviderSource, /refetchOnMount:\s*false/)
  assert.match(queryProviderSource, /refetchOnReconnect:\s*false/)
})

test('SNMP list queries remain cancellable and do not refetch on focus', () => {
  assert.match(snmpHooksSource, /queryFn: \(\{ signal \}\) => listSNMPDevicesOptimized\(params, signal\)/)
  assert.match(snmpHooksSource, /refetchOnWindowFocus:\s*false/)
})
