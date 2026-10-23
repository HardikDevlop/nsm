import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'

const page = await readFile(new URL('../src/pages/WindowsDevices.tsx', import.meta.url), 'utf8')
const api = await readFile(new URL('../src/lib/api.ts', import.meta.url), 'utf8')
const details = await readFile(new URL('../src/pages/DeviceDetails.tsx', import.meta.url), 'utf8')
const vite = await readFile(new URL('../vite.config.ts', import.meta.url), 'utf8')

test('onboarding uses the authorized site list without requiring a site', () => {
  assert.match(page, /listSites\(\)/)
  assert.match(page, /No accessible sites/)
  assert.match(page, /Select an existing device or provide hostname and IP address/)
  assert.match(page, /\.\.\.\(form\.site_id \? \{ site_id: Number\(form\.site_id\) \} : \{\}\)/)
})

test('onboarding blocks normalized duplicate IP and hostname before device creation', () => {
  assert.match(page, /const norm = \(v: string\) => v\.trim\(\)\.toLowerCase\(\)/)
  assert.match(page, /findDuplicate/)
  assert.match(page, /setDuplicate\(d\)/)
  assert.match(page, /OPEN EXISTING DEVICE/)
})

test('new Windows devices retain the explicit classification marker', () => {
  assert.match(page, /topology_metadata:\s*\{\s*platform:\s*["']windows["']/)
  assert.match(api, /topology_metadata\?: Record<string, unknown>/)
})

test('existing Windows device details remain reachable by ID', () => {
  assert.match(page, /duplicate\.id/)
})

test('Windows credential API contracts use device-scoped URLs and matching update arguments', () => {
  assert.match(api, /\/windows\/devices\/\$\{deviceId\}\/credentials/)
  assert.match(api, /\/windows\/devices\/\$\{deviceId\}\/credentials\/\$\{credentialId\}/)
  assert.match(details, /updateWindowsCredential\(device\.id, credential\.id/)
  assert.match(api, /\/windows\/devices\/\$\{deviceId\}\/connection-test/)
})

test('existing credentials use metadata lookup and PATCH without returning secrets', () => {
  assert.match(page, /listWindowsCredentials\(device\.id\)/)
  assert.match(page, /existingCredential \? await updateWindowsCredential\(device\.id, existingCredential\.id/)
  assert.match(page, /!existingCredential && !form\.password/)
  assert.match(api, /export interface WindowsCredentialRecord/)
  assert.doesNotMatch(page, /credential\.secret/)
})

test('Windows credentials carry the dedicated connection host without requiring a password on update', () => {
  assert.match(page, /Connection Host \(DNS\/IP\)/)
  assert.match(page, /connection_host: form\.connection_host\.trim\(\) \|\| undefined/)
  assert.match(api, /connection_host\?: string \| null/)
  assert.match(api, /connection_host\?: string/)
  assert.match(details, /setConnectionHost\(current\?\.connection_host \?\? ""\)/)
  assert.match(details, /connection_host: connectionHost\.trim\(\) \|\| undefined/)
})

test('credential conflicts refresh metadata for an update retry', () => {
  assert.match(page, /already\|409\|processing/)
  assert.match(page, /const rows = await listWindowsCredentials\(device\.id\)/)
  assert.match(page, /An existing credential was found/)
})

test('development port 8443 proxies Windows routes to backend', () => {
  assert.match(vite, /port: parseInt\(process\.env\.PORT \|\| '8443'\)/)
  assert.match(vite, /['"]\/windows['"]:\s*\{[\s\S]*?target: ['"]http:\/\/127\.0\.0\.1:8000['"]/) 
  assert.match(vite, /startsWith\('\/windows\/'\)/)
  assert.match(vite, /\/windows-devices/)
})

test('the four module buttons fetch only their selected metric', () => {
  assert.match(page, /"system",\s*"cpu",\s*"memory",\s*"disk"/) 
  assert.doesNotMatch(page, /"network",\s*"services",\s*"processes",\s*"events"/) 
  assert.match(page, /onClick=\{\(\) => void fetchMetric\(module\)\}/)
  assert.match(api, /`\/windows\/devices\/\$\{deviceId\}\/metrics\/\$\{module\}\/fetch`/) 
  assert.match(api, /method: "POST"/) 
})

test('opening MORE and loading saved data use GETs only', () => {
  const openDetails = page.match(/const openDetails = async[\s\S]*?\n  \}/)?.[0] ?? ''
  assert.match(openDetails, /getWindowsMetric\(device\.id, module\)/)
  assert.doesNotMatch(openDetails, /fetchWindowsMetric|fetchWindowsSystemInfo/)
  assert.match(api, /`\/windows\/devices\/\$\{deviceId\}\/metrics\/\$\{module\}`/) 
})

test('module state is independent and failed fetches retain saved data', () => {
  assert.match(page, /metricState\[module\] === "loading"/)
  assert.match(page, /setMetrics\(\(current\) => \(\{ \.\.\.current, \[module\]: result \}\)\)/)
  assert.match(page, /metricErrors\[module\]/)
  assert.match(page, /metrics\[module\]\?\.collected_at/)
  assert.match(page, /formatBytes\(/)
})

test('network table labels and displays interface identity without treating zero as missing', () => {
  assert.match(page, /"Interface Index"/)
  assert.match(page, /adapter\.interface_index \?\? "N\/A"/)
  assert.match(page, /adapter\.adapter_index != null/)
  assert.match(page, /Adapter \{adapter\.adapter_index\}/)
})

