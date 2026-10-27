import test from "node:test"
import assert from "node:assert/strict"
import fs from "node:fs"

const source = fs.readFileSync(new URL("../src/lib/api.ts", import.meta.url), "utf8")

test("Windows CA client exposes the required typed methods", () => {
  for (const name of [
    "listWindowsCABundles", "getWindowsCABundle", "uploadWindowsCABundle",
    "revokeWindowsCABundle", "getWindowsDeviceTrust", "assignWindowsDeviceCA",
    "unassignWindowsDeviceCA", "runWindowsTCPDiagnostic", "runWindowsTLSDiagnostic",
    "runWindowsWinRMDiagnostic",
  ]) assert.match(source, new RegExp(`export async function ${name}`))
  assert.match(source, /certificate_count\?: number \| null/)
})

test("CA upload uses FormData without forcing a multipart or JSON content type", () => {
  assert.match(source, /new FormData\(\)/)
  assert.match(source, /formData\.set\("site_id", String\(data\.site_id\)\)/)
  assert.match(source, /formData\.set\("certificate", data\.certificate\)/)
  assert.match(source, /if \(!\(init\.body instanceof FormData\)\) headers\.set\("Content-Type", "application\/json"\)/)
})

test("assignment and diagnostics preserve backend HTTP contracts", () => {
  assert.match(source, /`\/windows\/devices\/\$\{deviceId\}\/ca-bundle\?bundle_id=\$\{encodeURIComponent\(bundleId\)\}`/)
  assert.match(source, /method: "PUT"/)
  assert.match(source, /method: "DELETE"/)
  assert.match(source, /diagnostics\/tcp.*method: "POST"/s)
  assert.match(source, /diagnostics\/tls.*method: "POST"/s)
  assert.match(source, /diagnostics\/winrm.*method: "POST"/s)
})

test("existing credential API remains present", () => {
  assert.match(source, /export async function testWindowsConnection/)
  assert.match(source, /export async function createWindowsCredential/)
  assert.match(source, /export async function updateWindowsCredential/)
})
