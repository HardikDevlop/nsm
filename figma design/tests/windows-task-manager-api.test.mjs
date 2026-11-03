import assert from "node:assert/strict"
import { after, test } from "node:test"
import fs from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import ts from "typescript"

const temp = await fs.mkdtemp(path.join(os.tmpdir(), "nms-task-manager-api-"))
const source = await fs.readFile(new URL("../src/lib/api.ts", import.meta.url), "utf8")
const apiJs = ts.transpileModule(source.replace("import.meta.env.VITE_API_BASE_URL", "undefined"), {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText
const identityJs = ts.transpileModule(
  await fs.readFile(new URL("../src/lib/deviceIdentity.ts", import.meta.url), "utf8"),
  { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } },
).outputText
await fs.writeFile(path.join(temp, "api.mjs"), apiJs.replace('from "./deviceIdentity"', 'from "./deviceIdentity.mjs"'))
await fs.writeFile(path.join(temp, "deviceIdentity.mjs"), identityJs)

const storage = new Map([["nms_access_token", "test-token"]])
globalThis.window = {
  localStorage: { getItem: (key) => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: (key) => storage.delete(key) },
  sessionStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {}, length: 0, key: () => null },
  setTimeout, clearTimeout,
}
globalThis.performance = { now: () => 1 }
const api = await import(`file://${path.join(temp, "api.mjs")}`)
after(async () => fs.rm(temp, { recursive: true, force: true }))

function response(body) {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } })
}

test("Task Manager GET and POST URLs, query encoding, and cache behavior", async () => {
  const calls = []
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), init })
    return response({ device_id: 7, status: "warming_up", reason: null, collected_at: null, age_seconds: 0, items: [], total: 0, limit: 50, offset: 0 })
  }

  const processQuery = { name: "SQL Server & Agent", sort: "cpu", direction: "desc", limit: 50, offset: 10 }
  await api.getWindowsProcesses(7, processQuery)
  await api.fetchWindowsProcesses(7, processQuery)

  assert.match(calls[0].url, /\/windows\/devices\/7\/processes\?/) 
  assert.match(calls[0].url, /name=SQL\+Server\+%26\+Agent/)
  assert.equal(calls[0].init.cache, "no-store")
  assert.equal(calls[1].init.method, "POST")
  assert.equal(calls[1].init.body, "{}")
  assert.equal(calls[0].init.headers.get("Authorization"), "Bearer test-token")
})

test("optional query parameters are omitted and invalid values fail before fetch", async () => {
  let calls = 0
  globalThis.fetch = async () => { calls += 1; return response({}) }
  await assert.rejects(api.getWindowsProcesses(3, { limit: 201 }), /limit is out of range/)
  await assert.rejects(api.getWindowsProcesses(3, { offset: -1 }), /offset must be non-negative/)
  await assert.rejects(api.getWindowsProcesses(3, { name: "x".repeat(101) }), /at most 100/)
})

test("snapshot status and nullable CPU fields are returned unchanged", async () => {
  const snapshot = { device_id: 1, status: "stale", reason: "collection_timeout", collected_at: null, age_seconds: 20, items: [{ pid: 4, cpu_percent: null, cpu_status: "unavailable" }], total: 1, limit: 50, offset: 0 }
  globalThis.fetch = async () => response(snapshot)
  assert.deepEqual(await api.getWindowsProcesses(1), snapshot)
})
