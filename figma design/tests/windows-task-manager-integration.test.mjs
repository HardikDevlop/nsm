import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"

const page = await readFile(new URL("../src/pages/WindowsDevices.tsx", import.meta.url), "utf8")
const routes = await readFile(new URL("../src/routes.tsx", import.meta.url), "utf8")
const sidebar = await readFile(new URL("../src/components/Sidebar.tsx", import.meta.url), "utf8")

test("Windows details exposes Processes section", () => {
  assert.match(page, /"processes"/)
  assert.match(page, /processes: "Processes"/)
  assert.match(page, /WindowsProcessesPanel/)
})

test("Task Manager sections reuse the existing dynamic route and device context", () => {
  assert.match(routes, /path: "windows-devices\/\:deviceId\/\:section"/)
  assert.match(page, /case "processes":\s*return <WindowsProcessesPanel deviceId=\{d\.id\} \/>/)
  assert.match(page, /tabNames\.includes\(routeSection as TabName\)/)
})

test("existing Windows tabs and page permission boundary remain intact", () => {
  for (const tab of ["overview", "cpu", "memory", "disk", "network", "hardware", "storage", "events", "usb"]) assert.match(page, new RegExp(`\\"${tab}\\"`))
  assert.match(routes, /path: "windows-devices",[\s\S]*?device_monitoring:read/)
  assert.doesNotMatch(sidebar, /Task Manager|Processes|Services/)
  assert.doesNotMatch(routes, /windows-devices\/\:deviceId\/processes|windows-devices\/\:deviceId\/services/)
})

test("tab integration does not add collection or polling behavior", () => {
  const integration = page.slice(page.indexOf('case "processes"'), page.indexOf('case "hardware"'))
  assert.doesNotMatch(integration, /fetchWindowsProcesses|setInterval|setTimeout/)
})
