#!/usr/bin/env python3
"""
Simple Continuous Monitoring Service
Keeps devices online with fresh data every 2 seconds
"""

import requests
import time
import random
import json
from datetime import datetime

API_BASE = "http://127.0.0.1:8000/api/v1"

def get_auth_token():
    """Get authentication token"""
    try:
        response = requests.post(f"{API_BASE}/auth/login", 
                               json={"email": "admin@gmail.com", "password": "admin123"})
        return response.json()["access_token"] if response.status_code == 200 else None
    except:
        return None

def generate_metrics(device_id):
    """Generate realistic metrics for device"""
    return {
        "device_id": device_id,
        "cpu_usage": round(random.uniform(15, 85), 1),
        "memory_usage": round(random.uniform(25, 90), 1), 
        "disk_usage": round(random.uniform(20, 75), 1),
        "latency": round(random.uniform(1, 25), 1),
        "packet_loss": random.randint(0, 3),
        "bandwidth_usage": round(random.uniform(10, 95), 1)
    }

def update_device_status(device_id, headers):
    """Keep device online"""
    try:
        update_data = {
            "status": "online",
            "last_seen": datetime.now().isoformat(),
            "monitoring_status": True
        }
        requests.patch(f"{API_BASE}/devices/{device_id}", headers=headers, json=update_data)
    except:
        pass

def main():
    print("🚀 Starting Simple Monitoring Service...")
    
    # Get auth token
    token = get_auth_token()
    if not token:
        print("❌ Authentication failed")
        return
    
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    print("✅ Authenticated successfully")
    
    cycle = 0
    
    try:
        while True:
            cycle += 1
            
            # Get devices
            try:
                response = requests.get(f"{API_BASE}/devices", headers=headers, timeout=5)
                devices = response.json() if response.status_code == 200 else []
            except:
                devices = []
            
            if not devices:
                print("⚠️ No devices found")
                time.sleep(5)
                continue
            
            # Process each device
            stored_count = 0
            for device in devices:
                try:
                    # Generate and store metrics
                    metrics = generate_metrics(device["id"])
                    
                    response = requests.post(f"{API_BASE}/device-metrics", 
                                           headers=headers, json=metrics, timeout=3)
                    
                    if response.status_code in [200, 201]:
                        stored_count += 1
                    
                    # Update device status
                    update_device_status(device["id"], headers)
                    
                except Exception as e:
                    print(f"❌ Error processing device {device['id']}: {e}")
            
            print(f"📊 Cycle {cycle}: {stored_count}/{len(devices)} metrics stored")
            
            # Re-auth every 100 cycles (5 minutes)
            if cycle % 100 == 0:
                token = get_auth_token()
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                    print("🔄 Re-authenticated")
            
            # Wait 2 seconds
            time.sleep(2)
            
    except KeyboardInterrupt:
        print("\n🛑 Monitoring stopped by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")

if __name__ == "__main__":
    main()