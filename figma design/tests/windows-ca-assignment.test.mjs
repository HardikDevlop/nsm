import test from "node:test"
import assert from "node:assert/strict"
import fs from "node:fs"

const dialog = fs.readFileSync(new URL("../src/components/windows/WindowsCAAssignmentDialog.tsx", import.meta.url), "utf8")
const panel = fs.readFileSync(new URL("../src/components/windows/WindowsCATrustPanel.tsx", import.meta.url), "utf8")

test("assignment action is separately permission gated", () => {
  assert.match(panel, /hasPermission\("windows_ca:assign"\)/)
  assert.match(panel, /ASSIGN CA|REPLACE CA/)
  assert.doesNotMatch(panel, /devices:update.*assignWindowsDeviceCA/)
})

test("assignment dialog filters and disables ineligible bundles", () => {
  assert.match(dialog, /bundle\.status === "active"/)
  assert.match(dialog, /bundle\.id !== trust\?\.bundle_id/)
  assert.match(dialog, /disabled=\{bundle\.status !== "active" \|\| bundle\.id === trust\?\.bundle_id\}/)
  assert.match(dialog, /sha256_fingerprint/)
  assert.match(dialog, /not_after/)
})

test("assignment requires confirmation and prevents duplicate submission", () => {
  assert.match(dialog, /setConfirming\(true\)/)
  assert.match(dialog, /assignWindowsDeviceCA\(deviceId, selected\.id\)/)
  assert.match(dialog, /setSubmitting\(true\)/)
  assert.match(dialog, /disabled=\{submitting\}/)
  assert.match(dialog, /CONFIRM ASSIGNMENT/)
})

test("successful assignment refreshes trust without upload, revoke, unassign or diagnostics", () => {
  assert.match(panel, /setRefreshKey\(\(value\) => value \+ 1\)/)
  assert.doesNotMatch(dialog, /uploadWindowsCABundle|revokeWindowsCABundle|unassignWindowsDeviceCA|runWindows.*Diagnostic/)
  assert.doesNotMatch(dialog, /storage_key|protected_path|BEGIN PRIVATE KEY|password/i)
})
