import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

test('configuration compliance uses stored policy and violation APIs', () => {
  const api = fs.readFileSync('src/lib/api.ts', 'utf8')
  const page = fs.readFileSync('src/pages/ConfigurationCompliance.tsx', 'utf8')
  assert.match(api, /listConfigurationCompliancePolicies/)
  assert.match(api, /evaluateConfigurationCompliance/)
  assert.match(page, /Open violations/)
  assert.match(page, /recommendation/i)
})
