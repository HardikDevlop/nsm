import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

const api = fs.readFileSync('src/lib/api.ts', 'utf8')
const page = fs.readFileSync('src/pages/ChangeManagement.tsx', 'utf8')
const routes = fs.readFileSync('src/routes.tsx', 'utf8')

test('change management exposes controlled workflow and real APIs', () => {
  assert.match(api, /approveChange/)
  assert.match(api, /rejectChange/)
  assert.match(api, /submitChange/)
  assert.match(api, /rollbackChange/)
  assert.match(api, /linkChangeCI/)
  assert.match(api, /linkChangeProblem/)
  assert.match(api, /unlinkChangeIncident/)
  assert.match(api, /unlinkChangeProblem/)
  assert.match(api, /listChangeProblems/)
  assert.match(page, /Change priority/)
  assert.match(page, /Change owner/)
  assert.match(page, /Approval required/)
  assert.match(page, /Implementation plan/)
  assert.match(page, /Rollback plan/)
  assert.match(page, /Implementation result/)
  assert.match(page, /Rollback result/)
  assert.match(page, /maintenance_start/)
  assert.match(page, /Audit history/)
  assert.match(page, /Linked problems/)
  assert.match(page, /Unlink/)
  assert.match(routes, /withPermission\(ChangeManagement, 'changes:read'\)/)
})
