import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

const api = fs.readFileSync('src/lib/api.ts', 'utf8')
const page = fs.readFileSync('src/pages/ConfigurationBackups.tsx', 'utf8')
const routes = fs.readFileSync('src/routes.tsx', 'utf8')

test('configuration backup UI uses live version and checksum APIs', () => {
  assert.match(api, /captureConfiguration/)
  assert.match(api, /listConfigurationVersions/)
  assert.match(page, /checksum/)
  assert.match(page, /Configuration history/)
  assert.match(routes, /withPermission\(ConfigurationBackups, 'config_backups:read'\)/)
})
