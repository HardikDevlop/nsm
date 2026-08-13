# Monitoring Data API - Testing Guide

## Overview
Yeh API database se monitoring data read karti hai (live SNMP poll nahi karti).
Background polling scheduler data ko `latest_*` tables mein store karta hai, aur yeh API us data ko return karti hai.

---

## API Endpoints

### 1. POST /api/v1/monitoring/data (Recommended)
**Description:** Complete monitoring data with flexible options

**Headers:**
```
Content-Type: application/json
Authorization: Bearer <your_token>
```

**Request Body:**
```json
{
  "device_id": 329,
  "modules": ["cpu", "memory", "storage", "interfaces", "environment"],
  "include_history": false,
  "history_hours": 1
}
```

**cURL Example:**
```bash
curl -X POST "http://localhost:8000/api/v1/monitoring/data" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "device_id": 329,
    "modules": ["cpu", "memory", "storage", "interfaces"],
    "include_history": false,
    "history_hours": 1
  }'
```

**Response Example:**
```json
{
  "device_id": 329,
  "ip_address": "192.168.100.1",
  "hostname": "AgniGATE",
  "status": "online",
  "timestamp": "2026-08-12T10:30:00.000000",
  "modules": {
    "cpu": {
      "supported": true,
      "data": {
        "utilization_percent": 5.6,
        "per_core": {},
        "load_avg": {},
        "polled_at": "2026-08-12T10:29:45.000000"
      },
      "history": []
    },
    "memory": {
      "supported": true,
      "data": {
        "total_bytes": 8589934592,
        "used_bytes": 3221225472,
        "free_bytes": 5368709120,
        "cached_bytes": 1073741824,
        "buffer_bytes": 536870912,
        "swap_total": 2147483648,
        "swap_free": 2147483648,
        "utilization_percent": 58.7,
        "polled_at": "2026-08-12T10:29:45.000000"
      },
      "history": []
    },
    "storage": {
      "supported": true,
      "data": {
        "volumes": [
          {
            "volume_id": "/",
            "mount_name": "/",
            "total_bytes": 107374182400,
            "used_bytes": 32212254720,
            "free_bytes": 75161927680,
            "utilization_percent": 30.0,
            "type_label": "Fixed Disk",
            "polled_at": "2026-08-12T10:29:45.000000"
          }
        ]
      },
      "history": []
    },
    "interfaces": {
      "supported": true,
      "data": {
        "interfaces": [
          {
            "if_index": 1,
            "name": "eth0",
            "oper_status": "up",
            "admin_status": "up",
            "speed_bps": 1000000000,
            "rx_mbps": 2.5,
            "tx_mbps": 1.2,
            "rx_octets": 1048576000,
            "tx_octets": 524288000,
            "rx_packets": 1000000,
            "tx_packets": 500000,
            "errors": 0,
            "discards": 0,
            "utilization_percent": 0.35,
            "polled_at": "2026-08-12T10:29:45.000000"
          }
        ]
      },
      "history": []
    }
  },
  "monitoring_configs": {
    "cpu": {
      "enabled": true,
      "interval_seconds": 30,
      "status": "running",
      "last_poll_at": "2026-08-12T10:29:45.000000",
      "next_poll_at": "2026-08-12T10:30:15.000000",
      "error_message": null
    },
    "memory": {
      "enabled": true,
      "interval_seconds": 30,
      "status": "running",
      "last_poll_at": "2026-08-12T10:29:45.000000",
      "next_poll_at": "2026-08-12T10:30:15.000000",
      "error_message": null
    }
  },
  "capabilities": {
    "cpu": true,
    "memory": true,
    "storage": true,
    "interfaces": true,
    "environment": false,
    "lldp": false,
    "routing": false,
    "vlans": false
  }
}
```

---

### 2. GET /api/v1/monitoring/data/{device_id} (Simple Testing)
**Description:** Simpler GET version for quick testing

**URL Example:**
```
http://localhost:8000/api/v1/monitoring/data/329?modules=cpu,memory&include_history=false
```

**Query Parameters:**
- `device_id` (path) - Device ID
- `modules` (query) - Comma-separated module names (default: cpu,memory,storage,interfaces)
- `include_history` (query) - true/false (default: false)
- `history_hours` (query) - Number of hours (default: 1)

**cURL Example:**
```bash
curl -X GET "http://localhost:8000/api/v1/monitoring/data/329?modules=cpu,memory,storage&include_history=true&history_hours=2" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## Request Parameters Explained

### `device_id` (required)
Device ka database ID. Example: `329`

### `modules` (optional)
Konse modules ka data chahiye. Options:
- `cpu` - CPU usage data
- `memory` - Memory usage data
- `storage` - Disk/storage data
- `interfaces` - Network interface data
- `environment` - Temperature, fan, power sensors
- Default: `["cpu", "memory", "storage", "interfaces"]`

### `include_history` (optional)
Historical data include karni hai ya nahi:
- `true` - Include time-series history data
- `false` - Only latest data (default)

### `history_hours` (optional)
Kitne hours ka history chahiye:
- Default: `1` hour
- Range: 1-720 hours (30 days)

---

## Testing Steps

### 1. First, discover aur add karo device:
```bash
# Discovery API se device discover karo
POST /api/v1/discovery/snmp

# Device add karo with monitoring auto-start
# (Ye SNMPDiscoveryPanel automatically kar deta hai)
```

### 2. Wait for first poll (30 seconds):
Monitoring scheduler 30 seconds mein first poll karega aur data database mein store karega.

### 3. Test Monitoring Data API:

**Only CPU and Memory:**
```bash
curl -X POST "http://localhost:8000/api/v1/monitoring/data" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "device_id": 329,
    "modules": ["cpu", "memory"],
    "include_history": false
  }'
```

**All Modules with History:**
```bash
curl -X POST "http://localhost:8000/api/v1/monitoring/data" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "device_id": 329,
    "modules": ["cpu", "memory", "storage", "interfaces", "environment"],
    "include_history": true,
    "history_hours": 2
  }'
```

**Simple GET Request:**
```bash
curl "http://localhost:8000/api/v1/monitoring/data/329?modules=cpu,memory" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## Response Fields Explained

### `capabilities`
Ye batata hai ki device pe konse modules supported hain:
- `true` = Module supported (data available ho sakta hai)
- `false` = Module not supported (data nahi milega)

### `monitoring_configs`
Har module ki monitoring configuration:
- `enabled`: Monitoring on/off
- `interval_seconds`: Kitne seconds mein poll hota hai (15, 30, 60, etc.)
- `status`: `running`, `stopped`, `waiting_first_poll`, `error`
- `last_poll_at`: Last successful poll ka time
- `next_poll_at`: Next poll kab hoga
- `error_message`: Agar error hai to message

### `modules.{module_name}.data`
Latest monitoring data:
- `null` = Abhi tak koi data nahi mila (monitoring start nahi hua ya supported nahi)
- Object = Latest polled data

### `modules.{module_name}.history`
Time-series historical data (jab `include_history=true` ho):
- Empty array `[]` = History nahi li gayi ya available nahi
- Array of objects = Historical data points

---

## Common Issues & Solutions

### Issue 1: `data: null` in response
**Reason:** Monitoring abhi start nahi hui ya first poll pending hai
**Solution:** 30-60 seconds wait karo, phir retry karo

### Issue 2: `supported: false` for a module
**Reason:** Device us module ko support nahi karta
**Solution:** Discovery results check karo ki konse modules Yes hain

### Issue 3: Empty `monitoring_configs`
**Reason:** Device add hua but monitoring start nahi hui
**Solution:** Monitoring manually start karo:
```bash
POST /api/v1/snmp/devices/{device_id}/monitoring/cpu/start
POST /api/v1/snmp/devices/{device_id}/monitoring/memory/start
```

### Issue 4: `status: "error"` in monitoring_configs
**Reason:** SNMP polling mein error aa rahi hai
**Solution:** Device credentials check karo, SNMP connectivity verify karo

---

## Interval Options

Monitoring intervals jo support hote hain:
- `15` seconds - Very frequent (high load)
- `30` seconds - Frequent (default)
- `60` seconds - Normal (1 minute)
- `120` seconds - Low frequency (2 minutes)
- `300` seconds - Very low (5 minutes)
- `600` seconds - Minimal (10 minutes)

Interval ko change karne ke liye:
```bash
PUT /api/v1/snmp/devices/{device_id}/monitoring/{module}
Body: {
  "interval_seconds": 60
}
```

---

## Complete Testing Flow

```bash
# Step 1: Discover device
POST /api/v1/discovery/snmp
Body: {
  "ips": ["192.168.100.1"],
  "snmp_version": "v3",
  "username": "Agnigate",
  "auth_protocol": "MD5",
  "auth_password": "Gate@123",
  "privacy_protocol": "DES",
  "privacy_password": "Gate@123",
  "security_level": "authPriv",
  "timeout_seconds": 2
}

# Step 2: Add device (frontend SNMPDiscoveryPanel automatically does this)
# Monitoring will auto-start for supported modules

# Step 3: Wait 30-60 seconds for first poll

# Step 4: Get monitoring data
POST /api/v1/monitoring/data
Body: {
  "device_id": 329,
  "modules": ["cpu", "memory", "storage", "interfaces"],
  "include_history": false
}

# Step 5: Check data aur capabilities
# Response mein dekho ki konse modules ka data mil raha hai
```

---

## Postman Collection

**Collection Name:** NMS Monitoring API

### Request 1: Get Monitoring Data (POST)
- Method: POST
- URL: `{{base_url}}/api/v1/monitoring/data`
- Headers:
  - `Content-Type: application/json`
  - `Authorization: Bearer {{token}}`
- Body (raw JSON):
```json
{
  "device_id": 329,
  "modules": ["cpu", "memory", "storage", "interfaces"],
  "include_history": false,
  "history_hours": 1
}
```

### Request 2: Get Monitoring Data (GET)
- Method: GET
- URL: `{{base_url}}/api/v1/monitoring/data/329?modules=cpu,memory&include_history=false`
- Headers:
  - `Authorization: Bearer {{token}}`

### Request 3: Get with History
- Method: POST
- URL: `{{base_url}}/api/v1/monitoring/data`
- Body:
```json
{
  "device_id": 329,
  "modules": ["cpu", "memory"],
  "include_history": true,
  "history_hours": 2
}
```

---

## Notes

1. **Database Read Only**: Ye API live SNMP poll NAHI karti, sirf database se data read karti hai
2. **Background Polling**: Data ko background polling scheduler update karta hai
3. **Fast Response**: Database read bahut fast hai (< 100ms)
4. **No Device Load**: Device pe koi extra load nahi padta
5. **Configurable Intervals**: Aap interval customize kar sakte ho (15s to 600s)

---

## Frontend Integration Example

```typescript
// Get monitoring data
async function getMonitoringData(deviceId: number, modules: string[]) {
  const response = await fetch('/api/v1/monitoring/data', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify({
      device_id: deviceId,
      modules: modules,
      include_history: false,
      history_hours: 1
    })
  });
  
  return await response.json();
}

// Usage
const data = await getMonitoringData(329, ['cpu', 'memory', 'storage']);
console.log('CPU:', data.modules.cpu.data);
console.log('Memory:', data.modules.memory.data);
```

---

Agar koi issue ho to backend logs check karo:
```bash
tail -f hardik/logs/snmp.log
```
