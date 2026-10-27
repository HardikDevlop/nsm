import test from "node:test"
import assert from "node:assert/strict"
import fs from "node:fs"

const panel = fs.readFileSync(new URL("../src/components/windows/WindowsCATrustPanel.tsx", import.meta.url), "utf8")
const page = fs.readFileSync(new URL("../src/pages/WindowsDevices.tsx", import.meta.url), "utf8")

test("trust panel is permission gated and uses selected device/site", () => {
  assert.match(panel, /hasPermission\("windows_ca:read"\)/)
  assert.match(panel, /getWindowsDeviceTrust\(deviceId\)/)
  assert.match(panel, /listWindowsCABundles\(siteId\)/)
  assert.match(panel, /deviceId, siteId, hasPermission/)
  assert.match(panel, /setTrust\(null\)/)
  assert.match(panel, /setBundles\(\[\]\)/)
})

test("trust panel renders safe metadata and no management actions", () => {
  assert.match(panel, /Per-device CA/)
  assert.match(panel, /Global CA/)
  assert.match(panel, /System trust/)
  assert.match(panel, /No trust configured/)
  assert.doesNotMatch(panel, /certificate_count/)
  assert.doesNotMatch(panel, /uploadWindowsCABundle|assignWindowsDeviceCA|unassignWindowsDeviceCA|revokeWindowsCABundle|runWindows.*Diagnostic/)
  assert.doesNotMatch(panel, /storage_key|protected_path|BEGIN PRIVATE KEY|password/i)
})

test("panel is integrated only into the Windows overview", () => {
  assert.match(page, /WindowsCATrustPanel/)
  assert.match(page, /<WindowsCATrustPanel deviceId=\{d\.id\} deviceName=\{d\.hostname\} siteId=\{d\.site_id\} \/>/)
  assert.doesNotMatch(page, /WindowsCATrustPanel.*DeviceDetails/)
})
