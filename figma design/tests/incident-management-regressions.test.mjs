import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

const api = fs.readFileSync('src/lib/api.ts', 'utf8')
const page = fs.readFileSync('src/pages/IncidentManagement.tsx', 'utf8')
const routes = fs.readFileSync('src/routes.tsx', 'utf8')

test('incident management uses persisted APIs and permission guard', () => {
  assert.match(api, /createIncident/)
  assert.match(api, /addIncidentComment/)
  assert.match(page, /Linked alerts/)
  assert.match(page, /Attachments/)
  assert.match(page, /status === ["']resolved["'][\s\S]*Close incident/)
  assert.match(page, /Acknowledge/)
  assert.match(page, /Investigating/)
  assert.match(page, /Pending/)
  assert.match(page, /Resolve/)
  assert.match(page, /Reopen/)
  assert.match(page, /Incident history/)
  assert.match(page, /Analyze RCA/)
  assert.match(page, /Probable Root Cause/)
  assert.match(api, /acknowledgeIncident/)
  assert.match(api, /reopenIncident/)
  assert.match(api, /analyzeIncidentRCA/)
  assert.match(api, /`\/incidents\/\$\{id\}\/rca`/)
  assert.match(api, /method: 'POST'/)
  assert.match(routes, /withPermission\(IncidentManagement, ["']incidents:read["']\)/)
})

test('incident actions follow the backend lifecycle', () => {
  assert.match(page, /status === ["']open["'][\s\S]*Acknowledge[\s\S]*status: ["']investigating["'][\s\S]*Resolve/)
  assert.match(page, /status === ["']investigating["'][\s\S]*status: ["']pending["'][\s\S]*Resolve/)
  assert.match(page, /status === ["']pending["'][\s\S]*status: ["']investigating["'][\s\S]*Resolve/)
  assert.match(page, /status === ["']resolved["'][\s\S]*Close incident[\s\S]*Reopen/)
  assert.match(page, /activeStatus[\s\S]*Assign/)
  assert.doesNotMatch(page, /item\.status !== ["']closed["'][\s\S]*Close incident/)
})

test('incident action failures are displayed safely', () => {
  assert.match(page, /showActionError/)
  assert.match(page, /onError: showActionError/)
  assert.match(page, /role="alert"/)
})

test('Incident RCA action uses the selected incident exactly once', () => {
  assert.match(page, /const analyzeSelectedRca = \(\) =>/)
  assert.match(page, /if \(selected == null\) return/)
  assert.match(page, /analyzeRca\.mutate\(selected\)/)
  assert.match(page, /onClick=\{analyzeSelectedRca\}/)
  assert.match(page, /queryKey: \["managed-incident", selected\]/)
  assert.match(page, /queryKey: \["rca-incidents"\]/)
  assert.doesNotMatch(page, /onClick=\{\(\) => analyzeRca\.mutate\(item\.id\)\}/)
  assert.doesNotMatch(page, /analyzeRCA\(/)
})
