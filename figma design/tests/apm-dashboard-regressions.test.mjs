import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const page = await readFile(new URL('../src/pages/APM.tsx', import.meta.url), 'utf8');
const api = await readFile(new URL('../src/lib/api.ts', import.meta.url), 'utf8');
const routes = await readFile(new URL('../src/routes.tsx', import.meta.url), 'utf8');
const sidebar = await readFile(new URL('../src/components/Sidebar.tsx', import.meta.url), 'utf8');

test('APM dashboard uses stored metric and dependency APIs with all filters', () => {
  assert.match(api, /getAPMOverview\(filters: APMFilters\)/);
  assert.match(api, /getAPMServiceMetrics\(serviceId: number, filters: APMFilters\)/);
  assert.match(api, /getAPMDependencies\(filters: APMFilters\)/);
  assert.match(page, /getAPMOverview\(filters\)/);
  assert.match(page, /getAPMServiceMetrics\(serviceId!, filters\)/);
  assert.match(page, /getAPMDependencies\(filters\)/);
  assert.match(page, /Application filter/);
  assert.match(page, /Service filter/);
  assert.match(page, /Device filter/);
  assert.match(page, /Site filter/);
  assert.match(page, /Time range/);
});

test('APM dashboard avoids automatic refresh polling', () => {
  assert.match(page, /staleTime: 30_000/);
  assert.match(page, /refetchOnWindowFocus: false/);
  assert.match(page, /refetchOnMount: false/);
  assert.doesNotMatch(page, /refetchInterval/);
  assert.match(page, /No stored APM metrics/);
  assert.match(page, /No stored dependencies/);
});

test('APM dashboard route and navigation are RBAC protected', () => {
  assert.match(routes, /path: 'apm', Component: withPermission\(APM, 'apm:read'\)/);
  assert.match(sidebar, /APM Service Health/);
  assert.match(sidebar, /permission: 'apm:read'/);
});
