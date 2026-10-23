import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

const page = fs.readFileSync(new URL('../src/pages/WindowsDevices.tsx', import.meta.url), 'utf8')
const details = fs.readFileSync(new URL('../src/pages/DeviceDetails.tsx', import.meta.url), 'utf8')
const helper = fs.readFileSync(new URL('../src/lib/windowsClassification.ts', import.meta.url), 'utf8')

test('generic Windows onboarding persists an explicit platform marker', () => {
  assert.match(page, /platform:\s*["']windows["']/)
})

test('Windows Devices and Device Details share classification helper', () => {
  assert.match(page, /from ["']\.\.\/lib\/windowsClassification["']/)
  assert.match(details, /from ["']\.\.\/lib\/windowsClassification["']/)
  assert.match(helper, /platform.*windows/i)
})

test('legacy Windows metadata remains compatible', () => {
  assert.match(helper, /windows\|microsoft\|win32\|desktop-\|workstation/)
})

test('generic non-Windows hostnames are not classified by broad patterns', () => {
  assert.doesNotMatch(helper, /office-pc|router|switch/i)
})

test('classification survives refreshed DeviceRecord metadata', () => {
  assert.match(helper, /topology_metadata/)
  assert.match(helper, /live\.device_type/)
})
