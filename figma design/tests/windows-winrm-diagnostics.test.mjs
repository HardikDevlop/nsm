import test from "node:test"
import assert from "node:assert/strict"
import fs from "node:fs"

const component = fs.readFileSync(new URL("../src/components/windows/WindowsWinRMDiagnostics.tsx", import.meta.url), "utf8")
const page = fs.readFileSync(new URL("../src/pages/WindowsDevices.tsx", import.meta.url), "utf8")

test("WinRM diagnostics are permission gated and explicit", () => {
  assert.match(component, /hasPermission\("devices:update"\)/)
  assert.match(component, /runWindowsWinRMDiagnostic\(deviceId\)/)
  assert.match(component, /onClick=\{\(\) => void run\(\)\}/)
  assert.match(component, /Not tested/)
  assert.match(component, /setRunning\(true\)/)
  assert.match(component, /disabled=\{running\}/)
})

test("WinRM UI maps actual backend stages and preserves combined auth semantics", () => {
  for (const stage of ["winrm_authentication", "powershell_authorization", "cim_query"]) assert.match(component, new RegExp(stage))
  assert.match(component, /stage\.status/)
  assert.match(component, /indeterminate/)
  assert.match(component, /independent authentication status is not available/)
  assert.doesNotMatch(component, /runWindowsTCPDiagnostic|runWindowsTLSDiagnostic|password|BEGIN PRIVATE KEY|storage_key|protected_path|verify\s*:\s*false|CERT_NONE/i)
})

test("WinRM diagnostics preserve existing TCP, TLS, CA and onboarding UI", () => {
  assert.match(page, /WindowsWinRMDiagnostics/)
  assert.match(page, /WindowsTCPDiagnostics/)
  assert.match(page, /WindowsTLSDiagnostics/)
  assert.match(page, /WindowsCATrustPanel/)
  assert.match(page, /WindowsDeviceOverview/)
})
