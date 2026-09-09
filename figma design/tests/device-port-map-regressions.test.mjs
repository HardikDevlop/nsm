import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const page = await readFile(
  new URL('../src/pages/DevicePortMap.tsx', import.meta.url),
  'utf8',
);

test('device port map uses the supplied plug asset for every port socket', () => {
  assert.match(page, /import plugUltraAsset from "\.\.\/assets\/plug-ultra\.png"/);
  assert.match(page, /className="h-full w-full rotate-180 object-contain"/);
});

test('device port map renders a fallback port when no interfaces are returned', () => {
  assert.match(page, /function fallbackPort\(device: Device\)/);
  assert.match(page, /setPorts\(manualPorts\.length \? manualPorts : \[fallbackPort\(current\)\]\)/);
  assert.match(page, /rows\.length \? rows : \[fallbackPort\(current\)\]/);
});
