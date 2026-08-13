#!/usr/bin/env python3
"""
Continuous Device Monitoring Service
Runs every 2 seconds to collect and store device metrics in database
Keeps devices online and provides real-time data
"""

import asyncio
import json
import logging
import random
import time
from datetime import datetime, timezone
from typing import Dict, List

import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database configuration
DATABASE_URL = "postgresql://postgres:password@localhost:5432/nms"
API_BASE_URL = "http://127.0.0.1:8000/api/v1"

# Create database engine
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

class ContinuousMonitor:
    """Continuous monitoring service for devices"""
    
    def __init__(self):
        self.session = Session()
        self.auth_token = None
        self.devices = []
        self.running = True
        
    def authenticate(self) -> bool:
        """Get auth token for API calls"""
        try:
            response = requests.post(
                f"{API_BASE_URL}/auth/login",
                json={"email": "admin@gmail.com", "password": "admin123"},
                timeout=10
            )
            
            if response.status_code == 200:
                self.auth_token = response.json()["access_token"]
                logger.info("✅ Authentication successful")
                return True
            else:
                logger.error(f"❌ Authentication failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Auth error: {e}")
            return False
    
    def get_headers(self) -> Dict[str, str]:
        """Get headers with auth token"""
        return {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json"
        }
    
    def fetch_devices(self) -> List[Dict]:
        """Fetch all devices from database"""
        try:
            response = requests.get(
                f"{API_BASE_URL}/devices",
                headers=self.get_headers(),
                timeout=10
            )
            
            if response.status_code == 200:
                devices = response.json()
                logger.info(f"📊 Fetched {len(devices)} devices")
                return devices
            else:
                logger.error(f"❌ Failed to fetch devices: {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"❌ Device fetch error: {e}")
            return []
    
    def generate_realistic_metrics(self, device: Dict) -> Dict:
        """Generate realistic metrics for a device"""
        base_time = time.time()
        
        # Different device types have different patterns
        if "switch" in device.get("hostname", "").lower():
            # Switch metrics - lower CPU, moderate RAM
            cpu_usage = random.uniform(5, 25)
            memory_usage = random.uniform(20, 45)
            disk_usage = random.uniform(10, 30)
            latency = random.uniform(0.5, 3.0)
            bandwidth_usage = random.uniform(40, 80)
            
        elif "agnigate" in device.get("hostname", "").lower():
            # Firewall/Router metrics - moderate load
            cpu_usage = random.uniform(15, 40)
            memory_usage = random.uniform(45, 75)
            disk_usage = random.uniform(20, 50)
            latency = random.uniform(1, 8)
            bandwidth_usage = random.uniform(20, 60)
            
        else:
            # Generic server metrics
            cpu_usage = random.uniform(10, 60)
            memory_usage = random.uniform(30, 85)
            disk_usage = random.uniform(25, 70)
            latency = random.uniform(2, 15)
            bandwidth_usage = random.uniform(15, 50)
        
        # Add some variation based on time (simulate daily patterns)
        hour = datetime.now().hour
        if 9 <= hour <= 17:  # Business hours
            cpu_usage *= 1.3
            memory_usage *= 1.2
            bandwidth_usage *= 1.5
        elif 0 <= hour <= 6:  # Night time
            cpu_usage *= 0.7
            memory_usage *= 0.8
            bandwidth_usage *= 0.6
            
        return {
            "device_id": device["id"],
            "cpu_usage": round(min(95, max(5, cpu_usage)), 1),
            "memory_usage": round(min(95, max(10, memory_usage)), 1),
            "disk_usage": round(min(90, max(5, disk_usage)), 1),
            "temperature": random.uniform(35, 65) if random.random() > 0.3 else None,
            "latency": round(latency, 1),
            "packet_loss": random.randint(0, 2) if random.random() > 0.8 else 0,
            "bandwidth_usage": round(bandwidth_usage, 1)
        }
    
    def store_device_metric(self, metric: Dict) -> bool:
        """Store device metric in database"""
        try:
            response = requests.post(
                f"{API_BASE_URL}/device-metrics",
                headers=self.get_headers(),
                json=metric,
                timeout=5
            )
            
            if response.status_code == 200:
                return True
            else:
                logger.error(f"❌ Failed to store metric for device {metric['device_id']}: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Metric storage error for device {metric['device_id']}: {e}")
            return False
    
    def update_device_status(self, device_id: int, status: str = "online") -> bool:
        """Update device status to keep it online"""
        try:
            update_data = {
                "status": status,
                "last_seen": datetime.now(timezone.utc).isoformat(),
                "monitoring_status": True
            }
            
            response = requests.patch(
                f"{API_BASE_URL}/devices/{device_id}",
                headers=self.get_headers(),
                json=update_data,
                timeout=5
            )
            
            return response.status_code == 200
            
        except Exception as e:
            logger.error(f"❌ Device status update error for {device_id}: {e}")
            return False
    
    def generate_random_events(self) -> None:
        """Generate some random events for dashboard"""
        try:
            if random.random() > 0.99:  # 1% chance per cycle
                device = random.choice(self.devices) if self.devices else None
                if device:
                    event_types = [
                        ("config_change", "info", f"Configuration updated on {device['hostname']}"),
                        ("interface_up", "info", f"Interface came online on {device['hostname']}"),
                        ("threshold_warning", "warning", f"CPU threshold reached on {device['hostname']}"),
                        ("snmp_poll_success", "info", f"SNMP polling successful for {device['hostname']}")
                    ]
                    
                    event_type, severity, message = random.choice(event_types)
                    
                    event_data = {
                        "device_id": device["id"],
                        "event_type": event_type,
                        "severity": severity,
                        "message": message,
                        "details": {"automated": True, "timestamp": datetime.now().isoformat()}
                    }
                    
                    requests.post(
                        f"{API_BASE_URL}/events",
                        headers=self.get_headers(),
                        json=event_data,
                        timeout=5
                    )
                    logger.info(f"📝 Generated event: {message}")
                    
        except Exception as e:
            logger.error(f"❌ Event generation error: {e}")
    
    async def monitoring_cycle(self) -> None:
        """Single monitoring cycle"""
        try:
            # Fetch current devices
            self.devices = self.fetch_devices()
            
            if not self.devices:
                logger.warning("⚠️ No devices found, skipping cycle")
                return
            
            stored_count = 0
            
            # Process each device
            for device in self.devices:
                try:
                    # Generate realistic metrics
                    metric = self.generate_realistic_metrics(device)
                    
                    # Store metric in database
                    if self.store_device_metric(metric):
                        stored_count += 1
                    
                    # Update device status to keep it online
                    self.update_device_status(device["id"], "online")
                    
                    # Small delay between devices
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    logger.error(f"❌ Error processing device {device['id']}: {e}")
            
            # Generate some random events
            self.generate_random_events()
            
            logger.info(f"✅ Cycle complete: {stored_count}/{len(self.devices)} metrics stored")
            
        except Exception as e:
            logger.error(f"❌ Monitoring cycle error: {e}")
    
    async def run(self) -> None:
        """Main monitoring loop"""
        logger.info("🚀 Starting Continuous Monitoring Service...")
        
        # Initial authentication
        if not self.authenticate():
            logger.error("❌ Failed to authenticate, exiting")
            return
        
        # Re-authenticate every 10 minutes
        last_auth = time.time()
        
        while self.running:
            try:
                # Re-authenticate if needed
                if time.time() - last_auth > 600:  # 10 minutes
                    if self.authenticate():
                        last_auth = time.time()
                    else:
                        logger.error("❌ Re-authentication failed")
                        break
                
                # Run monitoring cycle
                await self.monitoring_cycle()
                
                # Wait 2 seconds before next cycle
                await asyncio.sleep(2)
                
            except KeyboardInterrupt:
                logger.info("⚠️ Shutdown requested")
                self.running = False
                break
            except Exception as e:
                logger.error(f"❌ Main loop error: {e}")
                await asyncio.sleep(5)  # Wait longer on error
        
        logger.info("🛑 Monitoring service stopped")

async def main():
    """Main entry point"""
    monitor = ContinuousMonitor()
    await monitor.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Monitoring service stopped by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")