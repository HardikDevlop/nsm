# SNMP Device Discovery Bugs - Test Suite

This directory contains the complete test suite for the SNMP device discovery bugfix workflow.

## Overview

The tests are organized in two phases:

1. **Exploration Tests** - Verify bugs exist on unfixed code
2. **Preservation Tests** - Establish baseline behavior that must be preserved after fixes

## Phase 1: Bug Exploration Tests

These tests confirm that bugs exist on unfixed code. They SHOULD FAIL on unfixed code, and their failure documents the bug condition.

### Test Files

- **test_snmpv3_timeout_exploration.py**
  - **Validates**: Requirements 1.2, 1.3, 2.1, 2.2, 2.3
  - **Bug**: SNMPv3 credentials with privacy_protocol=None cause SNMP queries to timeout
  - **Expected on unfixed code**: Test FAILS (timeout or invalid credential error)
  - **Counterexample documented**: SNMPClient._auth() passes privProtocol=None to UsmUserData
  - **How to run**: `python tests/test_snmpv3_timeout_exploration.py`

- **test_device_deletion_exploration.py**
  - **Validates**: Requirements 2.1, 2.2, 2.3
  - **Bug**: ICMP-discovered devices deleted when SNMP discovery finds no results
  - **Expected on unfixed code**: Test FAILS (deleted_at set on ICMP devices)
  - **Counterexample documented**: 5 ICMP devices deleted after SNMP discovery with 0 results
  - **How to run**: `python tests/test_device_deletion_exploration.py`

## Phase 2: Preservation Tests

These tests establish the BASELINE behavior on unfixed code that must be preserved after fixes are applied. They SHOULD PASS on unfixed code.

### Test Files

- **test_snmpv2c_preservation.py**
  - **Validates**: Requirements 5.2, 5.3
  - **Purpose**: Verify SNMPv2c discovery works correctly and creates devices with v2c credentials
  - **Test cases**:
    1. SNMPv2c discovery creates Device records with correct data
    2. DeviceCredential records created with snmp_version="v2c"
    3. Community string encrypted and stored
    4. Running discovery again doesn't create duplicates
    5. Device data preserved and updated correctly
  - **Expected on unfixed code**: TEST PASSES
  - **Expected after fix**: TEST STILL PASSES (no regressions)
  - **How to run**: `python tests/test_snmpv2c_preservation.py`

- **test_icmp_preservation.py**
  - **Validates**: Requirements 5.1
  - **Purpose**: Verify ICMP discovery works correctly and creates devices WITHOUT credentials
  - **Test cases**:
    1. ICMP discovery creates Device records with status="online"
    2. NO DeviceCredential records created (ICMP doesn't use credentials)
    3. Running discovery again doesn't create duplicates (idempotency)
    4. Device data preserved across multiple discoveries
    5. ICMP devices not affected by other discovery methods
  - **Expected on unfixed code**: TEST PASSES
  - **Expected after fix**: TEST STILL PASSES (no regressions)
  - **How to run**: `python tests/test_icmp_preservation.py`

- **test_mixed_protocol_preservation.py**
  - **Validates**: Requirements 5.1, 5.2
  - **Purpose**: Verify ICMP and SNMP discoveries can be mixed without interference
  - **Test cases**:
    1. ICMP on subnet A, SNMPv2c on subnet B - both preserved
    2. SNMPv2c on subnet A, ICMP on subnet B - both preserved
    3. Device count equals sum of both discoveries (no deletions)
    4. No unexpected device deletions or modifications
    5. Credentials only for SNMP devices, not ICMP
  - **Expected on unfixed code**: TEST PASSES
  - **Expected after fix**: TEST STILL PASSES (no regressions)
  - **How to run**: `python tests/test_mixed_protocol_preservation.py`

## Running All Tests

### Quick Start

```bash
# Run all exploration tests
python tests/test_snmpv3_timeout_exploration.py
python tests/test_device_deletion_exploration.py

# Run all preservation tests
python tests/test_snmpv2c_preservation.py
python tests/test_icmp_preservation.py
python tests/test_mixed_protocol_preservation.py
```

### Using pytest (if available)

```bash
# Run all tests
pytest tests/

# Run with verbose output
pytest tests/ -v

# Run specific test
pytest tests/test_snmpv2c_preservation.py -v

# Run specific test class
pytest tests/test_snmpv2c_preservation.py::TestSNMPv2cPreservation -v

# Run specific test method
pytest tests/test_snmpv2c_preservation.py::TestSNMPv2cPreservation::test_snmpv2c_basic_discovery_creates_devices_concrete -v
```

## Test Workflow

### Phase 1: Understand Bugs

1. Run exploration tests on UNFIXED code
2. Observe counterexamples that demonstrate bugs
3. Document bug conditions

Expected behavior:
```
✗ SNMPv3 timeout exploration test FAILS
  Counterexample: SNMPClient._auth() passes privProtocol=None

✗ Device deletion exploration test FAILS
  Counterexample: ICMP devices deleted after SNMP discovery with 0 results
```

### Phase 2: Establish Baselines

1. Run preservation tests on UNFIXED code
2. Verify all tests PASS (baseline is correct)
3. Document the correct behavior to preserve

Expected behavior:
```
✓ SNMPv2c preservation test PASSES
✓ ICMP preservation test PASSES
✓ Mixed protocol preservation test PASSES
```

### Phase 3: Implement Fixes

1. Apply fixes to:
   - `backend/snmp/client.py` - Fix UsmUserData parameter passing
   - `backend/api/discovery_routes.py` - Fix device deletion logic
   - Frontend SNMPv3 form - Make fields dynamic

2. Re-run all tests:
   - Exploration tests SHOULD NOW PASS (bugs fixed)
   - Preservation tests SHOULD STILL PASS (no regressions)

### Phase 4: Verify No Regressions

Expected behavior after fix:
```
✓ SNMPv3 timeout exploration test PASSES (bug fixed)
✓ Device deletion exploration test PASSES (bug fixed)
✓ SNMPv2c preservation test PASSES (no regression)
✓ ICMP preservation test PASSES (no regression)
✓ Mixed protocol preservation test PASSES (no regression)
```

## Database Setup

All tests use SQLite database that is created automatically:

- Database location: `sqlite:///./test.db` (in-memory or local file)
- Tables created automatically from SQLAlchemy models
- Cleaned up after each test

To use a specific database:

```python
# Edit database URL in test file
SessionLocal = sessionmaker(
    bind=create_engine("sqlite:///./test_snmp.db")  # Custom file
)
```

## Debugging Failed Tests

### If SNMPv2c preservation test fails:

1. Check database connectivity
2. Verify Device model has required fields
3. Verify encryption functions work
4. Check if there are constraint violations (unique IP addresses)

### If ICMP preservation test fails:

1. Check Device model creation
2. Verify queries work correctly
3. Check for leftover data from previous runs

### If mixed protocol test fails:

1. Verify both device sets are being created
2. Check device count calculations
3. Verify credential creation for SNMP only

## Test Structure

Each test file contains:

1. **Class-based test suite** - Multiple test methods
2. **Helper methods**:
   - `_setup_database()` - Create tables and clean data
   - `_cleanup_database()` - Delete all test data
3. **Individual test methods** - Each tests a specific scenario
4. **Main block** - Runs all tests with summary

### Typical test structure:

```python
def test_something(self):
    """Description of what this tests."""
    SessionLocal_factory = self._setup_database()
    try:
        # Setup
        db = SessionLocal_factory()
        try:
            # Create test data
            db.commit()
        finally:
            db.close()
        
        # Execute
        db = SessionLocal_factory()
        try:
            # Perform action
            db.commit()
        finally:
            db.close()
        
        # Verify
        db = SessionLocal_factory()
        try:
            # Assert results
            assert condition
        finally:
            db.close()
    finally:
        self._cleanup_database()
```

## Expected Outcomes Summary

| Test | Unfixed Code | After Fix | Status |
|------|--------------|-----------|--------|
| SNMPv3 Timeout | ✗ FAILS | ✓ PASSES | Bug fixed |
| Device Deletion | ✗ FAILS | ✓ PASSES | Bug fixed |
| SNMPv2c Preservation | ✓ PASSES | ✓ PASSES | Regression prevention ✓ |
| ICMP Preservation | ✓ PASSES | ✓ PASSES | Regression prevention ✓ |
| Mixed Protocol Preservation | ✓ PASSES | ✓ PASSES | Regression prevention ✓ |

## Requirements Mapping

### Exploration Tests
- Test files: `test_snmpv3_timeout_exploration.py`, `test_device_deletion_exploration.py`
- Validates bug conditions exist
- Requirement coverage: 1.2, 1.3, 2.1, 2.2, 2.3

### Preservation Tests
- Test files: `test_snmpv2c_preservation.py`, `test_icmp_preservation.py`, `test_mixed_protocol_preservation.py`
- Validates existing behavior remains unchanged
- Requirement coverage: 5.1, 5.2, 5.3

### Bug Fixes
- Task 7: Fix SNMPv3 credentials in SNMPClient._auth()
- Task 8: Fix device deletion in discovery_snmp()
- Task 9: Fix frontend form to be dynamic for SNMPv3

## Key Testing Principles

1. **Preservation First**: Establish baseline behavior before implementing fixes
2. **Counterexamples**: Document concrete examples that demonstrate bugs
3. **No Mocking**: Tests should validate real functionality where possible
4. **Idempotency**: Verify discoveries can be run multiple times safely
5. **Isolation**: Verify different protocols don't interfere with each other
6. **Data Integrity**: Verify device data remains consistent throughout

## Troubleshooting

### Import errors

Ensure sys.path includes the hardik directory:
```python
import sys
sys.path.insert(0, '/path/to/NMS/hardik')
```

### Database locked errors

- Clean up previous test runs
- Check for lingering database connections
- Use in-memory database for faster tests

### Encryption errors

- Verify `backend.utils.crypto` module exists
- Check encrypt_secret function works
- Verify ENCRYPTION_KEY environment variable is set

### Missing tables

- Run `Base.metadata.create_all(bind=engine)` in setup
- Verify all models are imported correctly
- Check for FK constraint issues

## Next Steps

After all tests pass:

1. ✓ Run exploration tests on unfixed code (expect failures)
2. ✓ Run preservation tests on unfixed code (expect passes)
3. Implement fixes (Tasks 7-9)
4. Re-run all tests (expect all passes)
5. Run integration tests
6. Deploy and verify production behavior

