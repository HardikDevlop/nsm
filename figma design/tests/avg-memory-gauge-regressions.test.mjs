import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'

const page = fs.readFileSync('src/pages/Dashboard.tsx', 'utf8')

test('AVG MEMORY uses the aggregate value and preserves zero', () => {
  assert.match(page, /const displayMem = memoryAggregate\?\.average_percent \?\? null/)
  assert.match(page, /const hasMemoryData = memoryAggregate\?\.average_percent != null/)
})

test('ClockGauge treats null and undefined as static no-data values', () => {
  assert.match(page, /value: number \| null \| undefined/)
  assert.match(page, /const hasNumericValue = typeof value === "number" && Number\.isFinite\(value\)/)
  assert.match(page, /const isNoData = !hasNumericValue \|\| Boolean\(valueLabel && !\/\^\\d\/\.test\(valueLabel\)\)/)
  assert.match(page, /const numericValue = hasNumericValue \? value : 0/)
})

test('AVG MEMORY no-data and request-failure states remain visible as N/A', () => {
  assert.match(page, /valueLabel: hasMemoryData \? undefined : "N\/A"/)
  assert.match(page, /setMemoryAggregate\(null\)/)
  assert.match(page, /\{animatedValueLabel \?\? `\$\{animatedValue\.toFixed\(/)
})

test('Overview and memory aggregate requests settle independently', () => {
  assert.match(page, /Promise\.allSettled\(\[/)
  assert.match(page, /overviewResult\.status === "fulfilled"/) 
  assert.match(page, /memoryResult\.status === "fulfilled"/)
  assert.match(page, /setData\(overviewResult\.value\)/)
  assert.match(page, /setMemoryAggregate\(memoryResult\.value\)/)
})

test('Overview failure does not prevent a successful memory aggregate from rendering', () => {
  assert.match(page, /if \(overviewResult\.status === "fulfilled"\)[\s\S]*?else \{[\s\S]*?setError\(overviewResult\.reason/) 
  assert.match(page, /if \(memoryResult\.status === "fulfilled"\) \{[\s\S]*?setMemoryAggregate\(memoryResult\.value\)/)
})

test('Memory aggregate failure clears only memory data and leaves overview state intact', () => {
  assert.match(page, /if \(memoryResult\.status === "fulfilled"\)[\s\S]*?else \{\s*setMemoryAggregate\(null\)/)
  assert.match(page, /setData\(overviewResult\.value\)[\s\S]*?setUpdated\(new Date\(\)\)/)
})

test('AVG MEMORY data detection remains null-safe and zero-safe', () => {
  assert.match(page, /const hasMemoryData = memoryAggregate\?\.average_percent != null/)
  assert.doesNotMatch(page, /Boolean\(memoryAggregate\?\.average_percent\)/)
})
