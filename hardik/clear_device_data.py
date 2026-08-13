#!/usr/bin/env python3
"""
Script to delete all device-related data from the NMS database.
This will clear all devices and their associated data (credentials, interfaces, metrics, etc.)
while keeping the database structure and code intact.
"""

from backend.database.session import SessionLocal
from backend.models import (
    Device, DeviceCredential, Interface, DeviceMetric, MonitoringJob,
    Alert, Event, Notification, DeviceStatusHistory
)
from backend.models.snmp import (
    DeviceInterface, DeviceInventory, DevicePerformance, SNMPCredential,
    CPUStatistic, MemoryStatistic, StorageStatistic, InterfaceStatistic,
    EnvironmentStatistic, PowerStatistic, POEStatistic, SystemHealth,
    VLANInformation, LLDPNeighbor, RoutingEntry, Alarm, SNMPTrap,
    PollingHistory, MonitoringConfig, MonitoringField, OIDCache,
    LatestCPU, LatestMemory, LatestStorage, LatestInterface, LatestEnvironment
)
from backend.models.identity import DeviceCapabilities, DeviceIdentity


def clear_all_device_data():
    """Delete all device-related data from the database."""
    
    db = SessionLocal()
    try:
        print("Starting device data deletion...")
        
        # Delete in order to respect foreign key constraints
        
        # 1. Delete SNMP latest statistics
        print("  → Deleting latest SNMP statistics...")
        db.query(LatestEnvironment).delete()
        db.query(LatestInterface).delete()
        db.query(LatestStorage).delete()
        db.query(LatestMemory).delete()
        db.query(LatestCPU).delete()
        
        # 2. Delete SNMP historical data
        print("  → Deleting SNMP historical data...")
        db.query(PollingHistory).delete()
        db.query(MonitoringField).delete()
        db.query(MonitoringConfig).delete()
        db.query(OIDCache).delete()
        db.query(SNMPTrap).delete()
        db.query(Alarm).delete()
        db.query(RoutingEntry).delete()
        db.query(LLDPNeighbor).delete()
        db.query(VLANInformation).delete()
        db.query(SystemHealth).delete()
        db.query(POEStatistic).delete()
        db.query(PowerStatistic).delete()
        db.query(EnvironmentStatistic).delete()
        db.query(InterfaceStatistic).delete()
        db.query(StorageStatistic).delete()
        db.query(MemoryStatistic).delete()
        db.query(CPUStatistic).delete()
        
        # 3. Delete SNMP device data
        print("  → Deleting SNMP device data...")
        db.query(DevicePerformance).delete()
        db.query(DeviceInventory).delete()
        db.query(DeviceInterface).delete()
        db.query(SNMPCredential).delete()
        
        # 4. Delete device identity and capabilities
        print("  → Deleting device identity and capabilities...")
        db.query(DeviceCapabilities).delete()
        db.query(DeviceIdentity).delete()
        
        # 5. Delete notifications (linked to alerts)
        print("  → Deleting notifications...")
        db.query(Notification).delete()
        
        # 6. Delete alerts
        print("  → Deleting alerts...")
        db.query(Alert).delete()
        
        # 7. Delete events
        print("  → Deleting events...")
        db.query(Event).delete()
        
        # 8. Delete device status history
        print("  → Deleting device status history...")
        db.query(DeviceStatusHistory).delete()
        
        # 9. Delete device metrics
        print("  → Deleting device metrics...")
        db.query(DeviceMetric).delete()
        
        # 10. Delete monitoring jobs
        print("  → Deleting monitoring jobs...")
        db.query(MonitoringJob).delete()
        
        # 11. Delete interfaces
        print("  → Deleting interfaces...")
        db.query(Interface).delete()
        
        # 12. Delete device credentials
        print("  → Deleting device credentials...")
        db.query(DeviceCredential).delete()
        
        # 13. Finally, delete devices
        print("  → Deleting devices...")
        device_count = db.query(Device).count()
        db.query(Device).delete()
        
        # Commit all deletions
        db.commit()
        
        print(f"\n✓ Successfully deleted all device data!")
        print(f"  Total devices removed: {device_count}")
        print("  All related data (credentials, metrics, interfaces, etc.) has been cleared.")
        
    except Exception as e:
        db.rollback()
        print(f"\n✗ Error occurred: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    confirm = input("⚠️  This will DELETE ALL device data from the database. Are you sure? (yes/no): ")
    if confirm.lower() == "yes":
        clear_all_device_data()
    else:
        print("Operation cancelled.")
