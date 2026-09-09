import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

const api = fs.readFileSync('src/lib/api.ts', 'utf8')
const page = fs.readFileSync('src/pages/KnowledgeBase.tsx', 'utf8')
const routes = fs.readFileSync('src/routes.tsx', 'utf8')

test('knowledge base provides search, known-error types and version history', () => {
  assert.match(api, /listKnowledge/)
  assert.match(api, /updateKnowledge/)
  assert.match(api, /submitKnowledgeForReview/)
  assert.match(api, /publishKnowledge/)
  assert.match(api, /retireKnowledge/)
  assert.match(page, /Search title or content/)
  assert.match(page, /Category filter/)
  assert.match(page, /Tag filter/)
  assert.match(page, /Submit for Review/)
  assert.match(page, /Return to Draft/)
  assert.match(page, /published_at|Published:/)
  assert.match(page, /History/)
  assert.match(page, /Known error/)
  assert.match(page, /Versions/)
  assert.match(routes, /withPermission\(KnowledgeBase, 'knowledge:read'\)/)
})
