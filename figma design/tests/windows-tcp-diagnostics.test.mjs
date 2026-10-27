import test from "node:test"
import assert from "node:assert/strict"
import fs from "node:fs"

const component = fs.readFileSync(new URL("../src/components/windows/WindowsTCPDiagnostics.tsx", import.meta.url), "utf8")
const page = fs.readFileSync(new URL("../src/pages/WindowsDevices.tsx", import.meta.url), "utf8")

test("TCP diagnostics are permission gated and explicitly triggered", () => {
  assert.match(component, /hasPermission\("devices:update"\)/)
  assert.match(component, /runWindowsTCPDiagnostic\(deviceId\)/)
  assert.match(component, /onClick=\{\(\) => void run\(\)\}/)
  assert.match(component, /Not tested/)
  assert.match(component, /setRunning\(true\)/)
  assert.match(component, /disabled=\{running\}/)
})

test("TCP results use safe fields and do not invoke later diagnostic stages", () => {
  assert.match(component, /result\.status/)
  assert.match(component, /result\.category/)
  assert.match(component, /result\.message/)
  assert.match(component, /connection_refused|timeout|dns_resolution/)
  assert.doesNotMatch(component, /runWindowsTLSDiagnostic|runWindowsWinRMDiagnostic|password|BEGIN PRIVATE KEY|storage_key|protected_path/i)
})

test("Windows page places TCP diagnostics without replacing CA or onboarding controls", () => {
  assert.match(page, /WindowsTCPDiagnostics/)
  assert.match(page, /WindowsCATrustPanel/)
  assert.match(page, /WindowsDeviceOverview/)
})
