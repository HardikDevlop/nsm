import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

const api = fs.readFileSync('src/lib/api.ts', 'utf8')
const page = fs.readFileSync('src/pages/IncidentManagement.tsx', 'utf8')

test('incident page renders persisted SLA state without polling', () => {
  assert.match(api, /listIncidentSLAPolicies/)
  assert.match(api, /getManagedIncident/)
  assert.match(page, /SLA timer/)
  assert.match(page, /Paused by configured state/)
  assert.doesNotMatch(page, /refetchInterval/)
})
