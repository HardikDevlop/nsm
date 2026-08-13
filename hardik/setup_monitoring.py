#!/usr/bin/env python3
"""
Setup script for continuous monitoring
Initializes database with sample data and starts monitoring
"""

import requests
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_BASE = "http://127.0.0.1:8000/api/v1"

def get_auth_token():
    """Get authentication token"""
    try:
        response = requests.post(f"{API_BASE}/auth/login", 
                               json={"email": "admin@gmail.com", "password": "admin123"})
        if response.status_code == 200:
            return response.json()["access_token"]
        else:
            logger.error(f"Auth failed: {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"Auth error: {e}")
        return None

def setup_sample_devices():
    """Setup sample devices if none exist"""
    token = get_auth_token()
    if not token:
        return False
    
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    # Check existing devices
    try:
        response = requests.get(f"{API_BASE}/devices", headers=headers)
        devices = response.json() if response.status_code == 200 else []
        
        if len(devices) >= 3:
            logger.info(f"✅ {len(devices)} devices already exist")
            return True
        
        # Add sample devices
        sample_devices = [
            {
                "hostname": "AgniGATE-FW01",
                "ip_address": "192.168.100.1", 
                "device_type": "firewall",
                "model": "AGNI3000-P-120",
                "monitoring_status": True,
                "status": "online"
            },
            {
                "hostname": "Core-Switch-01",
                "ip_address": "192.168.100.2",
                "device_type": "switch", 
                "model": "Cisco 2960X",
                "monitoring_status": True,
                "status": "online"
            },
            {
                "hostname": "Server-DB-01", 
                "ip_address": "192.168.100.10",
                "device_type": "server",
                "model": "Dell PowerEdge R740",
                "monitoring_status": True,
                "status": "online"
            },
            {
                "hostname": "Access-Point-01",
                "ip_address": "192.168.100.50",
                "device_type": "access_point",
                "model": "Ubiquiti UniFi AP",
                "monitoring_status": True, 
                "status": "online"
            },
            {
                "hostname": "Router-WAN-01",
                "ip_address": "192.168.100.254",
                "device_type": "router",
                "model": "Cisco ISR 4331",
                "monitoring_status": True,
                "status": "online"
            }
        ]
        
        created_count = 0
        for device_data in sample_devices:
            try:
                response = requests.post(f"{API_BASE}/devices", headers=headers, json=device_data)
                if response.status_code == 200:
                    created_count += 1
                    logger.info(f"✅ Created device: {device_data['hostname']}")
                else:
                    logger.warning(f"⚠️ Failed to create {device_data['hostname']}: {response.status_code}")
            except Exception as e:
                logger.error(f"❌ Device creation error: {e}")
        
        logger.info(f"✅ Created {created_count} devices")
        return created_count > 0
        
    except Exception as e:
        logger.error(f"❌ Setup error: {e}")
        return False

def setup_sample_alerts():
    """Setup sample alerts for testing"""
    token = get_auth_token()
    if not token:
        return False
    
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    sample_alerts = [
        {
            "device_id": 333,
            "alert_type": "high_cpu",
            "severity": "warning",
            "message": "CPU usage above 75% threshold",
            "status": "open"
        },
        {
            "device_id": 334, 
            "alert_type": "interface_down",
            "severity": "critical",
            "message": "GigabitEthernet0/2 interface is down",
            "status": "acknowledged"
        }
    ]
    
    try:
        for alert in sample_alerts:
            requests.post(f"{API_BASE}/alerts", headers=headers, json=alert)
        logger.info("✅ Sample alerts created")
        return True
    except Exception as e:
        logger.error(f"❌ Alert setup error: {e}")
        return False

def main():
    """Main setup function"""
    logger.info("🚀 Setting up continuous monitoring...")
    
    # Wait for backend to be ready
    logger.info("⏳ Waiting for backend...")
    for i in range(10):
        try:
            response = requests.get(f"{API_BASE}/devices", timeout=5)
            if response.status_code in [200, 401]:  # 401 is also OK, means auth is needed
                logger.info("✅ Backend is ready!")
                break
        except:
            pass
        time.sleep(2)
    else:
        logger.error("❌ Backend not responding")
        return
    
    # Setup sample data
    setup_sample_devices()
    setup_sample_alerts()
    
    logger.info("✅ Setup complete! You can now run:")
    logger.info("   python3 continuous_monitoring.py")
    logger.info("")
    logger.info("Or start it as a background service:")
    logger.info("   nohup python3 continuous_monitoring.py > monitoring.log 2>&1 &")

if __name__ == "__main__":
    main()