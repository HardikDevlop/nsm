import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'

const page = fs.readFileSync(new URL('../src/features/snmp/pages/SNMPGenericModulePage.tsx', import.meta.url), 'utf8')
const hook = fs.readFileSync(new URL('../src/features/snmp/modules/useSNMPModules.ts', import.meta.url), 'utf8')
const api = fs.readFileSync(new URL('../../hardik/backend/api/snmp_device_routes.py', import.meta.url), 'utf8')

test('MAC table uses the authoritative module endpoint instead of the metrics snapshot', () => {
  assert.match(page, /useModuleData\(id, isMacTable \? 'mac_table' : null\)/)
  assert.match(page, /useMonitoringData\(id, !isMacTable\)/)
  assert.match(hook, /enabled: !!deviceId && enabled/)
})

test('MAC table refreshes while the page remains open', () => {
  assert.match(hook, /refetchInterval: refetchIntervalSeconds \? refetchIntervalSeconds \* 1000 : false/)
  assert.match(hook, /refetchIntervalInBackground: false/)
  assert.match(hook, /refetchOnReconnect: true/)
})

test('MAC table API enriches canonical FDB groups from ARP without guessing IPs', () => {
  assert.match(api, /get_snmp_mac_table/)
  assert.match(api, /The scheduler persists both domains/)
  assert.doesNotMatch(api.slice(api.indexOf('def get_snmp_mac_table'), api.indexOf('def get_snmp_inventory')), /_live_collect\(/)
  assert.match(api, /_normalize_mac\(arp_entry\.get\(["']mac["']\)\)/)
  assert.match(api, /data_quality/)
  assert.match(api, /last_good_timestamp/)
  assert.match(api, /collection_status/)
  assert.match(api, /arp_by_mac\.setdefault\(mac, \[\]\)\.append/)
})

test('MAC table UI normalizes MACs, shows quality, and exposes manual refresh', () => {
  const card = fs.readFileSync(new URL('../src/features/snmp/components/SNMPCollectorDataCard.tsx', import.meta.url), 'utf8')
  assert.match(card, /function normalizeMac/)
  assert.match(card, /DATA PARTIAL/)
  assert.match(card, /REFRESHING\.\.\./)
  assert.match(page, /refetchMacTable/)
})

test('self FDB entries are removed before port groups are returned', () => {
  const collector = fs.readFileSync(new URL('../../hardik/backend/snmp/collectors/mac_table.py', import.meta.url), 'utf8')
  assert.match(collector, /entries = \[entry for entry in entries if entry\.get\("status"\) != "self"\]/)
  assert.match(collector, /self[\s\S]*not a connected host/i)
})
