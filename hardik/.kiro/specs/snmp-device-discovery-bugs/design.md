# SNMP Device Discovery Bugs - Bugfix Design

## Overview

This design formalizes three interconnected bugs in the SNMP and mixed-protocol device discovery system:

1. **SNMPv3 Credentials Not Properly Formatted** - The SNMPClient constructs invalid UsmUserData when optional security parameters (auth_protocol, privacy_protocol) are None, causing SNMP queries to timeout.

2. **Device Deletion Logic Flaw During Mixed Discovery** - When SNMP discovery finds no SNMP-enabled devices and the endpoint throws an error, the database transaction partially commits, deleting ICMP-discovered devices.

3. **Frontend Form Not Dynamic for SNMPv3** - The discovery form treats IP address and subnet as independent fields rather than mutually exclusive discovery modes, forcing users to provide IP even when doing subnet-based SNMPv3 discovery.

The fixes are targeted, minimal, and preserve all existing behavior for SNMP v2c discovery and ICMP discovery workflows.

---

## Glossary

- **Bug_Condition_SNMP (C₁)**: SNMPv3 discovery with privacy_protocol=None or auth_protocol=None in UsmUserData construction
- **Bug_Condition_Device (C₂)**: SNMP discovery failing after ICMP discovery on same subnet, causing device deletion
- **Bug_Condition_Form (C₃)**: Frontend form requiring IP address when user selects SNMPv3 and provides only auth credentials
- **Property_SNMP (P₁)**: Fixed SNMPClient SHALL properly construct UsmUserData with optional fields omitted
- **Property_Device (P₂)**: Fixed discovery endpoint SHALL upsert devices without deleting existing records when SNMP finds no results
- **Property_Form (P₃)**: Fixed frontend form SHALL dynamically show/hide IP field based on SNMP version selection
- **Preservation**: All existing v2c discovery, ICMP discovery, and manual device addition workflows must remain unchanged
- **SNMPClient**: The class in `backend/snmp/client.py` that constructs pysnmp security objects and executes SNMP GET/WALK operations
- **SNMPDiscovery**: The class in `backend/snmp/collector.py` that orchestrates multi-domain SNMP collection
- **discovery_snmp()**: The endpoint function in `backend/api/discovery_routes.py` that handles POST /discovery/snmp requests
- **add_discovered_devices()**: The endpoint function that persists discovered devices to the database
- **UsmUserData**: pysnmp class that represents SNMPv3 User-based Security Model credentials

---

## Bug Details

### Bug Condition 1: SNMPv3 Credentials Construction

**The Bug:**
When SNMPClient._auth() receives SNMPv3 credentials with privacy_protocol=None or auth_protocol=None, it passes those None values directly to pysnmp's UsmUserData constructor. According to pysnmp documentation, optional parameters must be either valid protocol objects or omitted entirely - passing None breaks SNMP negotiation and causes timeouts.

**Current Code Flow (Buggy):**
```python
# In SNMPClient._auth() - backend/snmp/client.py
auth = getattr(hlapi, AUTH_PROTOCOLS[protocol_name(self.credentials.auth_protocol)], None) if self.credentials.auth_protocol else None
priv = getattr(hlapi, PRIVACY_PROTOCOLS[protocol_name(self.credentials.privacy_protocol)], None) if self.credentials.privacy_protocol else None

# Problem: If auth_protocol is provided but privacy_protocol is None, this creates:
return UsmUserData(username="", authKey=password, authProtocol=auth, privKey=None, privProtocol=None)
#                                                                                     ^^^^ None breaks pysnmp
```

**Root Cause:**
The UsmUserData constructor from pysnmp does not accept None for optional protocol parameters when they should be omitted. The current code conditionally sets auth/priv but still passes them even when the corresponding key/password is None.

**Formal Specification:**
```
FUNCTION isBugCondition_SNMPv3(credentials)
  INPUT: credentials of type SNMPCredentials
  OUTPUT: boolean
  
  RETURN credentials.is_v3 = True
         AND (credentials.auth_protocol IS NULL 
              OR credentials.privacy_protocol IS NULL)
         AND SNMPClient._auth() passes None to UsmUserData(privProtocol=None)
         AND SNMP async operation times out
END FUNCTION
```

### Bug Condition 2: Device Deletion During Mixed Discovery

**The Bug:**
The discovery_snmp() endpoint creates a database session and performs upsert operations on Device records for successful SNMP discoveries. However, when no SNMP devices respond (empty results dict), the endpoint throws an HTTPException 502 BEFORE committing the transaction. But if add_discovered_devices() was called before the error (from a chunked scan callback), the partial transaction may have soft-deleted devices that were discovered via other methods.

**Current Code Flow (Buggy):**
```python
# In discovery_snmp() - backend/api/discovery_routes.py
results = {ip: result for ip, result in zip(ips, scanned) if result.get("snmp_enabled")}
if not results:
    raise HTTPException(...)  # Returns error without rollback guarantee

# Earlier in chunked scan:
# If SNMP find 0 devices, add_discovered_devices() is called with []
# This function does soft-delete or delete operations
```

**Root Cause:**
The code path that calls add_discovered_devices() (via chunked scan callback) can leave the database in an inconsistent state when SNMP discovery fails. The upsert logic in discovery_snmp() doesn't explicitly prevent deletion of devices from other discovery methods.

**Formal Specification:**
```
FUNCTION isBugCondition_DeviceDeletion(discoveryWorkflow, dbState)
  INPUT: discoveryWorkflow = [ICMP discovery creates 10 devices, SNMP discovery finds 0 devices]
         dbState = [Device records with discovery_method='ICMP' exist]
  OUTPUT: boolean
  
  RETURN devices exist from prior ICMP discovery
         AND SNMP discovery returns no SNMP-enabled devices
         AND add_discovered_devices() is called with empty list
         AND Device.deleted_at becomes non-NULL for ICMP devices
END FUNCTION
```

### Bug Condition 3: Frontend Form Not Dynamic

**The Bug:**
The SNMPv3 discovery form on the frontend treats "IP address" and "subnet" as completely independent fields, both optional for all SNMP versions. However, SNMP discovery on the backend requires either IP or subnet. SNMPv3 discovery is only implemented for subnet-based scanning (via ThreadPoolExecutor), not single IP queries. This creates UX confusion where the form allows invalid combinations.

**Root Cause:**
The form doesn't implement conditional field visibility or validation based on selected SNMP version. SNMPv3 requires auth credentials but no IP, yet the form structure doesn't change based on this selection.

**Formal Specification:**
```
FUNCTION isBugCondition_FormNotDynamic(formState)
  INPUT: formState with snmp_version="SNMPv3", subnet="192.168.100.0/24", ip_address=""
  OUTPUT: boolean
  
  RETURN form validation fails even though backend would accept subnet-based SNMPv3 discovery
         AND IP address field is required when it should be optional for SNMPv3
         AND form does not dynamically show/hide fields based on snmp_version selection
END FUNCTION
```

---

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- SNMPv2c discovery with community strings SHALL continue to work exactly as currently implemented
- ICMP discovery SHALL continue to create Device records without any changes to that workflow
- Manual device addition via UI SHALL continue to work and devices SHALL NOT be affected by discovery operations
- All existing device records created before this fix SHALL remain in the database after the fix is applied
- Device credentials stored in DeviceCredential table SHALL continue to be created and updated as before
- Topology graph rendering SHALL continue to work for all non-deleted devices

**Scope:**
All discovery operations for SNMP v2c, ICMP, TCP, ARP, DNS, HTTP, SSH, and WMI protocols should be completely unaffected by fixes to SNMPv3 handling. The fixes are scoped strictly to:
1. SNMPv3 credential construction (only affects pysnmp UsmUserData creation)
2. Database upsert logic (only affects how SNMP discovery persists to DB, not other methods)
3. Frontend form field visibility (only affects SNMPv3 form, not other discovery forms)

---

## Hypothesized Root Cause

### SNMPv3 Timeout Failures

Based on code analysis, the root causes are:

1. **UsmUserData Parameter Handling**: The pysnmp library's UsmUserData class requires that optional protocol parameters (privProtocol, authProtocol) be either valid protocol objects OR completely omitted from the constructor call. The current code passes None, which breaks SNMP v3 negotiation.

2. **Incomplete v3 Credential Validation**: The SNMPCredentials dataclass validates that username exists for SNMPv3 but doesn't enforce that auth_protocol must be provided (auth_password with no auth_protocol is invalid for SNMPv3).

3. **Missing Support for Auth-Only Security**: SNMPv3 supports three security levels: noAuthNoPriv, authNoPriv, and authPriv. The current code doesn't properly handle the authNoPriv case where privacy_protocol should be None.

### Device Deletion During Mixed Discovery

1. **Weak Transaction Isolation**: The add_discovered_devices() function performs upsert operations without properly isolating from other discovery methods. When called with empty results, it may interpret this as "delete everything" rather than "add nothing".

2. **No Explicit Non-Deletion Semantics**: The endpoint discovery_snmp() doesn't explicitly mark devices as "discovered via SNMP" to prevent deletion of "non-SNMP" devices. All devices are treated equally regardless of discovery method.

3. **Error Path Without Rollback**: The HTTPException thrown when no SNMP devices are found doesn't guarantee transaction rollback if called from within a callback that already started a transaction.

### Frontend Form Not Dynamic

1. **Static Form Definition**: The form is built as a single static component with all fields always present, rather than conditional rendering based on SNMP version.

2. **Shared IP/Subnet Logic**: The backend accepts both IP and subnet parameters, but they're different discovery modes (single host vs. CIDR range). The form doesn't distinguish these properly.

3. **No SNMPv3-Specific Validation**: Frontend validation doesn't include SNMPv3-specific rules like "if SNMPv3, privacy_password is optional but auth_password is required".

---

## Correctness Properties

Property 1: Bug Condition - SNMPv3 Credentials Properly Formatted

_For any_ SNMPv3 discovery request where privacy_protocol is None (authentication-only security level), the fixed SNMPClient SHALL construct valid UsmUserData with only authProtocol specified and privProtocol completely omitted, and the SNMP query SHALL successfully retrieve system information without timing out.

**Validates: Requirements 2.1, 2.2, 2.3**

Property 2: Preservation - Device Data Preserved During Mixed Discovery

_For any_ mixed-protocol discovery workflow where ICMP discovery has created Device records and SNMP discovery subsequently runs on the same subnet with no SNMP-enabled devices found, the fixed discovery system SHALL preserve all ICMP-discovered Device records in the database with deleted_at=NULL, status unchanged, and all data intact. The SNMP endpoint SHALL return an appropriate error WITHOUT attempting to modify the database.

**Validates: Requirements 3.1, 3.2, 3.3, 5.1, 5.2**

Property 3: Bug Condition - Frontend Form Dynamic for SNMPv3

_For any_ SNMPv3 discovery form submission where a subnet is provided and IP address is left empty, the fixed frontend form SHALL allow submission, and the backend SHALL accept this as valid subnet-based SNMPv3 discovery without requiring an IP address.

**Validates: Requirements 4.1, 4.2**

---

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct, the fixes are:

**File**: `backend/snmp/client.py`

**Function**: `SNMPClient._auth()`

**Specific Changes**:

1. **Fix UsmUserData Construction for SNMPv3**:
   - Instead of passing None for optional protocol parameters, completely omit them from the constructor call
   - Use conditional kwargs building to only include authProtocol and privProtocol when they have valid values
   - Handle the three security levels: noAuthNoPriv (no auth/priv), authNoPriv (auth only), authPriv (auth + priv)

2. **Validate Auth/Privacy Combinations**:
   - Enforce that if privacy_protocol is specified, auth_protocol must also be specified
   - Allow privacy_protocol to be None while auth_protocol is specified (authNoPriv security level)

**File**: `backend/api/discovery_routes.py`

**Function**: `discovery_snmp()`

**Specific Changes**:

1. **Prevent Deletion During Empty Results**:
   - Before throwing the "No SNMP response" error, explicitly check if any device was modified
   - Only throw error after ensuring no database modifications occurred
   - Use explicit transaction management to guarantee rollback on error

2. **Add Discovery Method Tracking** (optional enhancement):
   - Consider adding a discovery_method field to Device model to track which protocol discovered each device
   - This prevents accidental deletion of devices discovered by other methods

**File**: `frontend/src/pages/ISPMonitoring.tsx` (or SNMPv3 discovery form location)

**Function**: SNMPv3 discovery form component

**Specific Changes**:

1. **Implement Dynamic Field Visibility**:
   - Make IP address field optional for SNMPv3 (subnet-based discovery is the primary path)
   - Make IP address field required for single-host SNMPv3 queries (if supported)
   - Show/hide privacy_password field based on whether user provides auth_password

2. **Add SNMPv3-Specific Validation**:
   - When SNMPv3 is selected and auth_password is provided, privacy_password becomes optional
   - When subnet is provided without IP address, allow submission for subnet-based discovery

---

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate each bug on unfixed code, then verify fixes work correctly and preserve existing behavior.

### Exploratory Bug Condition Checking - SNMP v3 Timeout

**Goal**: Surface counterexamples that demonstrate SNMPv3 discovery timeout on unfixed code. This confirms the UsmUserData construction is broken.

**Test Plan**: Write property-based tests that simulate SNMPv3 discovery with privacy_protocol=None and assert that the SNMP query completes without timeout. Run on UNFIXED code to observe timeout failures and understand the credential construction issue.

**Test Cases**:
1. **SNMPv3 AuthOnly Test**: Simulate SNMPv3 discovery with username, auth_protocol="MD5", auth_password="test123", privacy_protocol=None (will timeout on unfixed code)
2. **SNMPv3 AuthPriv Test**: Simulate SNMPv3 with both auth and privacy (will timeout if privProtocol parameter is incorrectly passed as None)
3. **SNMPv2c Regression Test**: Verify SNMPv2c with community="public" still works (should pass on both fixed and unfixed code)
4. **Invalid Auth Combination**: Attempt SNMPv3 with privacy_protocol specified but auth_protocol=None (should fail validation)

**Expected Counterexamples**:
- SNMPClient._auth() passes privProtocol=None to UsmUserData when privacy_protocol is None
- SNMP async operation times out instead of returning results for valid auth-only credentials
- Possible causes: UsmUserData parameter validation, pysnmp version incompatibility, missing protocol translation

### Exploratory Bug Condition Checking - Device Deletion

**Goal**: Surface counterexamples that demonstrate ICMP devices being deleted when SNMP discovery finds no results.

**Test Plan**: Write tests that create ICMP-discovered devices in the database, then run SNMP discovery that returns no results, and assert that ICMP devices remain in the database.

**Test Cases**:
1. **Mixed Discovery Sequence**: Discover 5 devices via ICMP, then run SNMP discovery on same subnet with 0 SNMP results (devices should NOT be deleted on unfixed code - will fail)
2. **Check Device Preservation**: Query database after failed SNMP discovery and verify ICMP-discovered devices still have deleted_at=NULL
3. **Transaction Isolation**: Verify that a failed SNMP discovery doesn't affect devices from other discovery methods
4. **Rollback Verification**: Ensure HTTPException 502 causes transaction rollback without partial commits

**Expected Counterexamples**:
- ICMP devices have deleted_at set after failed SNMP discovery
- Device count decreases after running SNMP discovery with no SNMP results
- Possible causes: add_discovered_devices() called with empty list and interpreted as "delete all", transaction not rolled back properly

### Fix Checking

**Goal**: Verify that for all SNMPv3 requests, the fixed SNMPClient properly constructs credentials and SNMP queries complete successfully.

**Pseudocode:**
```
FOR ALL credentials WHERE isBugCondition_SNMPv3(credentials) DO
  client := SNMPClient(credentials)
  auth := client._auth()
  // Verify auth contains only valid (non-None) protocol objects
  ASSERT auth is properly constructed
  
  // For SNMPv3 with privacy_protocol=None, verify privProtocol is omitted
  IF credentials.privacy_protocol IS NULL THEN
    ASSERT auth does not include privProtocol parameter
  END IF
  
  // Verify actual SNMP query succeeds
  result := client.get(test_device, OIDs)
  ASSERT result contains valid system information
  ASSERT no timeout occurred
END FOR
```

### Preservation Checking

**Goal**: Verify that for all non-SNMPv3 discovery workflows and existing devices, the fixed code produces the same behavior as before.

**Pseudocode:**
```
FOR ALL discoveryWorkflow WHERE NOT isBugCondition(discoveryWorkflow) DO
  // Existing behavior from before fix
  original_devices := database.query(Device).all()
  
  // Run same discovery on fixed code
  fixed_devices := database.query(Device).all()
  
  // Verify no changes to existing devices
  ASSERT original_devices = fixed_devices
  
  // Verify ICMP discovery still creates devices normally
  // Verify SNMPv2c discovery still works normally
  // Verify manual device addition not affected
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across discovery workflows
- It catches edge cases where one discovery method interferes with another
- It provides strong guarantees that behavior is unchanged for non-buggy inputs

**Test Plan**: 
1. Observe behavior on UNFIXED code for ICMP discovery on a subnet with 5 devices
2. Observe behavior on UNFIXED code for SNMPv2c discovery with valid community strings
3. Observe behavior on UNFIXED code for manual device addition via UI
4. Write property-based tests capturing observed behavior patterns
5. Verify tests PASS on UNFIXED code before implementing fixes

**Test Cases**:
1. **ICMP Discovery Preservation**: Run ICMP discovery, verify devices created with correct status/hostname. Run again and verify no duplicates created.
2. **SNMPv2c Discovery Preservation**: Run SNMPv2c discovery with valid community, verify devices discovered and credentials stored. Repeat and verify update not delete.
3. **Manual Device Addition Preservation**: Add device manually, run ICMP discovery on different subnet, verify manual device untouched.
4. **Mixed Sequential Discovery Preservation**: Run ICMP on subnet A, then SNMP on subnet B, verify both subnets have devices and nothing deleted.
5. **Topology Graph Rendering**: Load topology graph after mixed-protocol discovery, verify all devices displayed and connections correct.

### Unit Tests

- Test SNMPClient._auth() with various SNMPv3 credential combinations (auth-only, auth+priv, no auth)
- Test SNMPClient._auth() with SNMPv2c to ensure no regressions
- Test discovery_snmp() endpoint with empty SNMP results - verify HTTPException thrown but database unchanged
- Test add_discovered_devices() with partial device lists - verify only adds, never deletes from other methods
- Test frontend SNMPv3 form validation with various field combinations

### Property-Based Tests

- Generate random SNMPv3 credentials and verify SNMP queries complete without timeout
- Generate random discovery sequences (ICMP then SNMP, or reverse) and verify devices never deleted
- Generate random device mixes and verify topology graph renders correctly with all devices
- Generate random form submissions for SNMPv3 and verify accepted when valid, rejected when invalid

### Integration Tests

- Test full ICMP discovery workflow on live subnet with multiple devices
- Test full SNMPv3 discovery workflow on subnet with SNMPv3-enabled devices
- Test mixed workflow: ICMP discovery, then SNMPv3 discovery, verify both device sets merged in topology
- Test topology graph rendering after mixed-protocol discovery with 20+ devices
- Test UI form for SNMPv3 - verify IP field optional, privacy_password optional when auth_password provided

