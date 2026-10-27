import test, { after } from "node:test"
import assert from "node:assert/strict"
import fs from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import ts from "typescript"

const temp = await fs.mkdtemp(path.join(os.tmpdir(), "nms-ca-api-"))
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
  localStorage: { getItem: (key) => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: (key) => storage.delete(key) },
  sessionStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {}, length: 0, key: () => null },
  setTimeout, clearTimeout,
}
globalThis.performance = { now: () => 1 }
const api = await import(`file://${path.join(temp, "api.mjs")}`)

after(async () => fs.rm(temp, { recursive: true, force: true }))

function response(status, body) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } })
}

test("CA reads, assignment, unassignment and revocation use backend contracts", async () => {
  const calls = []
  globalThis.fetch = async (url, init = {}) => {
    calls.push({ url, init })
    return response(200, { device_id: 7, trust_source: "per_device", bundle_id: 12, certificate_count: null })
  }
  await api.listWindowsCABundles(10)
  await api.getWindowsCABundle(12)
  await api.assignWindowsDeviceCA(7, 12)
  await api.unassignWindowsDeviceCA(7)
  await api.revokeWindowsCABundle(12)
  assert.match(calls[0].url, /\/windows\/ca-bundles\?site_id=10$/)
  assert.match(calls[1].url, /\/windows\/ca-bundles\/12$/)
  assert.match(calls[2].url, /\/windows\/devices\/7\/ca-bundle\?bundle_id=12$/)
  assert.equal(calls[2].init.method, "PUT")
  assert.equal(calls[2].init.body, undefined)
  assert.equal(calls[3].init.method, "DELETE")
  assert.equal(calls[4].init.method, "POST")
  assert.equal(calls[0].init.headers.get("Authorization"), "Bearer test-token")
})

test("upload sends multipart fields and preserves auth without forcing Content-Type", async () => {
  let request
  globalThis.fetch = async (url, init) => {
    request = { url, init }
    return response(201, { id: 12, site_id: 10, certificate_count: null })
  }
  await api.uploadWindowsCABundle({ site_id: 10, name: "Corporate CA", description: "test", certificate: new Blob(["PEM"]) })
  assert.equal(request.init.method, "POST")
  assert.equal(request.init.headers.get("Authorization"), "Bearer test-token")
  assert.equal(request.init.headers.get("Content-Type"), null)
  assert.equal(request.init.body.get("site_id"), "10")
  assert.equal(request.init.body.get("name"), "Corporate CA")
  assert.equal(request.init.body.get("description"), "test")
  assert.equal(request.init.body.get("certificate").size, 3)
})

test("all staged diagnostics use POST and parse JSON responses", async () => {
  const calls = []
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init })
    return response(200, { step: "tcp_connect", status: "PASS", category: "success", message: "ok", duration_ms: 1 })
  }
  const results = await Promise.all([
    api.runWindowsTCPDiagnostic(7), api.runWindowsTLSDiagnostic(7), api.runWindowsWinRMDiagnostic(7),
  ])
  assert.equal(results[0].status, "PASS")
  assert.equal(calls.length, 3)
  assert.ok(calls.every(({ init }) => init.method === "POST"))
})

test("expected HTTP failures are normalized without raw sensitive detail", async () => {
  const sensitive = ["password=top-secret", "Bearer eyJhbGciOi", "/etc/private.pem", "-----BEGIN PRIVATE KEY-----", "Traceback (most recent call last):", "postgresql://user:pass@db/internal", "field required", "internal failure detail"]
  for (const status of [401, 403, 404, 409, 413, 422, 500]) {
    globalThis.fetch = async () => response(status, { detail: sensitive.join(" "), error: { message: sensitive.join(" ") }, traceback: sensitive.join(" ") })
    await assert.rejects(
      api.getWindowsCABundle(12),
      (error) => {
        assert.ok(error.message.length > 0)
        assert.equal(error.status, status)
        assert.doesNotMatch(JSON.stringify(error), /top-secret|Bearer eyJhbGciOi|private\.pem|BEGIN PRIVATE KEY|Traceback|postgresql:|field required|internal failure detail/)
        return true
      },
    )
  }
})

test("safe network failures do not expose raw fetch errors", async () => {
  globalThis.fetch = async () => { throw new TypeError("connect ECONNREFUSED password=secret") }
  await assert.rejects(api.getWindowsCABundle(12), (error) => {
    assert.equal(error.status, undefined)
    assert.equal(error.message, "Unable to reach the server.")
    assert.doesNotMatch(JSON.stringify(error), /ECONNREFUSED|password=secret/)
    return true
  })
})
