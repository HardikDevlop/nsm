import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { test } from "node:test"

const page = await readFile(new URL("../src/pages/RemoteAccess.tsx", import.meta.url), "utf8")
const api = await readFile(new URL("../src/lib/api.ts", import.meta.url), "utf8")
const viteConfig = await readFile(new URL("../vite.config.ts", import.meta.url), "utf8")

test("Connect Terminal selects a verified credential or temporary credentials", () => {
  assert.match(page, /testResult\.credential_id/)
  assert.match(page, /credential_id: savedCredentialId/)
  assert.match(page, /username: username\.trim\(\), secret: password/)
  assert.doesNotMatch(page, /localStorage.*password|sessionStorage.*password/)
  assert.match(api, /credential_id\?: number/)
})

test("the /api/v1 proxy upgrades WebSocket connections to the FastAPI backend", () => {
  assert.match(
    viteConfig,
    /['"]\/api\/v1['"]:\s*\{[\s\S]*?target:\s*['"]http:\/\/127\.0\.0\.1:8000['"][\s\S]*?ws:\s*true/,
  )
})
