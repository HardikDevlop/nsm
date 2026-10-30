import assert from "node:assert/strict"
import { after, test } from "node:test"
import fs from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import ts from "typescript"

const temp = await fs.mkdtemp(path.join(os.tmpdir(), "nms-api-request-json-"))
const apiJs = ts.transpileModule(
  (await fs.readFile(new URL("../src/lib/api.ts", import.meta.url), "utf8"))
    .replace("import.meta.env.VITE_API_BASE_URL", "undefined"),
  { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } },
).outputText
const identityJs = ts.transpileModule(
  await fs.readFile(new URL("../src/lib/deviceIdentity.ts", import.meta.url), "utf8"),
  { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } },
).outputText
await fs.writeFile(path.join(temp, "api.mjs"), apiJs.replace('from "./deviceIdentity"', 'from "./deviceIdentity.mjs"'))
await fs.writeFile(path.join(temp, "deviceIdentity.mjs"), identityJs)

const storage = new Map([["nms_access_token", "test-token"]])
globalThis.window = {
  localStorage: {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
    removeItem: (key) => storage.delete(key),
  },
  sessionStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {}, length: 0, key: () => null },
  setTimeout,
  clearTimeout,
}
globalThis.performance = { now: () => 1 }
const api = await import(`file://${path.join(temp, "api.mjs")}`)

after(async () => fs.rm(temp, { recursive: true, force: true }))

function jsonResponse(status, body) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } })
}

test("204 DELETE succeeds without attempting JSON parsing and sends once", async () => {
  let calls = 0
  globalThis.fetch = async (_url, init) => {
    calls += 1
    assert.equal(init.method, "DELETE")
    return new Response(null, { status: 204 })
  }

  assert.equal(await api.deleteReportSchedule(2), undefined)
  assert.equal(calls, 1)
})

test("successful JSON responses remain parsed", async () => {
  globalThis.fetch = async () => jsonResponse(200, { value: 42 })
  assert.deepEqual(await api.requestJson("/example"), { value: 42 })
})

test("HTTP errors still propagate and 401 retains one retry", async () => {
  for (const status of [400, 403, 404]) {
    globalThis.fetch = async () => jsonResponse(status, { detail: "backend error" })
    await assert.rejects(api.requestJson("/example", { cache: "no-store" }), /backend error|Unable to complete the request|not found|permission/i)
  }

  let calls = 0
  globalThis.fetch = async () => {
    calls += 1
    return jsonResponse(401, { detail: "expired" })
  }
  await assert.rejects(api.requestJson("/example", { cache: "no-store" }), /Authentication required|Not authenticated|session has expired/i)
  assert.equal(calls, 2)
})
