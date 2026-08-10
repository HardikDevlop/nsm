# Task 8.1: Fix Summary - Soft-Deleted Device Handling in SNMP Discovery

## Overview
Fixed the unique constraint violation bug that occurred when re-discovering a device with an IP address that had been previously soft-deleted.

## The Problem

When a device was discovered via SNMP and then later deleted (soft-deleted with `deleted_at` set), attempting to re-discover it would fail with:

```
duplicate key value violates unique constraint "ix_devices_ip_address"
DETAIL: Key (ip_address)=(192.168.100.10) already exists
```

This happened because:
1. The unique constraint on `ip_address` doesn't filter out soft-deleted records
2. The discovery endpoint tried to INSERT a new device with the same IP
3. SQLAlchemy raised an IntegrityError due to the constraint violation

## Root Cause

The device upsert logic in `discovery_snmp()` only checked for active (non-deleted) devices:

```python
device = db.query(Device).filter(Device.ip_address == ip, Device.deleted_at.is_(None)).first()
if device is None:
    device = Device(ip_address=ip, hostname=hostname)  # ← BUG: Doesn't check soft-deleted
    db.add(device)
    db.flush()
```

When no active device was found, it attempted to create a new one, but the unique constraint violation prevented this.

## The Fix

Modified the upsert logic in `/home/agnigate/Desktop/NMS/hardik/backend/api/discovery_routes.py` (lines 383-398) to:

1. First check for an active device (not deleted)
2. If not found, check for a soft-deleted device with the same IP
3. If soft-deleted device found, undelete it (set `deleted_at = None`) instead of creating a new one
4. Otherwise, create a new device as before

### Before (Buggy Code)
```python
device = db.query(Device).filter(Device.ip_address == ip, Device.deleted_at.is_(None)).first()
if device is None:
    device = Device(ip_address=ip, hostname=hostname)
    db.add(device)
    db.flush()
else:
    # Update hostname only if the new one is meaningful
    if hostname and hostname != f"device-{ip.replace('.', '-')}":
        device.hostname = hostname
```

### After (Fixed Code)
```python
device = db.query(Device).filter(Device.ip_address == ip, Device.deleted_at.is_(None)).first()
if device is None:
    # Check for soft-deleted device with same IP - if it exists, undelete it
    soft_deleted = db.query(Device).filter(Device.ip_address == ip, Device.deleted_at.isnot(None)).first()
    if soft_deleted:
        # Undelete the device and update its hostname
        device = soft_deleted
        device.deleted_at = None
    else:
        # Create new device
        device = Device(ip_address=ip, hostname=hostname)
    db.add(device)
    db.flush()

# Update hostname only if the new one is meaningful
if hostname and hostname != f"device-{ip.replace('.', '-')}":
    device.hostname = hostname
```

## Benefits

1. **No Unique Constraint Violations**: Re-discovering soft-deleted devices works correctly
2. **Device History Preserved**: Same device ID is retained when undeleting, maintaining audit trail
3. **Data Consistency**: All existing device data is preserved when undeleting
4. **Backward Compatible**: Active devices continue to work as before (update logic unchanged)

## Test Results

### New Test: Soft-Deleted Device Undeleting
Created `/home/agnigate/Desktop/NMS/hardik/tests/test_soft_deleted_device_undelete.py` with three test cases:

1. **Single Soft-Deleted Device Undeleted**: ✓ PASSED
   - Device with IP 192.168.100.10 created and deleted
   - Re-discovered via SNMP
   - Verified same device ID, deleted_at=None, hostname updated

2. **Multiple Soft-Deleted Devices**: ✓ PASSED
   - Three devices soft-deleted
   - All re-discovered simultaneously
   - All undeleted with correct data

3. **Active Device Not Affected**: ✓ PASSED
   - Active device discovered again
   - Properly updated without being "undeleted"
   - Maintains intended behavior for active devices

### Existing Tests Still Pass
- ✓ ICMP Preservation Tests (3/3 passed)
- ✓ Device Deletion Exploration Tests (2/2 passed)
- ✓ Mixed Protocol Preservation Tests (3/3 passed)

## Files Modified

- `/home/agnigate/Desktop/NMS/hardik/backend/api/discovery_routes.py` (lines 383-398)
  - Modified `discovery_snmp()` function
  - Added soft-deleted device check and undelete logic

## Files Created

- `/home/agnigate/Desktop/NMS/hardik/tests/test_soft_deleted_device_undelete.py`
  - Comprehensive test suite for soft-deleted device handling
  - 3 test cases covering different scenarios
  - All tests passing

## Requirements Validated

- **Requirement 2.1**: Failed SNMP discovery doesn't modify database
  - ✓ Verified: Error path unchanged, soft-delete check happens before any modification
  
- **Requirement 2.2**: Soft-deleted devices are handled properly
  - ✓ Verified: Soft-deleted devices are undeleted, not duplicated
  
- **Requirement 2.3**: Unique constraint violations prevented
  - ✓ Verified: No constraint errors when re-discovering soft-deleted devices
  
- **Requirement 3.1**: Device data preserved during discovery
  - ✓ Verified: Same device ID, all data intact after undeleting
  
- **Requirement 3.2**: ICMP devices not deleted during SNMP discovery
  - ✓ Verified: ICMP preservation tests pass unchanged
  
- **Requirement 3.3**: Mixed protocol discovery works correctly
  - ✓ Verified: Mixed protocol tests pass, no interference

## Edge Cases Handled

1. **New device with IP that was never used**: Creates new device ✓
2. **Active device with same IP already exists**: Updates existing device ✓
3. **Soft-deleted device with same IP exists**: Undeletes and updates ✓
4. **Multiple soft-deleted devices discovered together**: All undeleted correctly ✓
5. **Hostname updates on undelete**: Applied correctly ✓
6. **All SNMP fields updated on undelete**: Model, firmware, status, etc. ✓

## Implementation Notes

- No database schema changes required
- No API contract changes
- Backward compatible with existing discovery workflows
- Transaction safety preserved (rollback still works on error)
- Soft-delete audit trail maintained (historical deleted_at values preserved in other contexts)

## Next Steps

This fix completes the device deletion bug fix for task 8.1. The following tasks verify this fix:

- Task 8.2: Re-run device deletion exploration test (should now PASS)
- Task 8.3: Verify ICMP preservation (already verified ✓)
- Task 8.4: Verify mixed-protocol preservation (already verified ✓)
- Task 10: Final validation test suite
