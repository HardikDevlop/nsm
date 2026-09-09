import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'

const identity = await readFile(new URL('../src/lib/deviceIdentity.ts', import.meta.url), 'utf8')
const api = await readFile(new URL('../src/lib/api.ts', import.meta.url), 'utf8')
const topology = await readFile(new URL('../src/pages/Topology.tsx', import.meta.url), 'utf8')

test('known MAC identity is normalized consistently across API responses', () => {
  assert.match(identity, /const AGNIGATE_MAC = '98a87800cf3b'/)
  assert.match(identity, /mac_address/)
  assert.match(identity, /Agnigate · \$\{label\}/)
  assert.match(api, /normalizeKnownDeviceIdentity\(payload\)/)
})

test('topology applies the known MAC identity to derived nodes', () => {
  assert.match(topology, /isAgnigateMac\(mac\)/)
  assert.match(topology, /isAgnigateMac\(lldp\.remoteMac\)/)
  assert.match(topology, /isAgnigateMac\(groupMacs\[0\]\)/)
})
