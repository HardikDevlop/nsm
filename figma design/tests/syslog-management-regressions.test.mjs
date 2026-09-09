import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

const root = new URL('../src/', import.meta.url)
const read = name => fs.readFileSync(new URL(name, root), 'utf8')
const page = read('pages/SyslogManagement.tsx')
const api = read('lib/api.ts')
const routes = read('routes.tsx')
const sidebar = read('components/Sidebar.tsx')

test('Syslog has a dedicated permission-gated route and navigation entry', () => {
  assert.match(routes, /path: 'syslog', Component: withPermission\(SyslogManagement, 'syslog:read'\)/)
  assert.match(sidebar, /to: '\/syslog', label: 'Syslog Management'/)
  assert.match(sidebar, /'\/syslog': \(\) => import\('\.\.\/pages\/SyslogManagement'\)/)
  assert.match(routes, /const SyslogManagement = lazyRetry\(\(\) => import\('\.\/pages\/SyslogManagement'\)\)/)
})

test('event list uses the real paginated Syslog records API and all requested filters', () => {
  assert.match(api, /requestJson<SyslogRecordsResponse>\(`\/syslog\/records\?\$\{query\.toString\(\)\}`\)/)
  for (const field of ['start', 'end', 'device_id', 'source_ip', 'hostname', 'severity', 'facility', 'application', 'pattern', 'limit', 'offset']) {
    assert.match(page, new RegExp(`(?:filters\\.${field}|${field}:|\\b${field}\\b)`))
  }
  assert.match(page, /PAGE_SIZE = 50/)
  assert.match(page, /total = records\.data\?\.total/)
  assert.match(page, /newest event first|received_at|event_timestamp/)
  assert.match(page, /invalidateNmsGetCache\(\); void records\.refetch\(\)/)
})

test('details and severity handling are real-data safe', () => {
  for (const field of ['event_timestamp', 'received_at', 'source_ip', 'hostname', 'application', 'process_id', 'message_id', 'structured_data', 'message', 'raw_message', 'alert_id', 'incident_id']) assert.match(page, new RegExp(`event\\.${field}`))
  assert.match(page, /return value === null \|\| value === undefined \|\| value === '' \? 'N\/A'/)
  assert.match(api, /Emergency.*Alert.*Critical.*Error.*Warning.*Notice.*Informational.*Debug/s)
  assert.match(page, /navigate\('\/alerts'\)/)
  assert.match(page, /navigate\('\/incidents'\)/)
})

test('rules and retention use existing backend APIs with confirmation for destructive actions', () => {
  for (const endpoint of ['/syslog/rules', '/syslog/retention/cleanup']) assert.match(api, new RegExp(endpoint.replace('/', '\\/')))
  for (const action of ['createSyslogRule', 'updateSyslogRule', 'deleteSyslogRule', 'setSyslogRuleEnabled', 'cleanupSyslog']) assert.match(page, new RegExp(action))
  assert.match(page, /confirmDanger/)
  assert.match(page, /hasPermission\('syslog:manage'\)/)
})

test('Syslog page does not add polling, websocket connections, or static event fixtures', () => {
  assert.doesNotMatch(page, /refetchInterval|setInterval|WebSocket|EventSource/)
  assert.doesNotMatch(page, /mock|fixture|staticEvents|sampleEvents/)
})
