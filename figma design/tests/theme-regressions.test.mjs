import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { test } from "node:test"

const css = await readFile(new URL("../src/index.css", import.meta.url), "utf8")
const theme = await readFile(new URL("../src/components/ThemeContext.tsx", import.meta.url), "utf8")
const picker = await readFile(new URL("../src/components/ThemePicker.tsx", import.meta.url), "utf8")
const manual = await readFile(new URL("../src/pages/ManualTopology.tsx", import.meta.url), "utf8")

test("theme authority exposes light/dark semantic surface tokens", () => {
  assert.match(theme, /DARK_DEFAULTS/)
  assert.match(theme, /LIGHT_DEFAULTS/)
  assert.match(theme, /--t-text-secondary/)
  assert.match(theme, /--t-table-header/)
  assert.match(theme, /localStorage\.getItem\('theme-mode'\)/)
  assert.match(theme, /localStorage\.setItem\('theme-colors-v2'/)
  assert.match(picker, /setColor/)
  assert.match(theme, /bg: '#f1f5f9'/)
  assert.match(theme, /card: '#f8fafc'/)
  assert.match(theme, /const secondary = theme === 'light'/)
  assert.match(theme, /theme === 'light' \? '#e8eef5'/)
  assert.match(theme, /theme === 'dark' \? DARK_DEFAULTS : LIGHT_DEFAULTS/)
})

test("shared tables and MAC surfaces use theme-aware readability rules", () => {
  assert.match(css, /table thead[\s\S]*var\(--t-table-header\)/)
  assert.match(css, /table tbody tr:hover[\s\S]*var\(--t-table-row-hover\)/)
  assert.match(css, /snmp-collector-card[\s\S]*var\(--t-text\)/)
  assert.match(css, /snmp-mac-topology[\s\S]*var\(--t-text-secondary\)/)
})

test("Manual Topology health semantic colors remain intact", () => {
  assert.match(manual, /healthColor\(status: DeviceHealthStatus\)/)
  assert.match(manual, /status === "offline"\) return "#d9646a"/)
  assert.match(manual, /status === "degraded"\) return "#d4a95c"/)
  assert.match(manual, /renderedToneFor/)
})
