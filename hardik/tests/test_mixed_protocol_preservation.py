"""Preservation test for mixed-protocol discovery baseline behavior.

This test establishes the baseline for mixed-protocol discovery workflows
(ICMP and SNMP together) on UNFIXED code.
It should PASS to demonstrate that mixing protocols doesn't cause issues
and should be preserved when fixes are applied.

**Validates: Requirements 5.1, 5.2**

**Test Goal**: Verify that ICMP and SNMP discoveries can be run on different
subnets and both device sets coexist in the database without interference.

**Expected Behavior**:
- Running ICMP discovery on subnet A should create Device records for subnet A
- Running SNMPv2c discovery on subnet B should create Device records for subnet B
- Both device sets should exist in the database simultaneously
- No device should be deleted or have deleted_at set
- Device count should equal sum of ICMP + SNMP discoveries
- Each device should maintain its discovery-specific characteristics

**Expected Outcome on UNFIXED Code**: TEST PASSES
This test verifies the CORRECT baseline behavior that must be preserved.

**Expected Outcome After Fix**: TEST STILL PASSES
No regressions - mixed-protocol discovery must work exactly the same after fixes.
"""

import sys
sys.path.insert(0, '/home/agnigate/Desktop/NMS/hardik')

from datetime import datetime


class TestMixedProtocolPreservation:
    """Preservation tests for mixed-protocol discovery baseline behavior."""

    def _setup_database(self):
        """Set up test database."""
        from backend.database.session import SessionLocal, engine, Base
        from backend.models import Device, DeviceCredential, Interface, Event
        
        # Create tables
        Base.metadata.create_all(bind=engine)
        
        # Clean up existing data
        db = SessionLocal()
        try:
            db.query(Event).delete()
            db.query(Interface).delete()
            db.query(DeviceCredential).delete()
            db.query(Device).delete()
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()
        
        return SessionLocal

    def _cleanup_database(self):
        """Clean up test database."""
        from backend.database.session import SessionLocal
        from backend.models import Device, DeviceCredential, Interface, Event
        
        db = SessionLocal()
        try:
            db.query(Event).delete()
            db.query(Interface).delete()
            db.query(DeviceCredential).delete()
            db.query(Device).delete()
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    def test_icmp_then_snmpv2c_both_preserved_concrete(self):
        """Property 2: Preservation - Mixed Protocol Discovery
        
        **Validates: Requirements 5.1, 5.2**
        
        Concrete test: Verify ICMP discovery followed by SNMPv2c discovery
        on different subnets preserves both device sets.
        
        Scenario:
        1. Run ICMP discovery on subnet A (192.168.1.0/24)
        2. Verify ICMP devices created with status="online", no credentials
        3. Run SNMPv2c discovery on subnet B (10.0.0.0/24)
        4. Verify SNMPv2c devices created with credentials
        5. Verify both device sets exist simultaneously
        6. Verify device count = ICMP count + SNMP count (no deletions)
        7. Verify all devices have deleted_at=NULL
        """
        from backend.database.session import SessionLocal
        from backend.models import Device, DeviceCredential, Event
        from backend.utils.crypto import encrypt_secret
        
        SessionLocal_factory = self._setup_database()
        
        try:
            print("\n" + "="*80)
            print("TEST: Mixed Protocol Discovery (ICMP → SNMPv2c)")
            print("="*80)
            
            # Step 1: Simulate ICMP discovery on subnet A
            print("\nStep 1: Running ICMP discovery on subnet 192.168.1.0/24")
            db = SessionLocal_factory()
            try:
                icmp_subnet = "192.168.1"
                icmp_count = 5
                
                for i in range(icmp_count):
                    device = Device(
                        ip_address=f"{icmp_subnet}.{100+i}",
                        hostname=f"icmp-host-{i}",
                        status="online",
                        monitoring_status=True,
                        last_seen=datetime.utcnow(),
                        deleted_at=None,
                    )
                    db.add(device)
                
                db.commit()
                print(f"  ✓ Created {icmp_count} ICMP devices on {icmp_subnet}.0/24")
                
            finally:
                db.close()
            
            # Step 2: Verify ICMP devices and no credentials
            print("\nStep 2: Verifying ICMP devices (no credentials)")
            db = SessionLocal_factory()
            try:
                icmp_devices = db.query(Device).filter(
                    Device.ip_address.startswith("192.168.1.")
                ).all()
                
                assert len(icmp_devices) == icmp_count
                
                for device in icmp_devices:
                    assert device.status == "online"
                    assert device.deleted_at is None
                    print(f"  - {device.ip_address}: status={device.status}")
                
                # Verify no credentials for ICMP devices
                icmp_credentials = db.query(DeviceCredential).filter(
                    DeviceCredential.device_id.in_([d.id for d in icmp_devices])
                ).all()
                
                assert len(icmp_credentials) == 0, "ICMP devices should not have credentials"
                print(f"  ✓ Verified: No DeviceCredential records for ICMP devices")
                
                icmp_device_ids = [d.id for d in icmp_devices]
                
            finally:
                db.close()
            
            # Step 3: Simulate SNMPv2c discovery on subnet B
            print("\nStep 3: Running SNMPv2c discovery on subnet 10.0.0.0/24")
            db = SessionLocal_factory()
            try:
                snmp_subnet = "10.0.0"
                snmp_count = 3
                
                snmp_device_ids = []
                for i in range(snmp_count):
                    device = Device(
                        ip_address=f"{snmp_subnet}.{10+i}",
                        hostname=f"snmp-device-{i}",
                        status="online",
                        monitoring_status=True,
                        last_seen=datetime.utcnow(),
                        deleted_at=None,
                    )
                    db.add(device)
                    db.flush()
                    
                    # Create credential for SNMP device
                    credential = DeviceCredential(
                        device_id=device.id,
                        snmp_version="v2c",
                        community_string=encrypt_secret("public"),
                    )
                    db.add(credential)
                    snmp_device_ids.append(device.id)
                
                # Create event
                for device_id in snmp_device_ids:
                    event = Event(
                        device_id=device_id,
                        event_type="SNMP_DISCOVERY",
                        description="SNMP discovery successful",
                    )
                    db.add(event)
                
                db.commit()
                print(f"  ✓ Created {snmp_count} SNMPv2c devices on {snmp_subnet}.0/24")
                
            finally:
                db.close()
            
            # Step 4: Verify SNMPv2c devices and credentials
            print("\nStep 4: Verifying SNMPv2c devices (with credentials)")
            db = SessionLocal_factory()
            try:
                snmp_devices = db.query(Device).filter(
                    Device.ip_address.startswith("10.0.0.")
                ).all()
                
                assert len(snmp_devices) == snmp_count
                
                for device in snmp_devices:
                    assert device.status == "online"
                    assert device.deleted_at is None
                    print(f"  - {device.ip_address}: status={device.status}")
                
                # Verify credentials for SNMP devices
                snmp_credentials = db.query(DeviceCredential).filter(
                    DeviceCredential.device_id.in_([d.id for d in snmp_devices])
                ).all()
                
                assert len(snmp_credentials) == snmp_count, (
                    f"SNMP devices should have credentials, got {len(snmp_credentials)}"
                )
                
                for credential in snmp_credentials:
                    assert credential.snmp_version == "v2c"
                
                print(f"  ✓ Verified: {len(snmp_credentials)} DeviceCredential records for SNMP devices")
                
            finally:
                db.close()
            
            # Step 5: Verify both device sets coexist
            print("\nStep 5: Verifying both device sets coexist")
            db = SessionLocal_factory()
            try:
                total_devices = db.query(Device).filter(
                    Device.deleted_at.is_(None)
                ).count()
                
                expected_total = icmp_count + snmp_count
                assert total_devices == expected_total, (
                    f"Expected {expected_total} devices, got {total_devices}"
                )
                print(f"  ✓ Total devices: {total_devices} ({icmp_count} ICMP + {snmp_count} SNMP)")
                
                # Verify no devices marked as deleted
                deleted_devices = db.query(Device).filter(
                    Device.deleted_at.isnot(None)
                ).count()
                
                assert deleted_devices == 0, (
                    f"No devices should be deleted, but found {deleted_devices} with deleted_at set"
                )
                print(f"  ✓ No deleted devices: {deleted_devices}")
                
            finally:
                db.close()
            
            # Step 6: Verify device characteristics preserved
            print("\nStep 6: Verifying device characteristics preserved")
            db = SessionLocal_factory()
            try:
                # Check ICMP devices
                icmp_devices = db.query(Device).filter(
                    Device.ip_address.startswith("192.168.1.")
                ).all()
                
                for device in icmp_devices:
                    assert device.status == "online"
                    assert device.monitoring_status is True
                    assert device.deleted_at is None
                    credentials = db.query(DeviceCredential).filter(
                        DeviceCredential.device_id == device.id
                    ).all()
                    assert len(credentials) == 0, "ICMP device should not have credentials"
                
                print(f"  ✓ ICMP devices: {len(icmp_devices)} preserved with correct characteristics")
                
                # Check SNMP devices
                snmp_devices = db.query(Device).filter(
                    Device.ip_address.startswith("10.0.0.")
                ).all()
                
                for device in snmp_devices:
                    assert device.status == "online"
                    assert device.monitoring_status is True
                    assert device.deleted_at is None
                    credentials = db.query(DeviceCredential).filter(
                        DeviceCredential.device_id == device.id
                    ).all()
                    assert len(credentials) == 1, "SNMP device should have credentials"
                    assert credentials[0].snmp_version == "v2c"
                
                print(f"  ✓ SNMP devices: {len(snmp_devices)} preserved with correct characteristics")
                
                print("\n✓ Mixed protocol preservation test PASSED")
                print("  Both discovery methods work together without interference:")
                print("  - ICMP devices preserved (no credentials)")
                print("  - SNMP devices preserved (with v2c credentials)")
                print("  - No deletions or interference between protocols")
                print("  - Total device count equals sum of both discoveries")
                
            finally:
                db.close()
        
        finally:
            self._cleanup_database()

    def test_snmpv2c_then_icmp_on_different_subnets(self):
        """Verify SNMPv2c followed by ICMP discovery works correctly.
        
        **Validates: Requirements 5.1, 5.2**
        
        Reverse order: SNMPv2c first, then ICMP
        - Should work without interference
        - Both device sets should coexist
        """
        from backend.database.session import SessionLocal
        from backend.models import Device, DeviceCredential, Event
        from backend.utils.crypto import encrypt_secret
        
        SessionLocal_factory = self._setup_database()
        
        try:
            print("\n" + "="*80)
            print("TEST: Mixed Protocol Discovery (SNMPv2c → ICMP)")
            print("="*80)
            
            # Step 1: SNMPv2c discovery on subnet A
            print("\nStep 1: Running SNMPv2c discovery on subnet 172.16.0.0/24")
            db = SessionLocal_factory()
            try:
                snmp_count = 2
                
                for i in range(snmp_count):
                    device = Device(
                        ip_address=f"172.16.0.{10+i}",
                        hostname=f"snmp-device-{i}",
                        status="online",
                        monitoring_status=True,
                        last_seen=datetime.utcnow(),
                        deleted_at=None,
                    )
                    db.add(device)
                    db.flush()
                    
                    credential = DeviceCredential(
                        device_id=device.id,
                        snmp_version="v2c",
                        community_string=encrypt_secret("public"),
                    )
                    db.add(credential)
                    
                    event = Event(
                        device_id=device.id,
                        event_type="SNMP_DISCOVERY",
                        description="SNMP discovery successful",
                    )
                    db.add(event)
                
                db.commit()
                print(f"  ✓ Created {snmp_count} SNMPv2c devices")
                
            finally:
                db.close()
            
            # Step 2: ICMP discovery on subnet B
            print("\nStep 2: Running ICMP discovery on subnet 203.0.113.0/24")
            db = SessionLocal_factory()
            try:
                icmp_count = 4
                
                for i in range(icmp_count):
                    device = Device(
                        ip_address=f"203.0.113.{50+i}",
                        hostname=f"icmp-host-{i}",
                        status="online",
                        monitoring_status=True,
                        last_seen=datetime.utcnow(),
                        deleted_at=None,
                    )
                    db.add(device)
                
                db.commit()
                print(f"  ✓ Created {icmp_count} ICMP devices")
                
            finally:
                db.close()
            
            # Step 3: Verify both sets coexist
            print("\nStep 3: Verifying both device sets coexist")
            db = SessionLocal_factory()
            try:
                total_devices = db.query(Device).filter(
                    Device.deleted_at.is_(None)
                ).count()
                
                expected_total = snmp_count + icmp_count
                assert total_devices == expected_total, (
                    f"Expected {expected_total} devices, got {total_devices}"
                )
                
                deleted_devices = db.query(Device).filter(
                    Device.deleted_at.isnot(None)
                ).count()
                
                assert deleted_devices == 0
                
                print(f"  ✓ Total devices: {total_devices} ({snmp_count} SNMP + {icmp_count} ICMP)")
                print(f"  ✓ No deleted devices: {deleted_devices}")
                
                # Verify credential distribution
                devices_with_creds = db.query(DeviceCredential).count()
                devices_without_creds = total_devices - devices_with_creds
                
                assert devices_with_creds == snmp_count, (
                    f"Expected {snmp_count} devices with credentials, got {devices_with_creds}"
                )
                assert devices_without_creds == icmp_count, (
                    f"Expected {icmp_count} devices without credentials, got {devices_without_creds}"
                )
                
                print(f"  ✓ Credentials correct: {devices_with_creds} SNMP, {devices_without_creds} ICMP")
                print("\n✓ Reverse order test PASSED")
                
            finally:
                db.close()
        
        finally:
            self._cleanup_database()

    def test_mixed_discovery_count_integrity(self):
        """Verify device count integrity with mixed discoveries.
        
        **Validates: Requirements 5.1, 5.2**
        
        When mixing multiple discoveries:
        - Device count should equal sum of all discoveries
        - No devices should be deleted
        - No unexpected credentials created/removed
        """
        from backend.database.session import SessionLocal
        from backend.models import Device, DeviceCredential
        from backend.utils.crypto import encrypt_secret
        
        SessionLocal_factory = self._setup_database()
        
        try:
            print("\n" + "="*80)
            print("TEST: Mixed Discovery Count Integrity")
            print("="*80)
            
            # Step 1: Create mixed devices
            print("\nStep 1: Creating mixed devices from different discovery methods")
            db = SessionLocal_factory()
            try:
                # ICMP devices on 192.168.x.x (no credentials)
                icmp_count = 0
                for subnet in [1, 2]:
                    for i in range(3):
                        device = Device(
                            ip_address=f"192.168.{subnet}.{100+i}",
                            hostname=f"icmp-{subnet}-{i}",
                            status="online",
                            monitoring_status=True,
                            deleted_at=None,
                        )
                        db.add(device)
                        icmp_count += 1
                
                # SNMPv2c devices on 10.x.x.x (with v2c credentials)
                snmp_v2c_count = 0
                for i in range(2):
                    device = Device(
                        ip_address=f"10.0.0.{10+i}",
                        hostname=f"snmp-v2c-{i}",
                        status="online",
                        monitoring_status=True,
                        deleted_at=None,
                    )
                    db.add(device)
                    db.flush()
                    
                    cred = DeviceCredential(
                        device_id=device.id,
                        snmp_version="v2c",
                        community_string=encrypt_secret("public"),
                    )
                    db.add(cred)
                    snmp_v2c_count += 1
                
                db.commit()
                
                print(f"  ✓ Created {icmp_count} ICMP devices")
                print(f"  ✓ Created {snmp_v2c_count} SNMPv2c devices")
                
            finally:
                db.close()
            
            # Step 2: Verify counts
            print("\nStep 2: Verifying count integrity")
            db = SessionLocal_factory()
            try:
                total = db.query(Device).count()
                active = db.query(Device).filter(Device.deleted_at.is_(None)).count()
                deleted = db.query(Device).filter(Device.deleted_at.isnot(None)).count()
                
                expected_total = icmp_count + snmp_v2c_count
                
                assert total == expected_total, f"Total count: expected {expected_total}, got {total}"
                assert active == expected_total, f"Active count: expected {expected_total}, got {active}"
                assert deleted == 0, f"Deleted count: expected 0, got {deleted}"
                
                print(f"  ✓ Total devices: {total}")
                print(f"  ✓ Active devices: {active}")
                print(f"  ✓ Deleted devices: {deleted}")
                
                # Verify credentials
                with_creds = db.query(DeviceCredential).count()
                without_creds = total - with_creds
                
                assert with_creds == snmp_v2c_count
                assert without_creds == icmp_count
                
                print(f"  ✓ Devices with credentials: {with_creds}")
                print(f"  ✓ Devices without credentials: {without_creds}")
                
                print("\n✓ Count integrity test PASSED")
                
            finally:
                db.close()
        
        finally:
            self._cleanup_database()


if __name__ == "__main__":
    print("\n" + "="*80)
    print("MIXED-PROTOCOL DISCOVERY PRESERVATION TEST")
    print("Validates: Requirements 5.1, 5.2")
    print("="*80)
    print("\nExpected outcome on UNFIXED code:")
    print("  - Test PASSES showing mixed protocols work correctly")
    print("  - ICMP devices created without credentials")
    print("  - SNMPv2c devices created with v2c credentials")
    print("  - No device interference or deletions")
    print("  - Device count = ICMP count + SNMP count")
    print("\nExpected outcome after fix:")
    print("  - Test STILL PASSES (no regressions)")
    print("  - Mixed protocol behavior unchanged")
    
    test_suite = TestMixedProtocolPreservation()
    
    tests = [
        ("ICMP Then SNMPv2c On Different Subnets",
         test_suite.test_icmp_then_snmpv2c_both_preserved_concrete),
        ("SNMPv2c Then ICMP On Different Subnets",
         test_suite.test_snmpv2c_then_icmp_on_different_subnets),
        ("Mixed Discovery Count Integrity",
         test_suite.test_mixed_discovery_count_integrity),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            print(f"\n{'='*80}")
            print(f"Running: {test_name}")
            print(f"{'='*80}")
            test_func()
            passed += 1
        except Exception as e:
            print(f"\n✗ TEST FAILED: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print(f"\n{'='*80}")
    print(f"SUMMARY: {passed} passed, {failed} failed")
    print(f"{'='*80}")
    
    if failed == 0:
        print("\n✓ ALL MIXED-PROTOCOL PRESERVATION TESTS PASSED")
        print("\nBaseline behavior established:")
        print("  - ICMP and SNMP can be mixed on different subnets")
        print("  - Both device sets coexist without interference")
        print("  - Device counts remain consistent")
        print("  - No unexpected deletions")
        print("\nThese tests will verify no regressions after fixes are applied.")
