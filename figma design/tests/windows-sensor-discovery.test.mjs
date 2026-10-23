import test from "node:test"
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

const page = readFileSync(new URL("../src/pages/WindowsDevices.tsx", import.meta.url), "utf8")
const api = readFileSync(new URL("../src/lib/api.ts", import.meta.url), "utf8")

test("native sensor discovery calls the device-scoped backend endpoint", () => {
  assert.match(api, /hardware\/sensors\/discover/)
  assert.match(page, /discoverWindowsHardwareSensors\(deviceId\)/)
  assert.match(page, /DISCOVER NATIVE SENSORS/)
})

test("sensor UI renders backend statuses and organized categories", () => {
  assert.match(page, /Temperature Sensors/)
  assert.match(page, /Fan Sensors/)
  assert.match(page, /Voltage Sensors/)
  assert.match(page, /Unsupported \/ Unavailable Sensors/)
  assert.match(page, /Permission Denied/)
  assert.match(page, /Not Supported/)
  assert.match(page, /Unavailable/)
  assert.match(page, /GPU Temperature/)
  assert.match(page, /Storage Temperature/)
  assert.match(page, /sensorProviders/)
})

test("sensor values are not fabricated and stale device data is cleared", () => {
  assert.match(page, /setNativeSensors\(\[\]\)/)
  assert.match(page, /result\.device_id === deviceId/)
  assert.match(page, /sensor\.value == null/)
  assert.doesNotMatch(page, /sensor\.value \|\| 0/)
})

test("refresh and loading states are wired to discovery", () => {
  assert.match(page, /disabled=\{sensorLoading\}/)
  assert.match(page, /setSensorLoading\(true\)/)
  assert.match(page, /Discovering native sensors/)
  assert.match(page, /Last updated:/)
})
