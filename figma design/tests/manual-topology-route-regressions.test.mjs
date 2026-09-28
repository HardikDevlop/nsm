import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
const page = readFileSync(new URL('../src/pages/ManualTopology.tsx', import.meta.url), 'utf8')
const portMap = readFileSync(new URL('../src/pages/DevicePortMap.tsx', import.meta.url), 'utf8')
const routes = readFileSync(new URL('../src/routes.tsx', import.meta.url), 'utf8')
test('topology route and live evidence workflow are available', () => {
  for (const token of ['manual-topology', 'ManualTopology', 'topology:read', 'getLatestManualTopologySnapshot', 'getSNMPInterfaces', 'getSNMPTopology', 'reconcileManualTopology', 'MiniMap', 'Connect workflow', 'PARTIAL_DISCOVERY', 'UNKNOWN']) assert.match(`${routes}\n${page}`, new RegExp(token))
})
test('device port map route uses live interface APIs', () => {
  assert.match(routes, /manual-topology\/device\/:deviceId\/ports/)
  assert.match(routes, /DevicePortMap/)
  assert.match(portMap, /getSNMPInterfaces/)
  assert.match(portMap, /getLatestInterfaces/)
})
