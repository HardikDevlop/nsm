import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

const api = fs.readFileSync('src/lib/api.ts', 'utf8')
const page = fs.readFileSync('src/pages/RCA.tsx', 'utf8')
const routes = fs.readFileSync('src/routes.tsx', 'utf8')

test('RCA dashboard uses stored RCA APIs and exposes raw alerts', () => {
  assert.match(api, /analyzeRCA/)
  assert.match(api, /getRCAIncident/)
  assert.match(page, /What Happened/)
  assert.match(page, /Probable Root Cause/)
  assert.match(page, /Why RCA Selected This/)
  assert.match(page, /Current State/)
  assert.match(page, /Supporting Evidence/)
  assert.match(page, /Confidence is a deterministic correlation score/)
  assert.match(page, /Insufficient evidence to determine a probable root cause/)
  assert.match(page, /RECOVERED/)
  assert.match(page, /PARTIALLY RECOVERED/)
  assert.match(page, /<details[\s\S]*key=\{alert\.id\}/)
  assert.match(page, /refetchOnWindowFocus: false/)
  assert.doesNotMatch(page, /refetchInterval/)
  assert.match(routes, /withPermission\(RCA, 'rca:read'\)/)
})
