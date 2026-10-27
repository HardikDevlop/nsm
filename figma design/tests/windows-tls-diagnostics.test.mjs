import test from "node:test"
import assert from "node:assert/strict"
import fs from "node:fs"

const component = fs.readFileSync(new URL("../src/components/windows/WindowsTLSDiagnostics.tsx", import.meta.url), "utf8")
const page = fs.readFileSync(new URL("../src/pages/WindowsDevices.tsx", import.meta.url), "utf8")

test("TLS diagnostics are permission gated and explicitly triggered", () => {
  assert.match(component, /hasPermission\("devices:update"\)/)
  assert.match(component, /runWindowsTLSDiagnostic\(deviceId\)/)
  assert.match(component, /onClick=\{\(\) => void run\(\)\}/)
  assert.match(component, /Not tested/)
  assert.match(component, /setRunning\(true\)/)
  assert.match(component, /disabled=\{running\}/)
})

test("TLS diagnostics render verified metadata and allowlisted guidance", () => {
  for (const field of ["certificate.subject", "certificate.issuer", "certificate.expires_at", "certificate.days_remaining", "certificate.san_match"]) assert.match(component, new RegExp(field.replace(".", "\\.")))
  assert.match(component, /untrusted_certificate|hostname_mismatch|expired_certificate|certificate_not_yet_valid|tls_handshake_failed/)
  assert.doesNotMatch(component, /verify\s*:\s*false|CERT_NONE|runWindowsTCPDiagnostic|runWindowsWinRMDiagnostic|BEGIN PRIVATE KEY|storage_key|protected_path/i)
})

test("Windows page preserves TCP and CA controls while adding TLS diagnostics", () => {
  assert.match(page, /WindowsTLSDiagnostics/)
  assert.match(page, /WindowsTCPDiagnostics/)
  assert.match(page, /WindowsCATrustPanel/)
})
