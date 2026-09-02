import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const page = await readFile(new URL('../src/pages/FlowAnalytics.tsx', import.meta.url), 'utf8');
const api = await readFile(new URL('../src/lib/api.ts', import.meta.url), 'utf8');
const routes = await readFile(new URL('../src/routes.tsx', import.meta.url), 'utf8');
const sidebar = await readFile(new URL('../src/components/Sidebar.tsx', import.meta.url), 'utf8');

test('flow analytics page uses the real analytics API with shared filters', () => {
  assert.match(api, /export async function getFlowAnalytics\([\s\S]*?filters: FlowAnalyticsFilters/);
  assert.match(api, /export async function getFlowTrends\(filters: FlowAnalyticsFilters\)/);
  assert.match(page, /getFlowAnalytics\(dimension, filters\)/);
  assert.match(page, /getFlowTrends\(filters\)/);
  assert.match(page, /Traffic Overview/);
  assert.match(page, /device_id: deviceId/);
  assert.match(page, /site_id: siteId/);
  assert.match(page, /Time range/);
});

test('flow analytics page requests once through React Query without polling', () => {
  assert.match(page, /queryKey: \['flow-analytics', filters\]/);
  assert.match(page, /refetchOnWindowFocus: false/);
  assert.match(page, /refetchOnMount: false/);
  assert.doesNotMatch(page, /refetchInterval/);
  assert.match(page, /getFlowTrends\(filters\)/);
});

test('flow analytics is exposed only to users with flow read permission', () => {
  assert.match(routes, /FlowAnalytics/);
  assert.match(routes, /withPermission\(FlowAnalytics, 'flows:read'\)/);
  assert.match(sidebar, /Flow Analytics/);
  assert.match(sidebar, /permission: 'flows:read'/);
});
