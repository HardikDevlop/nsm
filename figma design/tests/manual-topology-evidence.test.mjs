import test from 'node:test'
import assert from 'node:assert/strict'
import ts from 'typescript'
import { readFileSync } from 'node:fs'
const source = readFileSync(new URL('../src/pages/manualTopologyEvidence.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText
const { comparePhysicalConnection: compare } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)
const devices = [{ id: 'a', name: 'Core', backendId: 1 }, { id: 'b', name: 'Host', backendId: 2 }]
const link = { from: 'a', to: 'b', fromPort: 'Agnigate · GigabitEthernet7', toPort: 'eth0' }
const observation = { from: 'a', to: 'b', fromPort: 'Gi7', toPort: 'eth0', protocol: 'lldp', verified: true }
test('maps camelCase evidence and matches device-prefixed port names', () => {
  const result = compare(link, devices, [observation])
  assert.equal(result.status, 'VERIFIED')
  assert.equal(result.source_device, 'Core')
  assert.equal(result.source_port, 'Gi7')
  assert.equal(result.evidence_source, 'lldp')
})
test('orients reverse observations and resolves inventory aliases', () => {
  const result = compare(link, devices, [{ ...observation, from: '2', to: '1', fromPort: 'eth0', toPort: 'Gi7' }])
  assert.equal(result.status, 'VERIFIED')
  assert.equal(result.source_port, 'Gi7')
})
test('does not verify an undiscovered remote port or an unrelated pair', () => {
  assert.equal(compare(link, devices, [{ ...observation, toPort: '' }]).status, 'UNKNOWN')
  assert.equal(compare(link, devices, [{ ...observation, to: 'other' }]).status, 'UNKNOWN')
})
test('rejects known wrong ports and prefers exact parallel link evidence', () => {
  const wrong = { ...observation, fromPort: 'Gi8' }
  assert.equal(compare(link, devices, [wrong]).status, 'PORT_MISMATCH')
  assert.equal(compare(link, devices, [wrong, observation]).status, 'VERIFIED')
  assert.equal(compare(link, devices, [{ ...observation, verified: false }]).status, 'UNKNOWN')
})

test('accepts assigned manual endpoint when the discovered end matches', () => {
  const manual = { ...link, toPort: 'Manual Port 1', toPortSource: 'manual_fallback' }
  const result = compare(manual, devices, [{ ...observation, toPort: '', protocol: 'mac_table' }])
  assert.equal(result.status, 'VERIFIED')
  assert.equal(result.target_port, 'Manual Port 1 (assigned)')
  assert.equal(result.target_port_assigned, true)
  assert.match(result.reason, /assigned manual port/)
})
test('supports manual source and reversed physical evidence', () => {
  const manual = { from: 'b', to: 'a', fromPort: 'Manual Port 1', toPort: link.fromPort, fromPortSource: 'manual_fallback' }
  const result = compare(manual, devices, [{ ...observation, toPort: '' }])
  assert.equal(result.status, 'VERIFIED')
  assert.equal(result.source_port_assigned, true)
})
test('manual fallback never bypasses wrong known port or absent evidence', () => {
  const manual = { ...link, toPort: 'Manual Port 1', toPortSource: 'manual_fallback' }
  assert.equal(compare(manual, devices, [{ ...observation, fromPort: 'Gi8', toPort: '' }]).status, 'PORT_MISMATCH')
  assert.equal(compare(manual, devices, [{ ...observation, fromPort: '', toPort: '' }]).status, 'UNKNOWN')
  assert.equal(compare(manual, devices, [{ ...observation, toPort: '', verified: false }]).status, 'UNKNOWN')
  assert.equal(compare(manual, devices, []).status, 'UNKNOWN')
})
test('accepts persisted manual port metadata and rejects name-only fallback', () => {
  const manual = { ...link, toPort: 'Manual Port 1' }
  const observed = [{ ...observation, toPort: '' }]
  assert.equal(compare(manual, devices, observed).status, 'UNKNOWN')
  assert.equal(compare(manual, [devices[0], { ...devices[1], portSources: { 'Manual Port 1': 'manual_fallback' } }], observed).status, 'VERIFIED')
})
