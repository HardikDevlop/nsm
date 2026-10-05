import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { test } from "node:test"

const page = await readFile(new URL("../src/pages/RemoteAccess.tsx", import.meta.url), "utf8")
const api = await readFile(new URL("../src/lib/api.ts", import.meta.url), "utf8")
const viteConfig = await readFile(new URL("../vite.config.ts", import.meta.url), "utf8")

test("Connect Terminal selects a verified credential or temporary credentials", () => {
  assert.match(page, /testResult\.credential_id/)
  assert.match(page, /credential_id: savedCredentialId/)
  assert.match(page, /username: username\.trim\(\), secret: password/)
  assert.doesNotMatch(page, /localStorage.*password|sessionStorage.*password/)
  assert.match(api, /credential_id\?: number/)
})

test("the /api/v1 proxy upgrades WebSocket connections to the FastAPI backend", () => {
  assert.match(
    viteConfig,
    /['"]\/api\/v1['"]:\s*\{[\s\S]*?target:\s*['"]http:\/\/127\.0\.0\.1:8000['"][\s\S]*?ws:\s*true/,
  )
})

test("active and history session state bypasses API response caching", () => {
  assert.match(api, /listRemoteAccessSessions\(\): Promise<RemoteAccessSession\[]> \{\s*return requestJson<RemoteAccessSession\[]>\("\/remote-access\/sessions", \{ cache: "no-store" \}\)/)
  assert.match(api, /listRemoteAccessSessionHistory\(\): Promise<RemoteAccessSession\[]> \{\s*return requestJson<RemoteAccessSession\[]>\("\/remote-access\/sessions\/history", \{ cache: "no-store" \}\)/)
})

test("duplicate device attempts show the active protocol outside the terminal", () => {
  assert.match(page, /activeSessionForDevice\(deviceId\)/)
  assert.match(page, /is already connected via \$\{session\.protocol\.toUpperCase\(\)\}/)
  assert.match(page, /DEVICE_ALREADY_CONNECTED:\(ssh\|telnet\)/i)
  assert.doesNotMatch(page, /setTerminalError\(`[^`]*already connected/)
})

test("Connect performs session validation without requiring a prior test handshake", () => {
  assert.doesNotMatch(page, /if \(!validationMatches\)/)
  assert.match(page, /remember_credential: remember/)
  assert.match(api, /remember_credential\?: boolean/)
})

test("xterm fitting waits for the visible terminal host and reuses mounted instances", () => {
  assert.match(page, /visibleTerminalSessionRef\.current !== sessionUuid/)
  assert.match(page, /if \(width <= 0 \|\| height <= 0\) return/)
  assert.match(page, /terminalsRef\.current\.has\(sessionUuid\)/)
  assert.match(page, /new ResizeObserver\(\(\) => fitVisibleTerminal\(sessionUuid\)\)/)
})

test("empty device inventory and Add New Remote Device open the DB-backed device form", () => {
  assert.match(page, /if \(deviceOptions\.length === 0\) setAddingDevice\(true\)/)
  assert.match(page, /event\.target\.value === "add"[\s\S]*?setAddingDevice\(true\)/)
  assert.match(page, /await createDevice\(\{ hostname, ip_address: ipAddress \}\)/)
  assert.match(page, /setDeviceId\(option\.id\)/)
  assert.match(page, /ADD REMOTE DEVICE/)
})

test("New Session clears selected-device form and terminal metadata without disconnecting sessions", () => {
  assert.match(page, /const startNewSession = \(\) => \{[\s\S]*?setActiveSessionUuid\(null\)[\s\S]*?setDeviceId\(""\)[\s\S]*?setUsername\(""\)[\s\S]*?setPassword\(""\)/)
  assert.match(page, /\{selected && <>[\s\S]*?Protocol/)
  assert.match(page, /\{selected && <div[\s\S]*?activeTab\?\.status/)
  assert.match(page, /\{\(testing \|\| connectingRequest\) && \([\s\S]*?role="status"/)
})
