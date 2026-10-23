import test from "node:test"
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

const page = readFileSync(new URL("../src/pages/WindowsDevices.tsx", import.meta.url), "utf8")
const api = readFileSync(new URL("../src/lib/api.ts", import.meta.url), "utf8")

test("disk inventory API types and endpoint are present", () => {
  assert.match(api, /WindowsDiskInventoryPhysical/)
  assert.match(api, /WindowsDiskInventoryPartition/)
  assert.match(api, /modern_physical_disks/)
  assert.match(api, /hardware\/disks\/inventory/)
})

test("inventory UI renders disks, partitions, mappings and modern status", () => {
  assert.match(page, /Physical Disk Inventory/)
  assert.match(page, /Partitions/)
  assert.match(page, /No drive letter assigned/)
  assert.match(page, /Modern Storage Provider/)
  assert.match(page, /modern_status/)
})

test("inventory clears and guards device-scoped responses", () => {
  assert.match(page, /setDiskInventory\(null\)/)
  assert.match(page, /requestId === detailsRequest\.current\) setDiskInventory/)
  assert.match(page, /setDiskInventoryError/)
})
