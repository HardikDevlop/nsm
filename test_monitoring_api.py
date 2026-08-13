#!/usr/bin/env python3
"""Test the monitoring data API without authentication"""

import requests
import json
from datetime import datetime

# Backend URL
BASE_URL = "http://127.0.0.1:8000/api/v1"

def test_monitoring_api():
    # Test data
    payload = {
        "device_id": 333,
        "modules": ["cpu", "memory", "storage", "interfaces"],
        "include_history": False,
        "history_hours": 1
    }
    
    print(f"Testing API at: {BASE_URL}/monitoring/data")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    try:
        response = requests.post(
            f"{BASE_URL}/monitoring/data",
            json=payload,
            timeout=10,
            # Skip authentication for testing
            headers={"Content-Type": "application/json"}
        )
        
        print(f"\nStatus Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"\nResponse (formatted):")
            print(json.dumps(data, indent=2))
        else:
            print(f"\nError Response:")
            print(response.text)
            
    except requests.exceptions.ConnectionError:
        print("❌ Connection failed - backend not running on 127.0.0.1:8000")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_monitoring_api()