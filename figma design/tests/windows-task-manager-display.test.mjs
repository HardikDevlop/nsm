import assert from "node:assert/strict"
import { after, test } from "node:test"
import fs from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import ts from "typescript"

const temp = await fs.mkdtemp(path.join(os.tmpdir(), "nms-task-manager-display-"))
const transpile = async (file) => ts.transpileModule(await fs.readFile(new URL(`../src/${file}`, import.meta.url), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText
await fs.writeFile(path.join(temp, "unitFormatting.mjs"), await transpile("unitFormatting.ts"))
const display = (await transpile("lib/windowsTaskManagerDisplay.ts"))
  .replace('from "../unitFormatting"', 'from "./unitFormatting.mjs"')
  .replace('from "./api"', 'from "./api.mjs"')
await fs.writeFile(path.join(temp, "windowsTaskManagerDisplay.mjs"), display.replace(/import type .*\n/, ""))
await fs.writeFile(path.join(temp, "api.mjs"), "export {}")
const helpers = await import(`file://${path.join(temp, "windowsTaskManagerDisplay.mjs")}`)
after(async () => fs.rm(temp, { recursive: true, force: true }))

const statuses = ["ok", "no_snapshot", "stale", "collection_in_progress", "refresh_cooldown", "concurrency_limit", "collection_timeout", "collection_failed", "busy", "connection_error", "lock_lost", "release_error", "shutting_down"]

test("every supported snapshot status has safe presentation metadata", () => {
  for (const status of statuses) {
    const result = helpers.presentTaskManagerStatus(status)
    assert.ok(result.label)
    assert.ok(result.explanation)
    assert.equal(typeof result.retry, "boolean")
    assert.equal(typeof result.showCachedData, "boolean")
  }
  assert.equal(helpers.presentTaskManagerStatus("future_status").label, "Unavailable")
})

test("CPU presentation preserves null, zero, and explicit unavailable states", () => {
  assert.equal(helpers.presentProcessCPU("warming_up", null).text, "Warming up")
  assert.equal(helpers.presentProcessCPU("unavailable", null).text, "Unavailable")
  assert.equal(helpers.presentProcessCPU("terminated", null).text, "Terminated")
  assert.equal(helpers.presentProcessCPU("ok", null).text, "Unavailable")
  assert.equal(helpers.presentProcessCPU("ok", 0).text, "0.0%")
  assert.equal(helpers.presentProcessCPU("ok", 12.5).text, "12.5%")
})

test("display formatters handle bytes, age, timestamps, and missing values safely", () => {
  assert.equal(helpers.formatTaskManagerMemory(1024), "1.0 KiB")
  assert.equal(helpers.formatTaskManagerMemory(null), "Unavailable")
  assert.equal(helpers.formatTaskManagerAge(0), "0s ago")
  assert.equal(helpers.formatTaskManagerAge(65), "1m ago")
  assert.equal(helpers.formatTaskManagerAge(-1), "Unavailable")
  assert.equal(helpers.formatTaskManagerTimestamp("invalid"), "Unavailable")
  assert.equal(helpers.formatTaskManagerValue(null), "Unavailable")
  assert.equal(helpers.formatTaskManagerValue("MysteryState"), "MysteryState")
})

test("status presentations do not expose backend reasons or sensitive details", () => {
  const result = helpers.presentTaskManagerStatus("collection_failed")
  assert.doesNotMatch(result.explanation, /password|credential|winrm|sql|exception|secret/i)
})
