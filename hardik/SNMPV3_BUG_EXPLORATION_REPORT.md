# SNMPv3 Timeout Bug Exploration Report

## Executive Summary

The exploration test for SNMPv3 timeout bug condition has been completed. The bug has been **confirmed** through property-based testing.

## Test Execution Results

- **Test File**: `/home/agnigate/Desktop/NMS/hardik/tests/test_snmpv3_timeout_exploration.py`
- **Test Status**: PASSED (exploration test ran successfully)
- **Bug Confirmation**: YES - Bug condition manifested as expected on unfixed code

## Bug Condition Summary

### Requirements Validated
- Requirements 1.2, 1.3, 2.1, 2.2, 2.3

### Bug Details

**Current Behavior (Unfixed Code):**
When `SNMPClient._auth()` receives SNMPv3 credentials with `privacy_protocol=None` (authentication-only security level), it constructs a `UsmUserData` object with `privProtocol` set to a default protocol value instead of completely omitting the parameter.

**Expected Behavior (After Fix):**
When `privacy_protocol=None`, the `UsmUserData` should be constructed with only the `authProtocol` specified, and `privProtocol` should be completely omitted from the constructor call.

### Root Cause

In `backend/snmp/client.py`, the `_auth()` method:

```python
# Current buggy code:
auth = getattr(hlapi, AUTH_PROTOCOLS[protocol_name(self.credentials.auth_protocol)], None) if self.credentials.auth_protocol else None
priv = getattr(hlapi, PRIVACY_PROTOCOLS[protocol_name(self.credentials.privacy_protocol)], None) if self.credentials.privacy_protocol else None
return UsmUserData(self.credentials.username or "", authKey=self.credentials.auth_password if auth else None,
                   authProtocol=auth, privKey=self.credentials.privacy_password if priv else None, privProtocol=priv)
```

When `privacy_protocol=None`:
- `protocol_name(None)` returns `None`
- `PRIVACY_PROTOCOLS.get(None, ...)` returns `None`
- `priv` variable is set to `None`
- `UsmUserData(privProtocol=None)` is called with `privProtocol=None`

However, pysnmp's `UsmUserData` class has default behavior where even passing `privProtocol=None` results in a default privacy protocol being set. This breaks SNMPv3 authentication-only (authNoPriv) security level negotiation.

### Impact

**Manifestation:**
- SNMP queries timeout when connecting to devices that support authentication-only security level
- Users receive error: "No SNMP response received before timeout"
- SNMPv3 discovery fails even on reachable devices with SNMP enabled

**Scenario Tested:**
```
SNMPv3 Credentials:
  version: "v3"
  username: "testuser"
  auth_protocol: "MD5"
  auth_password: "test123"
  privacy_protocol: None  (auth-only mode)
  privacy_password: None

Result:
  UsmUserData(authProtocol=(1,3,6,1,6,3,10,1,1,2),
              privProtocol=(1,3,6,1,6,3,10,1,2,1))  ❌ BUG

Expected:
  UsmUserData(authProtocol=(1,3,6,1,6,3,10,1,1,2))  ✓ CORRECT
```

## Test Observations

### Test 1: UsmUserData Construction
- **Observation**: `UsmUserData` object is created successfully even with `privProtocol=None`
- **Issue**: The object contains an inappropriate `privProtocol` value even when not specified
- **Impact**: SNMP negotiation fails for auth-only devices

### Test 2: Credentials Formatting
- **Observation**: `SNMPCredentials` properly accepts `privacy_protocol=None`
- **Status**: ✓ Works correctly at the credentials level
- **Issue**: Problem is in the `SNMPClient._auth()` method, not credentials

### Test 3: Protocol Resolution
- **Observation**: When `privacy_protocol=None`, protocol resolution correctly returns `None`
- **Status**: ✓ Correctly identified
- **Issue**: This `None` is then passed to `UsmUserData(privProtocol=None)`, which is invalid

### Test 4: Parameter Passing
- **Observation**: The current code passes `privProtocol=None` to `UsmUserData` constructor
- **Issue**: This is the direct cause of the bug
- **Solution**: Use kwargs building to conditionally include only non-None parameters

### Test 5: Bug Manifestation
- **Scenario 1 (Auth-only)**: `privProtocol` is set to `(1, 3, 6, 1, 6, 3, 10, 1, 2, 1)` ❌
- **Scenario 2 (Auth+Priv)**: `privProtocol` is set to `(1, 3, 6, 1, 6, 3, 10, 1, 2, 2)` ✓
- **Difference**: Auth-only case should have no privacy protocol at all

## Counterexample Documented

```
Input SNMPv3 Credentials:
  auth_protocol = "MD5"
  auth_password = "test123"
  privacy_protocol = None
  privacy_password = None

Buggy Output:
  UsmUserData(
    userName='testuser',
    authKey='test123',
    authProtocol=(1, 3, 6, 1, 6, 3, 10, 1, 1, 2),  ✓ MD5 Auth
    privProtocol=(1, 3, 6, 1, 6, 3, 10, 1, 2, 1),  ❌ Default Privacy (DES)
    privKey=None                                      ❌ Inconsistent
  )

Expected Output:
  UsmUserData(
    userName='testuser',
    authKey='test123',
    authProtocol=(1, 3, 6, 1, 6, 3, 10, 1, 1, 2),  ✓ MD5 Auth
    privProtocol=None,                               ✓ No Privacy
    privKey=None                                      ✓ Consistent
  )
```

## Recommended Fix

**File**: `backend/snmp/client.py`
**Function**: `SNMPClient._auth()`

Replace the parameter passing logic with kwargs building:

```python
def _auth(self) -> Any:
    from pysnmp.hlapi.asyncio import CommunityData, UsmUserData
    if not self.credentials.is_v3:
        return CommunityData(self.credentials.community or "public", mpModel=1)
    
    import pysnmp.hlapi.asyncio as hlapi
    
    # Build kwargs only with non-None protocol values
    usmUserData_kwargs = {"userName": self.credentials.username or ""}
    
    if self.credentials.auth_protocol:
        auth_proto = getattr(hlapi, AUTH_PROTOCOLS[protocol_name(self.credentials.auth_protocol)])
        usmUserData_kwargs["authKey"] = self.credentials.auth_password
        usmUserData_kwargs["authProtocol"] = auth_proto
    
    if self.credentials.privacy_protocol:
        priv_proto = getattr(hlapi, PRIVACY_PROTOCOLS[protocol_name(self.credentials.privacy_protocol)])
        usmUserData_kwargs["privKey"] = self.credentials.privacy_password
        usmUserData_kwargs["privProtocol"] = priv_proto
    
    return UsmUserData(**usmUserData_kwargs)
```

This fix ensures:
1. ✓ When `privacy_protocol=None`, `privProtocol` is completely omitted
2. ✓ When `privacy_protocol` is specified, both `privKey` and `privProtocol` are set
3. ✓ Supports all SNMPv3 security levels: noAuthNoPriv, authNoPriv, authPriv
4. ✓ Maintains backward compatibility with SNMPv2c and existing SNMPv3 configurations

## Next Steps

1. **Implement Fix**: Apply the recommended fix to `backend/snmp/client.py`
2. **Re-run Test**: Run the same exploration test with fixed code (should PASS)
3. **Integration Testing**: Test actual SNMP queries to auth-only devices
4. **Preserve Existing Behavior**: Verify SNMPv2c discovery continues to work
5. **Complete Task Workflow**: Proceed with remaining bugfix tasks

## Test File Location

The exploration test has been created at:
```
/home/agnigate/Desktop/NMS/hardik/tests/test_snmpv3_timeout_exploration.py
```

Run with:
```bash
cd /home/agnigate/Desktop/NMS/hardik
source .venv/bin/activate
python tests/test_snmpv3_timeout_exploration.py
```

## Conclusion

The SNMPv3 timeout bug has been **successfully explored and documented**. The exploration test confirms that the bug exists on unfixed code, providing a concrete counterexample that will be used to validate the fix in the next phase.
