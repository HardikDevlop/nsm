import test from "node:test"
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

const page = readFileSync(new URL("../src/pages/WindowsDevices.tsx", import.meta.url), "utf8")
const api = readFileSync(new URL("../src/lib/api.ts", import.meta.url), "utf8")

test("disk types cover logical, physical, aggregate and counter status metadata", () => {
  assert.match(api, /WindowsDiskCounterStatus/)
  assert.match(api, /WindowsDiskPerformanceInstance/)
  assert.match(api, /WindowsDiskAggregatePerformance/)
  assert.match(api, /performance\?: WindowsDiskPerformance/)
})

test("disk UI renders logical, physical and aggregate performance sections", () => {
  assert.match(page, /Disk Performance/)
  assert.match(page, /Logical instance/)
  assert.match(page, /Physical instance/)
  assert.match(page, /aggregate/)
  assert.match(page, /Read IOPS/)
  assert.match(page, /Read throughput/)
  assert.match(page, /Average latency/)
})

test("disk UI preserves zeros and explicit missing-counter states", () => {
  assert.match(page, /counter\.value == null/)
  assert.match(page, /Not Supported/)
  assert.match(page, /Permission Denied/)
  assert.match(page, /Collection Failed/)
  assert.doesNotMatch(page, /counter\.value \|\| 0/)
})

test("disk UI remains compatible with old capacity-only snapshots", () => {
  assert.match(page, /const performance = disks\[0\]\?\.performance/)
  assert.match(page, /Disk performance unavailable in this snapshot/)
  assert.match(page, /fetchWindowsMetric\(deviceId, module\)/)
  assert.match(page, /Never fetched/)
})
