#!/usr/bin/env python3
"""Direct test of monitoring data function"""

import sys
import os
sys.path.append('/home/agnigate/Desktop/NMS/hardik')

from backend.database.session import SessionLocal
from backend.api.monitoring_data_routes import MonitoringDataRequest, get_monitoring_data

def test_direct():
    print("Testing monitoring data function directly...")
    
    db = SessionLocal()
    
    request = MonitoringDataRequest(
        device_id=333,
        modules=["cpu", "memory", "storage", "interfaces"],
        include_history=False,
        history_hours=1
    )
    
    try:
        result = get_monitoring_data(request, db)
        print("✅ SUCCESS!")
        print(f"Device ID: {result['device_id']}")
        print(f"Hostname: {result['hostname']}")
        print(f"Status: {result['status']}")
        print(f"Capabilities: {result['capabilities']}")
        
        print("\nModule Data:")
        for module, data in result['modules'].items():
            supported = data['supported']
            has_data = data['data'] is not None
            print(f"  {module}: supported={supported}, has_data={has_data}")
            if has_data:
                print(f"    {data['data']}")
        
        print("\nMonitoring Configs:")
        for module, config in result['monitoring_configs'].items():
            print(f"  {module}: {config}")
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    test_direct()