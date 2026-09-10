import test from 'node:test'
import assert from 'node:assert/strict'
import ts from 'typescript'
import { readFileSync } from 'node:fs'
const source = readFileSync(new URL('../src/pages/manualTopologyViewport.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText
const { readViewports, centeredViewport, zoomViewport } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)
test('restores the exact zoom and pan independently for each view', () => {
  const saved = { manual: { zoom: 1.5, pan: { x: 1100, y: 2700 } }, actual: { zoom: 0.75, pan: { x: -300, y: 200 } } }
  assert.deepEqual(readViewports(JSON.stringify(saved)), saved)
})
test('invalid saved state falls back safely', () => {
  for (const raw of ['invalid', 'null', '{"manual":{"zoom":1}}', '{"manual":{"zoom":0,"pan":{"x":0,"y":0}}}']) assert.deepEqual(readViewports(raw), {})
})
test('unsaved topology with negative coordinates is centered on the canvas', () => {
  const devices = [{ x: -560, y: -1600 }, { x: -340, y: -1400 }]
  const result = centeredViewport(devices)
  assert.equal(-450 * result.zoom + result.pan.x, 700)
  assert.equal(-1500 * result.zoom + result.pan.y, 410)
})

test('zoom controls preserve the world point at the canvas center and enforce limits', () => {
  const current = { zoom: 1.8, pan: { x: 900, y: -120 } }
  for (const requested of [0.1, 1, 2.5, 5]) {
    const next = zoomViewport(current, requested)
    assert.ok(next.zoom >= 0.25 && next.zoom <= 3)
    assert.ok(Math.abs((700 - current.pan.x) / current.zoom - (700 - next.pan.x) / next.zoom) < 0.00001)
    assert.ok(Math.abs((410 - current.pan.y) / current.zoom - (410 - next.pan.y) / next.zoom) < 0.00001)
  }
})
