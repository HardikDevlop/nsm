import test from "node:test"
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

const source = readFileSync(new URL("../src/unitFormatting.ts", import.meta.url), "utf8")
const windowsPage = readFileSync(new URL("../src/pages/WindowsDevices.tsx", import.meta.url), "utf8")
const windowsOverview = readFileSync(new URL("../src/components/WindowsDeviceOverview.tsx", import.meta.url), "utf8")

test("central unit utility exposes all required formatters and standards", () => {
  for (const name of ["formatBytesDecimal", "formatBytesBinary", "formatBitsPerSecond", "formatBytesPerSecond", "formatPercentage", "formatLatency", "formatUptime", "formatFrequency"]) {
    assert.match(source, new RegExp(`export function ${name}`))
  }
  assert.match(source, /\["B", "KB", "MB", "GB", "TB", "PB"\], 1000/)
  assert.match(source, /\["B", "KiB", "MiB", "GiB", "TiB", "PiB"\], 1024/)
  assert.match(source, /\["bps", "Kbps", "Mbps", "Gbps", "Tbps", "Pbps"\], 1000/)
  assert.match(source, /\["B\/s", "KiB\/s", "MiB\/s", "GiB\/s", "TiB\/s", "PiB\/s"\], 1024/)
})

test("unit utility guards invalid values and preserves zero", () => {
  assert.match(source, /Number\.isFinite\(value\)/)
  assert.doesNotMatch(source, /value \|\| 0/)
  assert.match(source, /value < 0 \? "-" : ""/)
})

test("unit utility covers requested boundary values", () => {
  for (const token of ["1024", "1000", "86400"]) assert.match(source, new RegExp(token))
})

test("Windows monitoring uses centralized presentation formatters", () => {
  assert.match(windowsPage, /from "\.\.\/unitFormatting"/)
  for (const name of ["formatBytesBinary", "formatBitsPerSecond", "formatBytesPerSecond", "formatPercentage", "formatLatency", "formatUptime", "formatFrequency"]) {
    assert.match(windowsPage, new RegExp(name))
  }
  assert.match(windowsOverview, /from "\.\.\/unitFormatting"/)
  assert.match(windowsOverview, /formatBytesBinary/)
  assert.match(windowsOverview, /formatUptime/)
})
