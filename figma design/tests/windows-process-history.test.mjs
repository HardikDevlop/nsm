import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"

const panel = await readFile(new URL("../src/components/windows/WindowsProcessesPanel.tsx", import.meta.url), "utf8")
const api = await readFile(new URL("../src/lib/api.ts", import.meta.url), "utf8")

test("process history uses the existing bounded list and detail APIs", () => {
  assert.match(api, /getWindowsProcessHistory\(/)
  assert.match(api, /processes\/history\$\{suffix\}/)
  assert.match(api, /getWindowsProcessHistoryDetail\(/)
  assert.match(api, /processes\/history\/\$\{snapshotId\}/)
  assert.match(panel, /getWindowsProcessHistory\(deviceId/)
  assert.match(panel, /getWindowsProcessHistoryDetail\(deviceId, selected\)/)
})

test("history UI supports list/detail navigation, search, sorting, pagination, and local time", () => {
  for (const token of ["HISTORY", "SNAPSHOT LIST", "Collection Time", "Total Processes", "Snapshot ID", "History process search", "History sort", "TablePagination", "toLocaleString"]) assert.match(panel, new RegExp(token.replace(/[{}]/g, "\\$&")))
  assert.match(panel, /Search name or PID/)
  assert.match(panel, /setDetailPage\(1\)/)
  assert.match(panel, /second: "2-digit"/)
})

test("history UI preserves CPU semantics and missing values", () => {
  assert.match(panel, /Warming up/)
  assert.match(panel, /Not available/)
  assert.match(panel, /cpu_status !== "ok"/)
  assert.match(panel, /System Idle Process/)
  assert.match(panel, /CPU Idle Time/)
  assert.match(panel, /value == null/)
})
