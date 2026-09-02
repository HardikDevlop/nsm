import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

const api = fs.readFileSync('src/lib/api.ts', 'utf8')
const page = fs.readFileSync('src/pages/ProblemManagement.tsx', 'utf8')
const routes = fs.readFileSync('src/routes.tsx', 'utf8')

test('problem management uses real problem APIs and exposes lifecycle evidence', () => {
  assert.match(api, /createProblem/)
  assert.match(api, /linkProblemIncident/)
  assert.match(api, /listUsers/)
  assert.match(api, /listIncidents/)
  assert.match(api, /priority: string/)
  assert.match(page, /Root cause/)
  assert.match(page, /Problem owner/)
  assert.match(page, /Problem priority/)
  assert.match(page, /Link incident/)
  assert.match(page, /incident\.rca/)
  assert.match(page, /Known error/)
  assert.match(page, /Audit history/)
  assert.match(routes, /withPermission\(ProblemManagement, 'problems:read'\)/)
})
