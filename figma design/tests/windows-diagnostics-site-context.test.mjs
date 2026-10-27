import test from "node:test"
import assert from "node:assert/strict"
import fs from "node:fs"

const files = ["WindowsTCPDiagnostics.tsx", "WindowsTLSDiagnostics.tsx", "WindowsWinRMDiagnostics.tsx"]
const sources = files.map((file) => fs.readFileSync(new URL(`../src/components/windows/${file}`, import.meta.url), "utf8"))
const page = fs.readFileSync(new URL("../src/pages/WindowsDevices.tsx", import.meta.url), "utf8")

test("all diagnostics receive site context and invalidate on device or site changes", () => {
  for (const source of sources) {
    assert.match(source, /siteId\?: number \| null/)
    assert.match(source, /\[deviceId, siteId\]/)
    assert.match(source, /requestId\.current \+= 1/)
    assert.match(source, /setResult\(null\)/)
  }
  assert.match(page, /WindowsTCPDiagnostics deviceId=\{d\.id\} siteId=\{d\.site_id\}/)
  assert.match(page, /WindowsTLSDiagnostics deviceId=\{d\.id\} siteId=\{d\.site_id\}/)
  assert.match(page, /WindowsWinRMDiagnostics deviceId=\{d\.id\} siteId=\{d\.site_id\}/)
})

test("site context changes do not trigger diagnostics and existing protections remain", () => {
  for (const source of sources) {
    assert.doesNotMatch(source, /useEffect\([^)]*runWindows/i)
    assert.match(source, /if \(running \|\| !Number\.isInteger\(deviceId\)/)
    assert.match(source, /hasPermission\("devices:update"\)/)
  }
  assert.match(page, /WindowsCATrustPanel/)
})
