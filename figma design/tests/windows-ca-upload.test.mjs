import test from "node:test"
import assert from "node:assert/strict"
import fs from "node:fs"

const dialog = fs.readFileSync(new URL("../src/components/windows/WindowsCAUploadDialog.tsx", import.meta.url), "utf8")
const panel = fs.readFileSync(new URL("../src/components/windows/WindowsCATrustPanel.tsx", import.meta.url), "utf8")

test("upload action is management-permission gated", () => {
  assert.match(panel, /hasPermission\("windows_ca:manage"\)/)
  assert.match(panel, /UPLOAD CA/)
  assert.match(panel, /WindowsCAUploadDialog/)
  assert.doesNotMatch(panel, /assignWindowsDeviceCA|unassignWindowsDeviceCA|revokeWindowsCABundle|runWindows.*Diagnostic/)
})

test("upload validates required fields and the 1 MiB limit", () => {
  assert.match(dialog, /Certificate name is required/)
  assert.match(dialog, /Certificate file is required/)
  assert.match(dialog, /1024 \* 1024/)
  assert.match(dialog, /must not exceed 1 MiB/)
})

test("upload derives site ID and sends only FormData certificate fields", () => {
  assert.match(dialog, /siteId: number/)
  assert.match(dialog, /formData\.set\("site_id", String\(siteId\)\)/)
  assert.match(dialog, /formData\.set\("name", name\.trim\(\)\)/)
  assert.match(dialog, /formData\.set\("certificate", file\)/)
  assert.match(dialog, /uploadWindowsCABundle\(formData\)/)
  assert.doesNotMatch(dialog, /localStorage|sessionStorage|console\.(log|error).*file|file\.text\(/)
})

test("upload prevents duplicate submission and refreshes only after success", () => {
  assert.match(dialog, /setUploading\(true\)/)
  assert.match(dialog, /disabled=\{uploading\}/)
  assert.match(dialog, /onUploaded\(\)/)
  assert.match(panel, /setRefreshKey\(\(value\) => value \+ 1\)/)
  assert.match(panel, /setUploadOpen\(false\)/)
})
