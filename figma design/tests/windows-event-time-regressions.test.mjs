import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const page = await readFile(new URL('../src/pages/WindowsDevices.tsx', import.meta.url), 'utf8')

test('Windows event formatter treats timezone-naive backend values as UTC', () => {
  assert.match(page, /const formatWindowsEventTime = /)
  assert.match(page, /const utcValue = \/\(\?:Z\|\[\+\-\]\\d\{2\}:\\d\{2\}\)\$\/.test\(value\) \? value : `\$\{value\}Z`/)
  assert.match(page, /formatWindowsEventTime\(item\.time_created\)/)
})

test('Windows event formatter uses browser local rendering', () => {
  assert.match(page, /date\.toLocaleString\(\)/)
  assert.doesNotMatch(page, /item\.time_created\)\.toLocaleString\("en-IN", \{ timeZone: "Asia\/Kolkata" \}\)/)
})
