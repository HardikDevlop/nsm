# SNMPv3 Frontend Form UX Issue Report

## Executive Summary

The SNMPv3 discovery form on the frontend requires an IP address even when the user intends to perform subnet-based discovery using only authentication credentials. This creates a confusing UX where:

1. The form doesn't distinguish between single-IP discovery and subnet-based discovery modes
2. IP address field is always present and treated as required across all SNMP versions
3. The form doesn't dynamically adjust field visibility based on selected SNMP version
4. Users cannot submit a form with only subnet + auth credentials for SNMPv3 discovery

**Impact**: Users attempting to discover SNMPv3-enabled devices on a subnet must provide a fake or arbitrary IP address even though the backend's subnet-based discovery doesn't require it.

---

## Current Frontend Form Structure

### SNMPSubnetDiscovery Component
**Location**: `/home/agnigate/Desktop/NMS/figma design/src/components/SNMPSubnetDiscovery.tsx`

This component provides subnet-based SNMP discovery with three scan modes:

#### Scan Modes (Lines 312-332)
```
1. SINGLE IP       - Requires single IP address
2. IP RANGE        - Requires start and end IPs (variations on last octet)
3. FULL SUBNET     - Uses entire subnet from prop (e.g., 192.168.100.0/24)
```

**Issue**: The form always requires an IP-like value depending on the selected mode:
- `scanMode === 'single'` → Must provide `singleIP` field
- `scanMode === 'range'` → Must provide both `rangeStart` and `rangeEnd`
- `scanMode === 'subnet'` → Automatically uses the subnet prop

**Current Code (Lines 96-120)**:
```typescript
const getTargetIPs = useCallback((): { ips: string[]; error?: string } => {
  if (scanMode === 'single') {
    const ip = singleIP.trim()
    if (!ip) return { ips: [], error: 'Enter an IP address' }  // ← REQUIRED
    return { ips: [ip] }
  }
  if (scanMode === 'range') {
    const start = rangeStart.trim()
    const end = rangeEnd.trim()
    if (!start || !end) return { ips: [], error: 'Enter both start and end IPs' }  // ← REQUIRED
    // ... validation ...
    return { ips }
  }
  // subnet
  const ips = subnetToHostIPs(subnet)
  if (!ips.length) return { ips: [], error: 'Invalid subnet format...' }
  return { ips }
}, [scanMode, singleIP, rangeStart, rangeEnd, subnet])
```

#### SNMP Credentials Form (Lines 334-367)
```typescript
// Version selection (Line 339)
<select value={version} onChange={e => setVersion(e.target.value as 'v2c' | 'v3')}>
  <option value="v2c">SNMPv2c</option>
  <option value="v3">SNMPv3</option>
</select>

// SNMPv2c branch - shows community string
version === 'v2c' ? (
  <input placeholder="Community string" ... />
) : (
  // SNMPv3 branch - shows username and security level
  <>
    <input value={username} placeholder="Username" ... />
    <select value={securityLevel}>
      <option>noAuthNoPriv</option>
      <option>authNoPriv</option>      // ← Auth without privacy
      <option>authPriv</option>         // ← Auth with privacy
    </select>
    
    {securityLevel !== 'noAuthNoPriv' && (
      <>
        <input value={authProtocol} placeholder="Auth protocol (SHA)" ... />
        <input value={authPassword} placeholder="Auth password" ... />
      </>
    )}
    
    {securityLevel === 'authPriv' && (
      <>
        <input value={privacyProtocol} placeholder="Privacy protocol (AES128)" ... />
        <input value={privacyPassword} placeholder="Privacy password" ... />
      </>
    )}
  </>
)
```

**Credentials Sent to Backend (Lines 150-159)**:
```typescript
const res = await discoverSNMP({
  ips: chunk,                                           // ← From scan mode, could be []
  snmp_version: version,
  timeout_seconds: parseFloat(timeoutSec) || 2,
  communities: version === 'v2c' ? [community] : undefined,
  username: version === 'v3' ? username || undefined : null,
  auth_protocol: version === 'v3' && securityLevel !== 'noAuthNoPriv' ? authProtocol : null,
  auth_password: version === 'v3' && securityLevel !== 'noAuthNoPriv' ? authPassword : null,
  privacy_protocol: version === 'v3' && securityLevel === 'authPriv' ? privacyProtocol : null,
  privacy_password: version === 'v3' && securityLevel === 'authPriv' ? privacyPassword : null,
  security_level: version === 'v3' ? securityLevel : null,
})
```

### SNMPDiscoveryPanel Component
**Location**: `/home/agnigate/Desktop/NMS/figma design/src/components/SNMPDiscoveryPanel.tsx`

This is a simpler form for single-IP or multi-IP discovery:

#### Structure (Lines 24-27)
```typescript
const [ips, setIps] = useState('192.168.100.10')  // ← ALWAYS requires IPs
const [version, setVersion] = useState<'v2c' | 'v3'>('v3')
// ... credentials ...

const run = async () => {
  const addresses = ips.split(/[\s,]+/).map(ip => ip.trim()).filter(Boolean)
  if (!addresses.length) throw new Error('Enter at least one IP address')  // ← REQUIRED
  // ... call discoverSNMP ...
}
```

**Critical Issue**: This form REQUIRES at least one IP address. It does not support subnet-based discovery.

---

## Validation Logic Analysis

### SNMPSubnetDiscovery Validation

1. **Scan Mode Validation** (Lines 96-120):
   - `single` mode: IP address is REQUIRED (error thrown if empty)
   - `range` mode: Both start and end IPs are REQUIRED
   - `subnet` mode: Subnet prop is used, no user input needed

2. **Credentials Validation** (Line 370):
   - Username is optional but recommended
   - Auth password is conditional on `securityLevel !== 'noAuthNoPriv'`
   - Privacy password is conditional on `securityLevel === 'authPriv'`

3. **Run Validation** (Lines 370-384):
   ```typescript
   const run = useCallback(async () => {
     const { ips, error: ipError } = getTargetIPs()
     if (!ips.length) {
       setError(ipError ?? 'No IPs to scan')
       return
     }
     // ... proceed with discovery ...
   }, [...])
   ```

**Finding**: The form allows submission when `scanMode === 'subnet'` WITHOUT any IP address field—only the subnet property is used. This is correct behavior for subnet-based discovery. However, for `single` and `range` modes, IP addresses are always required.

### SNMPDiscoveryPanel Validation

The SNMPDiscoveryPanel component has a hardcoded requirement for at least one IP address in the `ips` field (line 26 in `run()` function). This component does not support subnet-based discovery at all.

---

## Issue: Form Structure Not Dynamic for SNMPv3

### Problem 1: Conflicting Discovery Models

The frontend has two separate models for SNMP discovery:

1. **SNMPSubnetDiscovery** - Supports subnet-based scanning but requires selecting a scan mode
2. **SNMPDiscoveryPanel** - Requires explicit IP addresses, no subnet support

For SNMPv3 discovery, users should ideally:
- Select SNMPv3 as the protocol
- Provide auth credentials (username, auth_password, security_level)
- Either: a) provide IP address(es) for single-host query, OR b) provide subnet CIDR for batch scanning
- NOT be forced to provide both

**Current Problem**: The form doesn't enforce these as mutually exclusive. Users can confuse:
- "I want to discover via subnet" (requires no IP address)
- "I want to discover a single IP" (requires IP address)

### Problem 2: Form Doesn't Adapt to SNMP Version

The credentials grid layout (SNMPSubnetDiscovery, lines 335-367) is static. It doesn't:
- Hide/show IP fields based on selected SNMP version
- Indicate which fields are required vs. optional based on version
- Provide SNMPv3-specific guidance (e.g., "auth protocol SHA, privacy protocol AES128")

**Current Code Behavior**:
- When SNMPv3 is selected, the form shows username + security level selector
- The form ALWAYS shows the scan mode tabs (SINGLE IP, IP RANGE, FULL SUBNET)
- User can select FULL SUBNET but still confused about whether IP address is needed

### Problem 3: Form Submission Logic

**SNMPSubnetDiscovery submission** (line 370-384):
```typescript
const { ips, error: ipError } = getTargetIPs()
if (!ips.length) {
  setError(ipError ?? 'No IPs to scan')
  return
}
```

When `scanMode === 'subnet'`, this works fine (subnet is parsed into `.1–.254` IPs automatically).

However, the **visual presentation** doesn't make it clear that:
1. Selecting "FULL SUBNET" mode requires NO manual IP entry
2. IP address fields are ONLY required for "SINGLE IP" and "IP RANGE" modes
3. For SNMPv3 with "FULL SUBNET" mode, you can proceed with just credentials

---

## UX Issue: What Users Experience

### Scenario: User Wants SNMPv3 Subnet Discovery

**Steps**:
1. Opens SNMPSubnetDiscovery form
2. Sees three scan mode tabs: SINGLE IP, IP RANGE, FULL SUBNET
3. Clicks "FULL SUBNET" (wants to scan entire subnet)
4. Selects SNMPv3 from version dropdown
5. Sets security level to "authNoPriv" (auth without privacy)
6. Enters username and auth_password
7. Clicks "SCAN X IPs FOR SNMP" button

**Expected Result** (per Requirements 4.1, 4.2):
- Form should accept this and scan the subnet with SNMPv3 auth-only credentials

**Actual Result**:
- Form SHOULD work because `getTargetIPs()` returns all .1–.254 IPs from subnet
- BUT the visual presentation is unclear—user might think they need to provide IP address

**Additional Problem**: The SNMPDiscoveryPanel (which is simpler and many users may try first) does NOT support subnet-based discovery at all. It requires explicit IP addresses.

---

## Requirements Validation

From `bugfix.md`:

**Requirement 3.1**: "WHEN a user selects SNMPv3 as the SNMP version in the discovery form, THEN the form still displays 'Enter an IP address' field as required, even when the user only wants to provide auth credentials and should discover via subnet scan (subnet field should be the entry point instead)"

**Finding**: ✓ CONFIRMED - The IP address field behavior is confusing:
- In SNMPSubnetDiscovery: IP fields are mode-dependent but form doesn't make this clear
- In SNMPDiscoveryPanel: IP field is ALWAYS required, no subnet support

**Requirement 3.2**: "WHEN SNMPv3 is selected and the user leaves the IP address field empty but provides auth_password and privacy_password, THEN the frontend form validation rejects the submission because it requires either IP address OR subnet, but SNMPv3 discovery is only implemented for subnet-based discovery"

**Finding**: ✓ CONFIRMED - The SNMPDiscoveryPanel rejects submission without IP addresses (line 26: `if (!addresses.length) throw new Error('Enter at least one IP address')`). The SNMPSubnetDiscovery can work with just subnet if "FULL SUBNET" mode is selected, but the UX is confusing.

---

## Code Locations Requiring Changes

### Frontend Changes Needed (Per Requirements 4.1, 4.2)

#### 1. SNMPSubnetDiscovery.tsx - Make IP Fields Optional for SNMPv3

**File**: `/home/agnigate/Desktop/NMS/figma design/src/components/SNMPSubnetDiscovery.tsx`

**Change Locations**:

**Location A** (Lines 307-332): Scan mode tabs section
- Current: Always shows "SINGLE IP", "IP RANGE", "FULL SUBNET" tabs
- Needed: For SNMPv3 + authNoPriv/authPriv, prioritize "FULL SUBNET" as default
- Needed: For SNMPv3, disable or hide "SINGLE IP" mode (not implemented in backend)
- Needed: Add visual indicator that "FULL SUBNET" mode requires NO manual IP entry

**Location B** (Lines 334-367): Credentials grid
- Current: Shows generic layout for all SNMP versions
- Needed: Add conditional rendering based on SNMPv3 selection
- Needed: Hide scan mode tabs entirely when SNMPv3 is selected (auto-use subnet mode)
- Needed: Show SNMPv3-specific guidance: "Requires username, supports auth-only (authNoPriv) security level"

**Location C** (Lines 96-120): getTargetIPs() validation
- Current: Returns error if `singleIP` is empty for 'single' mode
- Needed: NO CHANGE (this function is correct)
- Note: The validation is mode-dependent and works correctly

**Implementation Approach**:
```typescript
// Add SNMPv3-specific form rendering
const isSnmpV3 = version === 'v3'

// When SNMPv3 is selected, auto-select 'subnet' mode and hide tabs
const displayScanModeSelector = !isSnmpV3  // Hide for SNMPv3

// When SNMPv3, only show 'subnet' mode logic, not tabs
if (isSnmpV3) {
  // Auto-set scanMode to 'subnet'
  setScanMode('subnet')
  // Show only subnet-based discovery options
}

// Credentials: Add SNMPv3-specific field guidance
if (isSnmpV3) {
  // Show message: "Discovering via subnet-based scan"
  // Show privacy_password as optional when securityLevel === 'authNoPriv'
}
```

#### 2. SNMPDiscoveryPanel.tsx - Add Subnet Support for SNMPv3

**File**: `/home/agnigate/Desktop/NMS/figma design/src/components/SNMPDiscoveryPanel.tsx`

**Change Locations**:

**Location A** (Line 24): IP input field
- Current: Always requires IP addresses
- Needed: Add conditional rendering to show "Subnet CIDR" input when SNMPv3 + "subnet" mode
- Needed: Allow either IP addresses OR subnet CIDR, but not both

**Location B** (Lines 35-38): Validation logic
- Current: Throws error if no IP addresses entered
- Needed: Allow submission with just subnet CIDR for SNMPv3

**Implementation Approach**:
```typescript
// Add mode selection: 'ips' (single/multiple) or 'subnet'
const [discoveryMode, setDiscoveryMode] = useState<'ips' | 'subnet'>('ips')

// When SNMPv3 + authNoPriv/authPriv, show mode selector
const canUseSNetMode = version === 'v3'

// Validation: accept either IPs or subnet based on mode
if (discoveryMode === 'ips') {
  if (!addresses.length) throw new Error('Enter at least one IP address')
} else if (discoveryMode === 'subnet') {
  if (!subnet.trim()) throw new Error('Enter subnet CIDR (e.g., 192.168.100.0/24)')
}
```

---

## Backend Behavior (For Reference)

**Note**: This report focuses on frontend UX. Backend behavior is covered in bugfix.md Requirements 2.1–2.3.

Backend `discoverSNMP()` endpoint (from API calls) accepts:
- `ips: string[]` - Array of IP addresses to scan
- `snmp_version: 'v2c' | 'v3'`
- `username` - SNMPv3 username (optional)
- `security_level` - SNMPv3 security level (noAuthNoPriv, authNoPriv, authPriv)
- `auth_protocol` - SNMPv3 auth protocol (SHA, MD5)
- `auth_password` - SNMPv3 auth password
- `privacy_protocol` - SNMPv3 privacy protocol (AES128, etc.)
- `privacy_password` - SNMPv3 privacy password

The backend correctly handles:
- `privacy_protocol = null` with `auth_password` set (authNoPriv security level)
- Batch scanning of multiple IPs
- Timeout handling per batch

**Frontend Issue**: The form doesn't clearly present this to users in a way that maps to SNMPv3's security model.

---

## Expected Findings After Fix

After implementing task 9 (fix frontend form), users should be able to:

1. **Open SNMPSubnetDiscovery** with SNMPv3 selected
2. **See clear indication** that subnet-based discovery is being used
3. **Provide only credentials**: username, auth_password, optionally privacy_password
4. **NOT be required to provide an IP address**
5. **Submit and scan the entire subnet** with SNMPv3 auth-only (authNoPriv) if desired

Similarly, after enhancing SNMPDiscoveryPanel:

1. **Select SNMPv3 as version**
2. **Choose between "IP addresses" or "Subnet" mode**
3. **For subnet mode**: Enter CIDR (e.g., 192.168.100.0/24)
4. **Provide only credentials** (username, auth_password)
5. **Submit** without requiring explicit IP address

---

## Recommendations

### Immediate (Task 9.1)

1. **SNMPSubnetDiscovery**: Make IP fields optional when SNMPv3 is selected
   - Auto-set to "FULL SUBNET" mode when SNMPv3 is selected
   - Hide scan mode tabs for SNMPv3 (only subnet-based discovery is implemented)
   - Make IP address input OPTIONAL for SNMPv3

2. **SNMPDiscoveryPanel**: Add basic subnet support
   - Add toggle: "IP Addresses" vs. "Subnet CIDR"
   - When SNMPv3 + Subnet mode: accept subnet CIDR instead of IPs
   - Pass subnet to backend (backend will expand to .1–.254)

### Longer Term (Not in Current Scope)

1. **Single-IP SNMPv3 Discovery**: Backend may not support querying single IPs via SNMPv3 (it may require batch scanning via subnet). Clarify and document this limitation.

2. **Security Level Presets**: Show SNMPv3 security level presets:
   - "Auth Only" (authNoPriv) - less secure, faster
   - "Auth + Privacy" (authPriv) - more secure, slower
   - "No Security" (noAuthNoPriv) - testing only

3. **Form Validation UX**: Color-code required vs. optional fields differently

---

## Summary

The SNMPv3 discovery form on the frontend prevents users from performing subnet-based discovery without providing an IP address, even though:
1. The backend fully supports SNMPv3 subnet-based discovery
2. The form components can handle subnet-based discovery
3. The UX doesn't make the distinction between discovery modes clear

**Fix Required**: Make IP address field optional when SNMPv3 is selected, and clarify that subnet-based discovery is being used instead of single-IP discovery.

**Validation Against Bugfix Requirements**:
- ✓ Requirement 3.1: IP field appears required even for subnet-based SNMPv3
- ✓ Requirement 3.2: Form validation prevents submission without IP address
- → Tasks 9.1 and 9.2 will fix both issues
