import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const page = await readFile(new URL('../src/pages/DeviceMonitoring.tsx', import.meta.url), 'utf8');

test('device monitoring does not render unknown live samples as down', () => {
  assert.match(page, /function liveStatusLabel\(status: string\)/);
  assert.match(page, /return 'WAIT'/);
  assert.match(page, /entry\.status === 'down' \? '#ff3366' : '#ffaa00'/);
});

test('device monitoring renders live status and latest check in the overview', () => {
  assert.match(page, /isMonitoring \? 'Enabled' : 'Disabled'/);
  assert.match(page, /effectiveStatus/);
  assert.match(page, /liveLastCheck \?\? device\.last_seen/);
  assert.match(page, /realStatusHistory = useMemo/);
  assert.match(page, /entry\.new_status === 'online'/);
  assert.match(page, /online\/offline transitions from database/);
  assert.match(page, /device\.ip_address} · \{entry\.old_status} → \{entry\.new_status}/);
});
