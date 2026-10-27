import test from "node:test"
import assert from "node:assert/strict"
import fs from "node:fs"

const panel = fs.readFileSync(new URL("../src/components/windows/WindowsCATrustPanel.tsx", import.meta.url), "utf8")
const api = fs.readFileSync(new URL("../../hardik/backend/windows_monitoring/api.py", import.meta.url), "utf8")

test("unavailable trust is distinct from no trust and displays safe guidance", () => {
  assert.match(panel, /unavailable: "Trust unavailable"/)
  assert.match(panel, /CA trust configuration is unavailable or invalid/) 
  assert.match(api, /"trust_source": "unavailable"/)
  assert.doesNotMatch(panel, /protected_path|storage_key|BEGIN PRIVATE KEY|password/i)
})

test("existing trust states and verified TLS behavior remain intact", () => {
  for (const source of ["per_device", "global", "system", "none"]) assert.match(panel, new RegExp(source))
  assert.match(api, /HTTPException\(status_code=409, detail=str\(exc\)\)/)
  assert.match(api, /ssl\.create_default_context\(cafile=ca_trust_path or None\)/)
  assert.doesNotMatch(api, /verify\s*=\s*False|CERT_NONE/)
})
