import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const page = await readFile(new URL('../src/pages/CMDB.tsx', import.meta.url), 'utf8');
const api = await readFile(new URL('../src/lib/api.ts', import.meta.url), 'utf8');
const routes = await readFile(new URL('../src/routes.tsx', import.meta.url), 'utf8');
const sidebar = await readFile(new URL('../src/components/Sidebar.tsx', import.meta.url), 'utf8');

test('CMDB dashboard uses real inventory, relationship and history APIs', () => {
  assert.match(api, /listCMDBItems\(filters: CMDBItemFilters/);
  assert.match(api, /getCMDBRelationships\(ciId: number\)/);
  assert.match(api, /getCMDBHistory\(ciId: number\)/);
  assert.match(page, /listCMDBItems\(/);
  assert.match(page, /getCMDBRelationships\(selected!\.id\)/);
  assert.match(page, /getCMDBHistory\(selected!\.id\)/);
  assert.match(page, /CI Inventory/);
  assert.match(page, /Dependency Graph/);
  assert.match(page, /Change History/);
});

test('CMDB dashboard supports server-side filters without polling', () => {
  assert.match(page, /Search CMDB/);
  assert.match(page, /CI type filter/);
  assert.match(page, /Lifecycle filter/);
  assert.match(page, /Device filter/);
  assert.match(page, /Site filter/);
  assert.match(page, /refetchOnWindowFocus: false/);
  assert.match(page, /refetchOnMount: false/);
  assert.doesNotMatch(page, /refetchInterval/);
});

test('CMDB dashboard route and navigation use cmdb read permission', () => {
  assert.match(routes, /path: 'cmdb', Component: withPermission\(CMDB, 'cmdb:read'\)/);
  assert.match(sidebar, /label: 'CMDB'/);
  assert.match(sidebar, /permission: 'cmdb:read'/);
});
