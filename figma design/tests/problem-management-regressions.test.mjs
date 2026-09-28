import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const page = readFileSync(new URL('../src/pages/ProblemManagement.tsx', import.meta.url), 'utf8')
const api = readFileSync(new URL('../src/lib/api.ts', import.meta.url), 'utf8')

test('problem management edits persisted fields and loads real owners/incidents', () => {
  assert.match(page, /description: ''/)
  assert.match(page, /priority: 'p3'/)
  assert.match(page, /listUsers/)
  assert.match(page, /listIncidents/)
  assert.match(page, /updateProblem\(/)
  assert.match(page, /linkProblemIncident\(/)
})

test('problem management exposes lifecycle, known error and RCA details', () => {
  assert.match(page, /known_error/)
  assert.match(page, /permanent_fix/)
  assert.match(page, /RCA/)
  assert.match(page, /Not analyzed/)
  assert.match(api, /reference: string[\s\S]*status: string[\s\S]*probable_root_cause/)
})
