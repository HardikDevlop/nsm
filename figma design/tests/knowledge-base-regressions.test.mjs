import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

const api = fs.readFileSync('src/lib/api.ts', 'utf8')
const page = fs.readFileSync('src/pages/KnowledgeBase.tsx', 'utf8')
const routes = fs.readFileSync('src/routes.tsx', 'utf8')

test('knowledge base provides search, known-error types and version history', () => {
  assert.match(api, /listKnowledge/)
  assert.match(api, /updateKnowledge/)
  assert.match(page, /Search articles/)
  assert.match(page, /Known error/)
  assert.match(page, /Version history/)
  assert.match(routes, /withPermission\(KnowledgeBase, 'knowledge:read'\)/)
})
