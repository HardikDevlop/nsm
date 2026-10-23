import assert from "node:assert/strict"
import test from "node:test"
import fs from "node:fs"

const api = fs.readFileSync("src/lib/api.ts", "utf8")
const page = fs.readFileSync("src/pages/WindowsDevices.tsx", "utf8")

test("Windows disk health API and UI use the backend contract", () => {
  assert.match(api, /hardware\/disks\/health/)
  assert.match(api, /WindowsDiskHealthMetric/)
  assert.match(api, /reliability_counters/)
  assert.match(page, /getWindowsDiskHealth\(deviceId\)/)
  assert.match(page, /Storage Health &amp; Reliability/)
  assert.match(page, /association_status === "matched"/)
})

test("Windows disk health UI preserves zero values and provider states", () => {
  assert.match(page, /metric\.value == null/)
  assert.match(page, /metric\.status !== "ok"/)
  assert.match(page, /Permission Denied/)
  assert.match(page, /Not Supported/)
  assert.match(page, /healthMetricText\(healthMetric\(record, "unsafe_shutdown_count"\)\)/)
})
