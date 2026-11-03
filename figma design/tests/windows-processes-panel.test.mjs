import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"

const source = await readFile(new URL("../src/components/windows/WindowsProcessesPanel.tsx", import.meta.url), "utf8")

test("processes panel uses typed cache GET and explicit POST refresh", () => {
  assert.match(source, /getWindowsProcesses\(deviceId, query\)/)
  assert.match(source, /fetchWindowsProcesses\(deviceId, query\)/)
  assert.match(source, /status !== "ok"/)
  assert.match(source, /getWindowsProcesses\(deviceId, query\)/g)
})

test("processes panel provides bounded search, sorting, pagination, and human-readable columns", () => {
  for (const token of ["maxLength={100}", "value=\"cpu\"", "value=\"memory\"", "value=\"name\"", "value=\"pid\"", "TablePagination", "Process Name", "Process ID", "CPU Usage", "Memory Usage", "Threads", "Started At", "Parent Process ID", "Private Memory"]) assert.match(source, new RegExp(token.replace(/[{}]/g, "\\$&")))
  assert.match(source, /value\.slice\(0, 100\)/)
  assert.match(source, /pidSearch/)
  assert.match(source, /setExpanded/)
})

test("processes panel handles permission, status, null CPU, and no polling safely", () => {
  assert.match(source, /hasPermission\("devices:update"\)/)
  assert.match(source, /disabled={!canRefresh \|\| refreshing}/)
  assert.match(source, /presentProcessCPU\(row\.cpu_status, row\.cpu_percent\)/)
  assert.match(source, /presentTaskManagerStatus\(snapshot\?\.status\)/)
  assert.match(source, /Not available/)
  assert.match(source, /CPU Idle Time/)
  assert.match(source, /Original:/)
  assert.doesNotMatch(source, /setInterval/)
  assert.match(source, /setTimeout\(\(\) => \{ void poll\(\) \}, 5000\)/)
  assert.doesNotMatch(source, /kill|command_line|executable_path|environment/i)
})

test("processes panel guards unmounts and outdated device responses", () => {
  assert.match(source, /mounted\.current/)
  assert.match(source, /requestSeq\.current/)
  assert.match(source, /sequence === requestSeq\.current/)
  assert.match(source, /return \(\) => \{ active = false \}/)
})

test("processes panel uses completion-based scoped polling with visibility cleanup", () => {
  assert.match(source, /fetchWindowsProcesses\(deviceId, query\)/)
  assert.match(source, /setTimeout\(\(\) => \{ void poll\(\) \}, 5000\)/)
  assert.match(source, /document\.addEventListener\("visibilitychange"/)
  assert.match(source, /document\.removeEventListener\("visibilitychange"/)
  assert.match(source, /pollingInFlight\.current/)
  assert.match(source, /view === "history"/) 
  assert.match(source, /pollingStatus/)
})
