import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { test } from "node:test"

const page = await readFile(new URL("../src/pages/RemoteAccess.tsx", import.meta.url), "utf8")
const api = await readFile(new URL("../src/lib/api.ts", import.meta.url), "utf8")
const viteConfig = await readFile(new URL("../vite.config.ts", import.meta.url), "utf8")
const websocket = await readFile(new URL("../../hardik/backend/services/remote_access/terminal_websocket.py", import.meta.url), "utf8")
const css = await readFile(new URL("../src/index.css", import.meta.url), "utf8")

test("Connect Terminal selects a verified credential or temporary credentials", () => {
  assert.match(page, /selectedCredential\?\.id/)
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

test("session history refreshes automatically and connection toast is once per session", () => {
  assert.match(page, /window\.setInterval\(\(\) => \{ void refreshSessionData\(\) \}, 5000\)/)
  assert.match(page, /connectionToastShownRef\.current\.has\(sessionUuid\)/)
  assert.match(page, /connectionToastShownRef\.current\.add\(sessionUuid\)/)
  assert.match(page, /sessionStorage\.getItem\(connectionToastStorageKey\(sessionUuid\)\)/)
  assert.match(page, /sessionStorage\.setItem\(connectionToastStorageKey\(sessionUuid\), "shown"\)/)
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
  assert.match(page, /if \(width <= 0 \|\| height <= 0 \|\| host\.clientWidth <= 0 \|\| host\.clientHeight <= 0\) return/)
  assert.match(page, /terminalsRef\.current\.has\(sessionUuid\)/)
  assert.match(page, /new ResizeObserver\(\(\) => \{/)
  assert.match(page, /requestAnimationFrame\(\(\) => \{[\s\S]*fitVisibleTerminal\(sessionUuid\)/)
  assert.match(page, /state\.terminal\.refresh\(0, Math\.max\(0, state\.terminal\.rows - 1\)\)/)
  assert.match(page, /event: "resize-sent"/)
})

test("terminal host containment prevents xterm fit width feedback", () => {
  assert.match(page, /grid min-w-0 grid-cols-1 xl:grid-cols-/)
  assert.match(page, /rounded-t-xl min-w-0 overflow-hidden/)
  assert.match(page, /p-2 min-w-0 flex-1 overflow-hidden/)
  assert.match(page, /remote-terminal-host h-full min-w-0 overflow-hidden/)
})

test("terminal replays buffered output only after the initial resize", () => {
  const resizeWait = websocket.indexOf("initial_message = await websocket.receive()")
  const historyReplay = websocket.indexOf("await websocket.send_bytes(bytes(managed.output_history))")
  assert.ok(resizeWait >= 0)
  assert.ok(historyReplay > resizeWait)
})

test("terminal does not double-convert device line endings or grow the page", () => {
  assert.match(page, /convertEol: false/)
  assert.match(page, /height: "clamp\(390px, 62vh, 720px\)", minHeight: 390, flex: "1 1 auto"/)
  assert.match(page, /p-2 min-w-0 flex-1 overflow-hidden.*minHeight: 0/)
})

test("xterm output cannot start a resize feedback loop", () => {
  assert.match(page, /if \(state\?\.firstOutput\) return/)
  assert.match(css, /contain: layout paint/)
})

test("stale terminal attachment stops without deleting the session", () => {
  assert.match(page, /event\.code === 4404/)
  assert.match(page, /Session ended because the Remote Access service restarted/)
  assert.match(page, /tabs\.filter\(\(item\) => item\.sessionUuid !== sessionUuid\)/)
  assert.match(page, /event\.code === 1006 \|\| event\.code === 0/)
  assert.match(page, /Remote Access service unavailable\. The session was not ended\./)
})

test("empty device inventory and Add New Remote Device open the DB-backed device form", () => {
  assert.match(page, /if \(deviceOptions\.length === 0\) setAddingDevice\(true\)/)
  assert.match(page, /event\.target\.value === "add"[\s\S]*?setAddingDevice\(true\)/)
  assert.match(page, /await createDevice\(\{ hostname, ip_address: ipAddress \}\)/)
  assert.match(page, /setDeviceId\(option\.id\)/)
  assert.match(page, /ADD REMOTE DEVICE/)
})

test("Connect Terminal cannot race host-key retry validation into session creation", () => {
  assert.match(page, /if \(testing \|\| hostKeyActionBusy\) return/)
  assert.match(page, /disabled=\{testing \|\| connecting \|\| connectingRequest \|\| hostKeyActionBusy \|\| formLocked\}/)
})

test("New Session clears selected-device form and terminal metadata without disconnecting sessions", () => {
  assert.match(page, /const startNewSession = \(\) => \{[\s\S]*?setActiveSessionUuid\(null\)[\s\S]*?setDeviceId\(""\)[\s\S]*?setUsername\(""\)[\s\S]*?setPassword\(""\)/)
  assert.match(page, /\{selected && <>[\s\S]*?Protocol/)
  assert.match(page, /\{selected && <div[\s\S]*?activeTab\?\.status/)
  assert.match(page, /\{\(testing \|\| connectingRequest\) && \([\s\S]*?role="status"/)
})
