import test from 'node:test'
import assert from 'node:assert/strict'
import ts from 'typescript'
import { readFileSync } from 'node:fs'
const source = readFileSync(new URL('../src/pages/manualTopologyEvidence.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText
const { comparePhysicalConnection: compare } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)
const devices = [{ id: 'a', name: 'Core', backendId: 1 }, { id: 'b', name: 'Host', backendId: 2 }]
const link = { from: 'a', to: 'b', fromPort: 'Agnigate · GigabitEthernet7', toPort: 'eth0' }
const evidence = { from: 'a', to: 'b', fromPort: 'Gi7', toPort: 'eth0', protocol: 'lldp', verified: true }
test('topology evidence validates verified, partial, mismatch and unknown states', () => {
  assert.equal(compare(link, devices, [evidence]).status, 'VERIFIED')
  assert.equal(compare(link, devices, [{ ...evidence, toPort: '' }]).status, 'PARTIAL_DISCOVERY')
  assert.equal(compare(link, devices, [{ ...evidence, fromPort: 'Gi8' }]).status, 'PORT_MISMATCH')
  assert.equal(compare(link, devices, []).status, 'UNKNOWN')
})
test('topology evidence supports reversed device aliases', () => {
  const result = compare(link, devices, [{ ...evidence, from: '2', to: '1', fromPort: 'eth0', toPort: 'Gi7' }])
  assert.equal(result.status, 'VERIFIED')
  assert.equal(result.source_port, 'Gi7')
})
