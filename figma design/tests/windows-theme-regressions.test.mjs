import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const page = await readFile(new URL('../src/pages/WindowsDevices.tsx', import.meta.url), 'utf8')

test('Windows page reuses the global NMS theme tokens', () => {
  assert.match(page, /className="dashboard-page/)
  for (const token of ['var(--t-bg)', 'var(--t-card)', 'var(--t-text)', 'var(--t-border)']) assert.ok(page.includes(token), `missing ${token}`)
  assert.doesNotMatch(page, /windows-page-theme|activePageTheme|setPageTheme/)
})

test('Windows page does not render a second theme picker', () => {
  assert.doesNotMatch(page, /aria-label="Windows page theme"/)
  assert.doesNotMatch(page, /\["light", "dark", "system"\]/)
})
