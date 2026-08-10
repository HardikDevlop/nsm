# Implementation Plan - SNMP Device Discovery Bugs

## Phase 1: Explore and Understand Bugs

- [x] 1. Write SNMPv3 timeout exploration test
  - **Property 1: Bug Condition** - SNMPv3 Credentials with Privacy Protocol None
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists with UsmUserData construction
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate SNMPv3 discovery timeout when privacy_protocol=None
  - **Scoped PBT Approach**: For deterministic bugs, scope the property to concrete failing cases: SNMPv3 with auth_protocol="MD5", auth_password="test123", privacy_protocol=None
  - Test implementation:
    - Create SNMPClient with SNMPv3 credentials where privacy_protocol=None (auth-only security level)
    - Call _auth() and verify it constructs UsmUserData without privProtocol parameter
    - Attempt SNMP GET query on a reachable test device and verify it completes without timeout
  - The test assertions should match Expected Behavior from design (Property 1)
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS with timeout or invalid credential error (this confirms the bug exists)
  - Document counterexamples found: "SNMPClient._auth() passes privProtocol=None to UsmUserData, causing SNMP query to timeout"
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.2, 1.3, 2.1, 2.2, 2.3_

- [x] 2. Write device deletion exploration test
  - **Property 1: Bug Condition** - ICMP Devices Deleted During SNMP Discovery
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms devices are being deleted
  - **GOAL**: Surface counterexamples that demonstrate ICMP-discovered devices being deleted when SNMP finds no results
  - **Scoped PBT Approach**: Scope the property to concrete failing case: Create 5 ICMP devices, then run SNMP discovery with 0 SNMP results
  - Test implementation:
    - Seed database with 5 Device records created as if from ICMP discovery (status="online", no SNMP credentials, last_seen set)
    - Call discovery_snmp() endpoint with subnet that returns 0 SNMP-enabled devices
    - Query database and verify ICMP devices still have deleted_at=NULL, status="online", all data unchanged
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS - ICMP devices have deleted_at set or status changed (this confirms bug exists)
  - Document counterexamples found: "Running SNMP discovery with 0 results deletes ICMP-discovered devices from previous discovery"
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 2.1, 2.2, 2.3_

- [x] 3. Document SNMPv3 form UX issue
  - **Goal**: Manually verify that frontend SNMPv3 discovery form requires IP address even when subnet is provided
  - **Test Approach**: 
    - Open SNMPv3 discovery form on frontend
    - Select SNMPv3 as protocol
    - Provide subnet (e.g., 192.168.100.0/24) and auth credentials
    - Leave IP address empty
    - Attempt to submit
  - **EXPECTED OUTCOME**: Form validation error "IP address is required" (this confirms frontend bug exists)
  - Document the issue: "Frontend form prevents SNMPv3 discovery when using subnet-based scanning without an IP address"
  - Mark task complete when issue is verified and documented
  - _Requirements: 3.1, 3.2_

---

## Phase 2: Preservation Tests (BEFORE Implementing Fix)

- [x] 4. Write SNMPv2c discovery preservation test
  - **Property 2: Preservation** - SNMPv2c Discovery Continues to Work
  - **IMPORTANT**: Follow observation-first methodology
  - Observe behavior on UNFIXED code:
    - Run SNMPv2c discovery with community="public" on a reachable device with SNMP v2c enabled
    - Observe that devices are discovered and DeviceCredential records are created with snmp_version="v2c"
    - Run discovery again and observe devices are updated, not duplicated
  - Write property-based test:
    - Generate random SNMPv2c community strings and test device subnet ranges
    - For each combination: assert that SNMP discovery either creates new Device or updates existing one
    - Assert that discovered devices always have valid DeviceCredential with snmp_version="v2c"
    - Assert that running discovery twice on same subnet doesn't create duplicates
  - Verify tests PASS on UNFIXED code (this is the baseline we must preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 5.2, 5.3_

- [x] 5. Write ICMP discovery preservation test
  - **Property 2: Preservation** - ICMP Discovery Behavior Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - Observe behavior on UNFIXED code:
    - Run ICMP discovery on a subnet with reachable devices
    - Observe that Device records are created with status="online", hostname generated
    - Observe that no DeviceCredential records are created (ICMP doesn't require credentials)
    - Run ICMP discovery again and observe devices are not duplicated or deleted
  - Write property-based test:
    - Generate random subnets and reachable IP sets
    - For each: assert ICMP discovery creates Device records only (no credentials)
    - Assert running ICMP discovery multiple times doesn't delete or duplicate devices
    - Assert Device.status remains "online" after ICMP discovery
  - Verify tests PASS on UNFIXED code
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 5.1_

- [x] 6. Write mixed-protocol discovery preservation test
  - **Property 2: Preservation** - Mixed Protocol Discovery Doesn't Interfere
  - **IMPORTANT**: Follow observation-first methodology
  - Observe behavior on UNFIXED code:
    - Run ICMP discovery on subnet A (e.g., 10.0.0.0/24)
    - Observe 5 devices created with ICMP discovery pattern
    - Run SNMPv2c discovery on subnet B (e.g., 10.1.0.0/24) with different community
    - Observe new devices created from SNMPv2c, and subnet A devices remain unchanged
  - Write property-based test:
    - Generate random discovery sequences: (ICMP on subnet A, then SNMPv2c on subnet B)
    - For each: assert all devices from both discoveries remain in database
    - Assert deleted_at=NULL for all devices
    - Assert count of devices = count from ICMP + count from SNMP (no deletions)
  - Verify tests PASS on UNFIXED code (establishes baseline for preservation)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 5.1, 5.2_

---

## Phase 3: Implement Fixes

- [ ] 7. Fix SNMPv3 credentials construction in SNMPClient

  - [x] 7.1 Fix UsmUserData parameter passing
    - **File**: `backend/snmp/client.py`
    - **Function**: `SNMPClient._auth()`
    - **Change**: Replace direct None parameter passing with conditional kwargs building
    - Replace this pattern:
      ```python
      auth = getattr(...) if self.credentials.auth_protocol else None
      priv = getattr(...) if self.credentials.privacy_protocol else None
      return UsmUserData(..., authProtocol=auth, privProtocol=priv)  # BUG: passes None
      ```
    - With this pattern:
      ```python
      # Build kwargs only with non-None values
      usmUserData_kwargs = {"userName": self.credentials.username or ""}
      
      if self.credentials.auth_protocol:
        auth_proto = getattr(hlapi, AUTH_PROTOCOLS[protocol_name(self.credentials.auth_protocol)])
        usmUserData_kwargs["authKey"] = self.credentials.auth_password
        usmUserData_kwargs["authProtocol"] = auth_proto
      
      if self.credentials.privacy_protocol:
        priv_proto = getattr(hlapi, PRIVACY_PROTOCOLS[protocol_name(self.credentials.privacy_protocol)])
        usmUserData_kwargs["privKey"] = self.credentials.privacy_password
        usmUserData_kwargs["privProtocol"] = priv_proto
      
      return UsmUserData(**usmUserData_kwargs)  # Only passes non-None params
      ```
    - This allows all SNMPv3 security levels: noAuthNoPriv, authNoPriv (auth only), authPriv (auth + priv)
    - _Bug_Condition: isBugCondition_SNMPv3 from design_
    - _Expected_Behavior: UsmUserData properly constructed with only valid protocol objects_
    - _Preservation: SNMPv2c community-based auth continues to work exactly as before_
    - _Requirements: 1.2, 1.3, 2.1, 2.2, 2.3_

  - [~] 7.2 Verify SNMPv3 timeout exploration test now passes
    - **Property 1: Expected Behavior** - SNMPv3 Credentials Now Work
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior
    - When this test passes, it confirms SNMPv3 credentials are properly constructed
    - Run SNMPv3 timeout exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed - SNMP queries no longer timeout)
    - Verify that SNMPv3 discovery with privacy_protocol=None now works correctly
    - _Requirements: Expected Behavior Properties 2.1, 2.2, 2.3_

  - [~] 7.3 Verify SNMPv2c preservation still works
    - **Property 2: Preservation** - SNMPv2c Discovery Still Works
    - Re-run the SNMPv2c preservation test from step 4
    - **EXPECTED OUTCOME**: Test still PASSES (confirms no regressions in v2c code path)
    - Verify community-based discovery is completely unaffected by SNMPv3 fix
    - _Requirements: 5.2, 5.3_

- [ ] 8. Fix device deletion logic in discovery endpoint

  - [~] 8.1 Prevent database modifications when SNMP discovery fails
    - **File**: `backend/api/discovery_routes.py`
    - **Function**: `discovery_snmp()`
    - **Change**: Restructure the endpoint to guarantee database consistency
    - Current problematic flow:
      ```python
      results = {ip: result for ip, result in zip(ips, scanned) if result.get("snmp_enabled")}
      if not results:
          raise HTTPException(...)  # May occur after partial DB modifications
      
      db = SessionLocal()
      try:
          for ip, result in results.items():
              # ... upsert device ...
          db.commit()
      except Exception:
          db.rollback()
      finally:
          db.close()
      ```
    - Fix: Move all error checking BEFORE opening database session:
      ```python
      results = {ip: result for ip, result in zip(ips, scanned) if result.get("snmp_enabled")}
      if not results:
          raise HTTPException(...)  # NOW: error thrown BEFORE database session opened
      
      db = SessionLocal()
      try:
          for ip, result in results.items():
              # ... upsert device ...
          db.commit()
      except Exception:
          db.rollback()
          raise
      finally:
          db.close()
      ```
    - This ensures HTTPException 502 is thrown before ANY database modifications occur
    - _Bug_Condition: isBugCondition_DeviceDeletion from design_
    - _Expected_Behavior: Failed SNMP discovery returns error WITHOUT modifying database_
    - _Preservation: Successful SNMP discovery continues to upsert devices exactly as before_
    - _Requirements: 2.1, 2.2, 2.3, 3.1, 3.2, 3.3_

  - [~] 8.2 Verify device deletion exploration test now passes
    - **Property 1: Expected Behavior** - ICMP Devices Preserved
    - **IMPORTANT**: Re-run the SAME test from task 2 - do NOT write a new test
    - The test from task 2 encodes the expected behavior
    - Run device deletion exploration test from step 2
    - **EXPECTED OUTCOME**: Test PASSES (confirms ICMP devices no longer deleted)
    - Verify that seed ICMP devices remain in database after failed SNMP discovery
    - _Requirements: Expected Behavior Properties 3.1, 3.2, 3.3_

  - [~] 8.3 Verify ICMP discovery preservation still works
    - **Property 2: Preservation** - ICMP Discovery Still Works
    - Re-run the ICMP preservation test from step 5
    - **EXPECTED OUTCOME**: Test still PASSES (confirms ICMP discovery unaffected)
    - Verify ICMP devices are still created and not affected by SNMP changes
    - _Requirements: 5.1_

  - [~] 8.4 Verify mixed-protocol preservation still works
    - **Property 2: Preservation** - Mixed Protocol Discovery Still Works
    - Re-run the mixed-protocol preservation test from step 6
    - **EXPECTED OUTCOME**: Test still PASSES (confirms no interference between methods)
    - Verify ICMP and SNMP discoveries can be mixed without deleting devices
    - _Requirements: 5.1, 5.2_

- [ ] 9. Fix SNMPv3 form to be dynamic on frontend

  - [~] 9.1 Make IP address field optional for SNMPv3
    - **File**: Frontend discovery form (likely `src/pages/ISPMonitoring.tsx` or similar SNMPv3 discovery component)
    - **Change**: Implement conditional field visibility based on SNMP version selection
    - Current issue: Form treats IP and subnet as independent optional fields
    - Fix:
      1. When SNMPv3 is selected, make IP address field NOT required (mark as optional in form validation)
      2. Allow submission when subnet is provided without IP address for SNMPv3
      3. Keep IP address required for single-host discovery modes (if implemented)
    - Implementation approach:
      ```javascript
      const isSnmpV3 = snmpVersion === 'v3' || snmpVersion === 'SNMPv3';
      const ipAddressRequired = !isSnmpV3;  // IP required for other versions, optional for v3
      const subnetRequired = isSnmpV3;      // Subnet required for v3 subnet discovery
      ```
    - _Bug_Condition: isBugCondition_FormNotDynamic from design_
    - _Expected_Behavior: Form allows SNMPv3 discovery with subnet but no IP address_
    - _Preservation: All other form modes (ICMP, SNMPv2c, etc.) continue to work exactly as before_
    - _Requirements: 4.1, 4.2_

  - [~] 9.2 Make privacy_password optional when only auth_password provided
    - **File**: Frontend discovery form
    - **Change**: Implement conditional requirement for privacy_password based on whether user provides auth_password
    - Current issue: Form may require both password fields
    - Fix:
      1. When auth_password is provided, privacy_password becomes optional
      2. When neither is provided, show auth_password as required for SNMPv3
      3. Update form validation to allow: auth_password only (authNoPriv), or both passwords (authPriv)
    - Implementation approach:
      ```javascript
      const privacyPasswordRequired = isSnmpV3 && authPassword && !privacyPassword;
      // Show visual indicator that privacy is optional when auth-only is an option
      ```
    - _Requirements: 4.1, 4.2_

  - [~] 9.3 Verify frontend SNMPv3 form UX now works
    - **Goal**: Manually verify that SNMPv3 form now accepts subnet-based discovery without IP address
    - **Test Approach**:
      - Open SNMPv3 discovery form on frontend
      - Select SNMPv3 as protocol
      - Provide only: subnet (e.g., 192.168.100.0/24) and auth credentials
      - Leave IP address empty
      - Attempt to submit
    - **EXPECTED OUTCOME**: Form accepts submission and backend processes subnet-based SNMPv3 discovery
    - Verify that IP address field is now optional and form allows submission without it
    - _Requirements: 4.1, 4.2_

---

## Phase 4: Final Validation

- [~] 10. Run full test suite
  - **Goal**: Ensure all exploration tests, preservation tests, and integration tests pass
  - **Test Cases to Verify**:
    - [~] SNMPv3 timeout exploration test from step 1 PASSES
    - [~] Device deletion exploration test from step 2 PASSES
    - [~] SNMPv2c preservation test from step 4 PASSES
    - [~] ICMP preservation test from step 5 PASSES
    - [~] Mixed-protocol preservation test from step 6 PASSES
    - [~] All unit tests for SNMPClient, discovery_snmp, and form components PASS
    - [~] Property-based tests for all discovery methods PASS with 100+ test cases each
    - [~] Integration test: ICMP discovery → SNMPv3 discovery → Topology graph rendering PASSES
    - [~] Integration test: SNMPv2c discovery → ICMP discovery on different subnet PASSES
  - **EXPECTED OUTCOME**: All tests pass, no regressions detected, bugs are fixed
  - Confirm that:
    - SNMPv3 discovery now detects devices without timeout
    - ICMP devices are NOT deleted when SNMP discovery fails or finds no results
    - Frontend SNMPv3 form allows subnet-based discovery without IP address
    - All existing discovery workflows continue to work exactly as before
  - Mark task complete when all tests pass and issues are resolved
  - _Requirements: All requirements from bugfix.md_

---

## Summary

This implementation follows the exploratory bugfix methodology:
1. **Explore** - Write and run tests on UNFIXED code to understand bugs (steps 1-6)
2. **Implement** - Apply fixes based on understanding (steps 7-9)
3. **Validate** - Verify fixes work and don't break existing functionality (step 10)

The fixes are targeted and minimal:
- SNMPClient._auth(): Only change UsmUserData parameter passing for SNMPv3
- discovery_snmp(): Move error checking before database session
- Frontend form: Add conditional field visibility for SNMPv3

All preservation tests ensure existing functionality remains unchanged.

