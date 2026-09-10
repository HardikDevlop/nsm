import test from 'node:test'
import assert from 'node:assert/strict'
import ts from 'typescript'
import { readFileSync } from 'node:fs'
const source = readFileSync(new URL('../src/pages/manualTopologyPorts.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText
const { portEndpoint, compactPortLabel } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)
test('connected ports keep distinct, spaced anchors including more than five links', () => {
  const device = { id: 'core', x: 100, y: 100 }
  const links = Array.from({ length: 36 }, (_, i) => ({ id: `link-${i}`, from: 'core', to: `host-${i}`, fromPort: `Gi${i + 1}` }))
  const positions = links.map(link => portEndpoint(device, link, links))
  assert.equal(new Set(positions.map(p => `${p.x},${p.y}`)).size, 36)
  for (let i = 1; i < positions.length; i++) assert.equal(positions[i].y - positions[i - 1].y, 26)
  assert.deepEqual(portEndpoint(device, links[0], [...links].reverse()), positions[0])
  const moved = portEndpoint({ ...device, x: 120, y: 150 }, links[0], links)
  assert.equal(moved.x, positions[0].x + 20)
  assert.equal(moved.y, positions[0].y + 50)
})
test('target endpoints and labels identify physical and manual ports', () => {
  const links = [{ id: '1', from: 'host', to: 'core', toPort: 'Gi7' }, { id: '2', from: 'core', to: 'host2', fromPort: 'Gi3' }]
  assert.ok(portEndpoint({ id: 'core', x: 0, y: 0 }, links[0], links).y > portEndpoint({ id: 'core', x: 0, y: 0 }, links[1], links).y)
  assert.equal(compactPortLabel('Agnigate · GigabitEthernet7'), 'Gi7')
  assert.equal(compactPortLabel('Manual Port 1'), 'M1')
  assert.equal(compactPortLabel('eth0'), 'eth0')
})

test('ports follow the peer-facing edge when devices move', () => {
  const core = { id: 'core', x: 0, y: 0 }
  const link = { id: 'link', from: 'core', to: 'peer', fromPort: 'Gi3', toPort: 'M1' }
  for (const [x, y, side, opposite] of [[400, 0, 'right', 'left'], [-400, 0, 'left', 'right'], [0, 400, 'bottom', 'top'], [0, -400, 'top', 'bottom']]) {
    const peer = { id: 'peer', x, y }
    const devices = [core, peer]
    const start = portEndpoint(core, link, [link], devices)
    const end = portEndpoint(peer, link, [link], devices)
    assert.equal(start.side, side)
    assert.equal(end.side, opposite)
    assert.ok(start.leader.startsWith(`M ${start.anchor.x} ${start.anchor.y}`))
    if (side === 'right') assert.ok(start.exit.x > start.x && end.exit.x < end.x)
    if (side === 'bottom') assert.ok(start.exit.y > start.y && end.exit.y < end.y)
  }
})
