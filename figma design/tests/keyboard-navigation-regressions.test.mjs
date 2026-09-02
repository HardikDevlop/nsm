import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'

const hookSource = await readFile(new URL('../src/components/useKeyboardShortcuts.ts', import.meta.url), 'utf8')
const layoutSource = await readFile(new URL('../src/components/Layout.tsx', import.meta.url), 'utf8')
const cssSource = await readFile(new URL('../src/index.css', import.meta.url), 'utf8')

test('global shortcuts avoid editable fields and browser/system shortcuts', () => {
  assert.match(hookSource, /isContentEditable/)
  assert.match(hookSource, /event\.metaKey \|\| event\.ctrlKey \|\| event\.altKey/)
  assert.match(hookSource, /input\[type="search"\]/)
  assert.match(hookSource, /invalidateQueries/)
})

test('shared controls expose accessible names and keyboard focus styling', () => {
  assert.match(layoutSource, /aria-label="Open navigation"/)
  assert.match(layoutSource, /aria-label="Open notifications"/)
  assert.match(cssSource, /button:focus-visible/)
  assert.match(cssSource, /a:focus-visible/)
})
