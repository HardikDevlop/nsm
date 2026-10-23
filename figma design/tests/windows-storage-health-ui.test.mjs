import test from "node:test"
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

const component = readFileSync(new URL("../src/components/WindowsStorageHealth.tsx", import.meta.url), "utf8")
const page = readFileSync(new URL("../src/pages/WindowsDevices.tsx", import.meta.url), "utf8")

test("storage health UI uses provider statuses, correlation and supported counters", () => {
  assert.match(component, /healthy|warning|failed|unknown/)
  assert.match(component, /correlation_status/)
  assert.match(component, /permission_denied|unsupported|unavailable|collection_failed/)
  assert.match(component, /temperature_max|wear|power_on_hours|unsafe_shutdown_count/)
})

test("storage health remains lazy, retryable and separated from inventory", () => {
  assert.match(component, /OPEN HEALTH/)
  assert.match(component, /RETRY/)
  assert.match(page, /<WindowsStorageHealth/)
  assert.match(page, /loadDiskHealth\(true\)/)
  assert.match(page, /setDiskHealth\(null\)/)
})
