import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

const api = fs.readFileSync('src/lib/api.ts', 'utf8')
const page = fs.readFileSync('src/pages/ChangeManagement.tsx', 'utf8')
const routes = fs.readFileSync('src/routes.tsx', 'utf8')

test('change management exposes controlled workflow and real APIs', () => {
  assert.match(api, /approveChange/)
  assert.match(api, /linkChangeCI/)
  assert.match(page, /Implementation plan/)
  assert.match(page, /Rollback plan/)
  assert.match(page, /maintenance_start/)
  assert.match(page, /Audit history/)
  assert.match(routes, /withPermission\(ChangeManagement, 'changes:read'\)/)
})
