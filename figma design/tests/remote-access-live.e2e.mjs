/*
 * Live Remote Access smoke test.
 *
 * This intentionally uses the same HTTP actions as the Remote Access form:
 * test -> review host key -> explicit trust -> retry -> create session.
 * It never prints credentials and never updates a mismatched host key.
 *
 * Required environment:
 *   NMS_LOGIN_EMAIL, NMS_LOGIN_PASSWORD, NMS_DEVICE_ID
 * Optional:
 *   NMS_API_BASE_URL (default http://127.0.0.1:8000/api/v1)
 *   NMS_SSH_USERNAME, NMS_SSH_PASSWORD, NMS_SSH_PORT (default 22)
 *   NMS_TRUST_UNKNOWN_HOST=1 (required to perform explicit Trust & Connect)
 *   NMS_CREATE_SESSION=1 (also validates session creation)
 */

import assert from "node:assert/strict"

const base = (process.env.NMS_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1").replace(/\/$/, "")
const required = ["NMS_LOGIN_EMAIL", "NMS_LOGIN_PASSWORD", "NMS_DEVICE_ID"]
const missing = required.filter((name) => !process.env[name])
if (missing.length) {
  console.error(`Missing environment: ${missing.join(", ")}`)
  process.exitCode = 2
  process.exit()
}

const json = (value) => JSON.stringify(value)
let token

async function request(path, init = {}) {
  const response = await fetch(`${base}${path}`, {
    ...init,
    headers: { "content-type": "application/json", authorization: `Bearer ${token ?? ""}`, ...(init.headers ?? {}) },
  })
  let body = null
  try { body = await response.json() } catch { /* preserve status below */ }
  if (!response.ok) {
    const detail = typeof body?.detail === "string" ? body.detail : `HTTP ${response.status}`
    throw new Error(`${path}: ${detail}`)
  }
  return body
}

const login = await fetch(`${base}/auth/login`, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: json({ email: process.env.NMS_LOGIN_EMAIL, password: process.env.NMS_LOGIN_PASSWORD }),
})
assert.equal(login.ok, true, `login failed with HTTP ${login.status}`)
token = (await login.json()).access_token
assert.ok(token, "login did not return an access token")

const deviceId = Number(process.env.NMS_DEVICE_ID)
const port = Number(process.env.NMS_SSH_PORT ?? 22)
const username = process.env.NMS_SSH_USERNAME
const secret = process.env.NMS_SSH_PASSWORD
const credentials = username && secret ? { username, secret, auth_type: "password" } : {}

async function testConnection() {
  return request("/remote-access/test", {
    method: "POST",
    body: json({ device_id: deviceId, protocol: "ssh", port, ...credentials, remember_credential: false }),
  })
}

let result = await testConnection()
console.log(`initial test: ${result.success ? "SUCCESS" : `${result.stage ?? "UNKNOWN"}/${result.error_code ?? result.code ?? "UNKNOWN"}`}`)

if (result.error_code === "HOST_KEY_UNKNOWN" || result.code === "HOST_KEY_UNKNOWN") {
  assert.ok(result.host_key_id, "HOST_KEY_UNKNOWN did not return host_key_id")
  assert.ok(result.fingerprint, "HOST_KEY_UNKNOWN did not return live fingerprint")
  assert.equal(result.success, false)
  if (process.env.NMS_TRUST_UNKNOWN_HOST !== "1") {
    throw new Error("HOST_KEY_UNKNOWN: review required; set NMS_TRUST_UNKNOWN_HOST=1 for explicit Trust & Connect")
  }
  const trusted = await request(`/remote-access/host-keys/${result.host_key_id}/trust`, { method: "POST", body: "{}" })
  assert.equal(trusted.status, "TRUSTED")
  assert.equal(trusted.fingerprint, result.fingerprint)
  console.log(`trusted host key ${result.host_key_id} for ${result.host}:${result.port}`)
  result = await testConnection()
  console.log(`retry: ${result.success ? "SUCCESS" : `${result.stage ?? "UNKNOWN"}/${result.error_code ?? result.code ?? "UNKNOWN"}`}`)
}

if (result.error_code === "HOST_KEY_MISMATCH" || result.code === "HOST_KEY_MISMATCH") {
  throw new Error("HOST_KEY_MISMATCH: blocked safely; no automatic update was attempted")
}
if (result.error_code === "SSH_AUTH_FAILED" || result.code === "SSH_AUTH_FAILED") {
  throw new Error("SSH_AUTH_FAILED: live device rejected credentials; update them explicitly")
}
assert.equal(result.success, true, `SSH validation failed: ${result.error_code ?? result.code ?? result.message ?? "unknown"}`)
assert.equal(result.protocol, "ssh")

if (process.env.NMS_CREATE_SESSION === "1") {
  assert.ok(username && secret, "NMS_CREATE_SESSION=1 requires NMS_SSH_USERNAME and NMS_SSH_PASSWORD")
  const session = await request("/remote-access/sessions", {
    method: "POST",
    body: json({ device_id: deviceId, protocol: "ssh", port, ...credentials, remember_credential: false }),
  })
  assert.ok(session.session_uuid, "session response did not contain session_uuid")
  console.log(`session created: ${session.session_uuid}`)
}

console.log("Remote Access live validation passed")
