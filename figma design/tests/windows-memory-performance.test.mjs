import test from "node:test"
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

const page = readFileSync(new URL("../src/pages/WindowsDevices.tsx", import.meta.url), "utf8")
const api = readFileSync(new URL("../src/lib/api.ts", import.meta.url), "utf8")

test("memory API types expose optional counter metadata", () => {
  assert.match(api, /WindowsMemoryCounterStatus/)
  assert.match(api, /available_mbytes/)
  assert.match(api, /percent_committed_bytes_in_use/)
  assert.match(api, /status: WindowsMemoryCounterStatus/)
})

test("memory UI renders advanced groups and preserves free versus available memory", () => {
  assert.match(page, /Advanced Memory Performance|Memory Capacity/)
  assert.match(page, /OS Free Memory/)
  assert.match(page, /PerfMon Available/)
  assert.match(page, /Commit & Cache/)
  assert.match(page, /Paging Activity/)
  assert.match(page, /Kernel Memory/)
})

test("memory UI preserves zero values and explicit unsupported states", () => {
  assert.match(page, /counter\.value == null/)
  assert.match(page, /Not Supported/)
  assert.match(page, /Permission Denied/)
  assert.match(page, /Collection Failed/)
  assert.doesNotMatch(page, /counter\.value \|\| 0/)
})

test("memory fetch keeps existing device-scoped refresh and timestamp behavior", () => {
  assert.match(page, /fetchWindowsMetric\(deviceId, module\)/)
  assert.match(page, /setMetrics\(\(current\) => \(\{ \.\.\.current, \[module\]: result \}\)\)/)
  assert.match(page, /Never fetched/)
})
