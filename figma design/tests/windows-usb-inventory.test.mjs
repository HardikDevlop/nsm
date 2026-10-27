import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const page = await readFile(new URL('../src/pages/WindowsDevices.tsx', import.meta.url), 'utf8')
const api = await readFile(new URL('../src/lib/api.ts', import.meta.url), 'utf8')

test('Windows Details exposes a lazy USB tab and uses the USB endpoint', () => {
  assert.match(page, /"usb"/)
  assert.match(page, /activeDeviceTab === "usb"/)
  assert.match(page, /getWindowsUSBInventory\(deviceId\)/)
  assert.match(api, /\/windows\/devices\/\$\{deviceId\}\/usb/)
})

test('USB UI keeps presence, driver health, and physical connection separate', () => {
  assert.match(page, /presence_state/)
  assert.match(page, /driver_health/)
  assert.match(page, /Physical connection/)
  assert.match(page, /collection_errors/)
  assert.match(page, /Some USB inventory sources were unavailable/)
})

test('USB UI derives summary counts from returned devices and avoids polling', () => {
  assert.match(page, /const devices = Array\.isArray\(inventory\.usb\?\.devices\)/)
  assert.match(page, /const count = \(value: string\) => devices\.filter/)
  assert.match(page, /usbInFlight = useRef/)
  assert.doesNotMatch(page, /setInterval\([^)]*usb/i)
})

test('USB responses are validated before caching or rendering', () => {
  assert.match(page, /if \(value\.device_id !== deviceId\) throw new Error\("USB inventory response did not match the selected device"\)/)
  assert.match(page, /usbCache\.current\.set\(deviceId, value\)/)
  assert.match(page, /if \(requestId === detailsRequest\.current\) setUsbInventory\(value\)/)
  assert.match(page, /usbInFlight\.current\.get\(deviceId\)/)
})

test('USB hub summary distinguishes unavailable hubs from a successful zero count', () => {
  assert.match(page, /const hubUnavailable = inventory\.usb\?\.collection_errors\?\.some\(\(error\) => error\.source === "Win32_USBHub"\)/)
  assert.match(page, /<Tile label="Hubs" value=\{hubUnavailable \? "Unavailable" : hubs\.length\} \/>/)
  assert.match(page, /Some USB inventory sources were unavailable; showing the collected results/)
})

test('USB UI preserves and labels the Windows PnP class dynamically', () => {
  assert.match(page, /d\.device_class/)
  assert.match(page, /WPD: "WPD \(Portable Device\)"/)
  assert.match(page, /HIDClass: "HID"/)
  assert.match(page, /DiskDrive: "Disk Drive"/)
  assert.match(page, /Camera: "Camera"/)
  assert.match(page, /Bluetooth: "Bluetooth"/)
  assert.match(page, /labels\[value\] \?\? value/)
})

test('USB response validation preserves stale-request and error handling', () => {
  assert.match(page, /requestId === detailsRequest\.current\) setUsbError/)
  assert.match(page, /requestId === detailsRequest\.current\) setUsbLoading\(false\)/)
  assert.match(page, /usbCache\.current\.get\(deviceId\)/)
})

test('USB UI does not fabricate unsupported port or version fields', () => {
  assert.doesNotMatch(page, /Physical port|USB version|port_number|usb_version/i)
})
