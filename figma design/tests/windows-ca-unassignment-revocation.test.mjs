import test from "node:test"
import assert from "node:assert/strict"
import fs from "node:fs"

const panel = fs.readFileSync(new URL("../src/components/windows/WindowsCATrustPanel.tsx", import.meta.url), "utf8")
const unassign = fs.readFileSync(new URL("../src/components/windows/WindowsCAUnassignmentDialog.tsx", import.meta.url), "utf8")
const revoke = fs.readFileSync(new URL("../src/components/windows/WindowsCARevocationDialog.tsx", import.meta.url), "utf8")

test("unassignment is permission gated, confirmed, and bound to the selected device", () => {
  assert.match(panel, /hasPermission\("windows_ca:assign"\).*trust\?\.trust_source === "per_device"/s)
  assert.match(panel, /WindowsCAUnassignmentDialog/)
  assert.match(unassign, /unassignWindowsDeviceCA\(deviceId\)/)
  assert.match(unassign, /CONFIRM REMOVAL/)
  assert.match(unassign, /setSubmitting\(true\)/)
  assert.match(unassign, /disabled=\{submitting\}/)
  assert.match(unassign, /global or system trust policy/)
})

test("revocation is management gated and does not revoke the device's assigned bundle", () => {
  assert.match(panel, /hasPermission\("windows_ca:manage"\)/)
  assert.match(panel, /trust\?\.bundle_id === bundle\.id/)
  assert.match(panel, /WindowsCARevocationDialog/)
  assert.match(revoke, /revokeWindowsCABundle\(bundle\.id\)/)
  assert.match(revoke, /CONFIRM REVOCATION/)
  assert.match(revoke, /bundle\.status === "revoked"/)
  assert.match(revoke, /not automatically unassigned/)
})

test("mutations refresh server state and expose no sensitive certificate material", () => {
  assert.match(panel, /setRefreshKey\(\(value\) => value \+ 1\)/)
  assert.doesNotMatch(unassign, /storage_key|protected_path|BEGIN PRIVATE KEY|password/i)
  assert.doesNotMatch(revoke, /storage_key|protected_path|BEGIN PRIVATE KEY|password/i)
  assert.match(unassign, /Unable to remove the Windows CA assignment/)
  assert.match(revoke, /Unable to revoke the Windows CA bundle/)
})
