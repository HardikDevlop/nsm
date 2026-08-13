# 📡 NMS API Documentation

## 🔧 **Base Configuration**

### **Base URL:**
```
Production:  https://your-domain.com/api/v1
Development: http://127.0.0.1:8000/api/v1
```

### **Authentication:**
```bash
# Login to get token
POST /auth/login
{
  "email": "user@example.com",
  "password": "password123"
}

# Use token in headers
Authorization: Bearer <your_jwt_token>
```

---

## 🔐 **Authentication Endpoints**

### **Login**
```http
POST /auth/login
Content-Type: application/json

{
  "email": "admin@example.com",
  "password": "password123"
}
```

**Response:**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": {
    "id": 1,
    "email": "admin@example.com",
    "role": "admin"
  }
}
```

### **Refresh Token**
```http
POST /auth/refresh
Authorization: Bearer <token>
```

### **Logout**
```http
POST /auth/logout
Authorization: Bearer <token>
```

---

## 🖥️ **Device Management**

### **List All Devices**
```http
GET /devices?skip=0&limit=100
Authorization: Bearer <token>
```

**Response:**
```json
[
  {
    "id": 333,
    "hostname": "AgniGATE",
    "ip_address": "192.168.100.1",
    "mac_address": "aa:bb:cc:dd:ee:ff",
    "status": "online",
    "device_type": "router",
    "monitoring_status": "enabled",
    "created_at": "2026-08-13T10:30:00Z",
    "last_seen": "2026-08-13T15:30:00Z"
  }
]
```

### **Add New Device**
```http
POST /devices
Authorization: Bearer <token>
Content-Type: application/json

{
  "hostname": "NewRouter",
  "ip_address": "192.168.1.100",
  "device_type": "router",
  "snmp_community": "public",
  "snmp_version": "v2c"
}
```

### **Update Device**
```http
PUT /devices/{device_id}
Authorization: Bearer <token>
Content-Type: application/json

{
  "hostname": "UpdatedName",
  "monitoring_status": "enabled"
}
```

### **Delete Device**
```http
DELETE /devices/{device_id}
Authorization: Bearer <token>
```

### **Get Device Details**
```http
GET /devices/{device_id}
Authorization: Bearer <token>
```

---

## 📊 **Monitoring Data**

### **Get Device Metrics**
```http
GET /devices/{device_id}/metrics?hours=24
Authorization: Bearer <token>
```

**Response:**
```json
[
  {
    "id": 1,
    "device_id": 333,
    "cpu_usage": 45.2,
    "memory_usage": 67.8,
    "disk_usage": 23.4,
    "bandwidth_in": 1024000,
    "bandwidth_out": 512000,
    "latency": 12.5,
    "packet_loss": 0.1,
    "created_at": "2026-08-13T15:30:00Z"
  }
]
```

### **Get Latest Metrics (Real-time)**
```http
POST /monitoring/data
Authorization: Bearer <token>
Content-Type: application/json

{
  "device_id": 333,
  "modules": ["cpu", "memory", "interfaces", "storage"]
}
```

**Response:**
```json
{
  "device_id": 333,
  "hostname": "AgniGATE",
  "status": "online",
  "capabilities": {
    "cpu": true,
    "memory": true,
    "storage": true,
    "interfaces": true,
    "environment": false
  },
  "modules": {
    "cpu": {
      "supported": true,
      "data": {
        "utilization_percent": 45.2,
        "load_1min": 0.8,
        "load_5min": 0.6,
        "load_15min": 0.4,
        "cores": 4,
        "last_updated": "2026-08-13T15:30:00+05:30"
      }
    },
    "memory": {
      "supported": true,
      "data": {
        "total_mb": 8192,
        "used_mb": 3686,
        "free_mb": 4506,
        "utilization_percent": 45.0,
        "swap_total_mb": 2048,
        "swap_used_mb": 0,
        "last_updated": "2026-08-13T15:30:00+05:30"
      }
    },
    "storage": {
      "supported": true,
      "data": {
        "volumes": [
          {
            "name": "/",
            "total_gb": 120.0,
            "used_gb": 4.8,
            "free_gb": 115.2,
            "utilization_percent": 3.99,
            "filesystem": "ext4"
          }
        ],
        "last_updated": "2026-08-13T15:30:00+05:30"
      }
    }
  }
}
```

### **Start Device Monitoring**
```http
POST /monitoring/start
Authorization: Bearer <token>
Content-Type: application/json

{
  "device_id": 333,
  "modules": ["cpu", "memory", "interfaces"],
  "interval_seconds": 60
}
```

### **Stop Device Monitoring**
```http
POST /monitoring/stop
Authorization: Bearer <token>
Content-Type: application/json

{
  "device_id": 333
}
```

---

## 🔍 **Network Discovery**

### **Start Network Scan**
```http
POST /discovery/chunked-scan
Authorization: Bearer <token>
Content-Type: application/json

{
  "network_range": "192.168.1.0/24",
  "scan_icmp": true,
  "scan_snmp": true,
  "scan_ports": true,
  "snmp_community": "public",
  "timeout_ms": 3000,
  "max_hosts": 254
}
```

**Response:**
```json
{
  "job_id": "scan_12345",
  "total_ips": 254,
  "chunks_total": 10,
  "chunk_size": 25,
  "status": "running"
}
```

### **Get Scan Progress**
```http
GET /discovery/chunked-scan/{job_id}/progress
Authorization: Bearer <token>
```

**Response (Server-Sent Events):**
```
event: progress
data: {"chunks_completed": 3, "chunks_total": 10, "progress_pct": 30}

event: discovered
data: {"ip": "192.168.1.100", "hostname": "Router1", "capabilities": ["snmp", "icmp"]}

event: complete
data: {"discovered_count": 15, "total_scanned": 254, "elapsed_seconds": 45}
```

### **Get Discovery Results**
```http
GET /discovery/chunked-scan/{job_id}/results
Authorization: Bearer <token>
```

### **Add Discovered Devices**
```http
POST /discovery/add-devices
Authorization: Bearer <token>
Content-Type: application/json

{
  "devices": [
    {
      "ip_address": "192.168.1.100",
      "hostname": "Router1",
      "snmp_community": "public",
      "start_monitoring": true
    }
  ]
}
```

---

## 📈 **Analytics & Reports**

### **System Overview**
```http
GET /overview
Authorization: Bearer <token>
```

**Response:**
```json
{
  "devices": {
    "total": 25,
    "online": 22,
    "offline": 3,
    "critical": 1
  },
  "alerts": {
    "total": 5,
    "critical": 1,
    "warning": 3,
    "info": 1
  },
  "performance": {
    "avg_cpu": 45.2,
    "avg_memory": 67.8,
    "avg_latency": 12.5,
    "network_utilization": 23.4
  },
  "last_updated": "2026-08-13T15:30:00+05:30"
}
```

### **Get Alerts**
```http
GET /alerts?severity=critical&status=active&limit=50
Authorization: Bearer <token>
```

**Response:**
```json
[
  {
    "id": 1,
    "device_id": 333,
    "severity": "critical",
    "title": "High CPU Usage",
    "description": "CPU utilization is above 90% for 5 minutes",
    "status": "active",
    "created_at": "2026-08-13T15:25:00+05:30",
    "acknowledged_by": null,
    "resolved_at": null
  }
]
```

### **Get Events**
```http
GET /events?device_id=333&hours=24
Authorization: Bearer <token>
```

### **Device History**
```http
GET /devices/{device_id}/history?hours=24
Authorization: Bearer <token>
```

---

## 🌐 **SNMP-Specific Endpoints**

### **Test SNMP Connection**
```http
POST /snmp/test
Authorization: Bearer <token>
Content-Type: application/json

{
  "ip_address": "192.168.1.100",
  "snmp_version": "v2c",
  "community": "public"
}
```

### **Get SNMP Capabilities**
```http
POST /snmp/capabilities
Authorization: Bearer <token>
Content-Type: application/json

{
  "ip_address": "192.168.1.100",
  "snmp_version": "v2c",
  "community": "public"
}
```

### **SNMP Walk**
```http
POST /snmp/walk
Authorization: Bearer <token>
Content-Type: application/json

{
  "ip_address": "192.168.1.100",
  "oid": "1.3.6.1.2.1.1",
  "snmp_version": "v2c",
  "community": "public"
}
```

---

## ⚡ **Real-time Endpoints**

### **WebSocket Connection**
```javascript
// Connect to real-time updates
const ws = new WebSocket('ws://127.0.0.1:8000/ws/monitoring');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Real-time update:', data);
};
```

### **Server-Sent Events**
```javascript
// Subscribe to monitoring events
const eventSource = new EventSource('/api/v1/events/stream?device_id=333');

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Monitoring event:', data);
};
```

---

## 🔧 **Administrative Endpoints**

### **System Health**
```http
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2026-08-13T15:30:00Z",
  "database": {
    "connected": true,
    "response_time_ms": 5
  },
  "services": {
    "snmp_polling": "running",
    "monitoring": "running",
    "discovery": "idle"
  },
  "version": "1.0.0"
}
```

### **System Stats**
```http
GET /admin/stats
Authorization: Bearer <admin_token>
```

### **Service Control**
```http
POST /admin/services/{service_name}/restart
Authorization: Bearer <admin_token>
```

---

## 🚨 **Error Responses**

### **Common HTTP Status Codes:**
- `200` - Success
- `201` - Created
- `400` - Bad Request (validation error)
- `401` - Unauthorized (invalid token)
- `403` - Forbidden (insufficient permissions)
- `404` - Not Found
- `422` - Unprocessable Entity (validation error)
- `500` - Internal Server Error

### **Error Response Format:**
```json
{
  "error": {
    "code": "DEVICE_NOT_FOUND",
    "message": "Device with ID 999 not found",
    "details": {
      "device_id": 999,
      "timestamp": "2026-08-13T15:30:00Z"
    }
  }
}
```

### **Validation Errors:**
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid input data",
    "details": {
      "field_errors": {
        "ip_address": ["Invalid IP address format"],
        "snmp_community": ["Community string is required"]
      }
    }
  }
}
```

---

## 📚 **Code Examples**

### **Python (requests)**
```python
import requests

# Login
response = requests.post(
    'http://127.0.0.1:8000/api/v1/auth/login',
    json={'email': 'admin@example.com', 'password': 'password123'}
)
token = response.json()['access_token']

# Get devices
headers = {'Authorization': f'Bearer {token}'}
devices = requests.get(
    'http://127.0.0.1:8000/api/v1/devices',
    headers=headers
).json()

print(f"Found {len(devices)} devices")
```

### **JavaScript (fetch)**
```javascript
// Login and get token
const login = async () => {
  const response = await fetch('/api/v1/auth/login', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      email: 'admin@example.com',
      password: 'password123'
    })
  });
  const data = await response.json();
  return data.access_token;
};

// Get monitoring data
const getMonitoringData = async (deviceId, token) => {
  const response = await fetch('/api/v1/monitoring/data', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      device_id: deviceId,
      modules: ['cpu', 'memory', 'interfaces']
    })
  });
  return response.json();
};
```

### **curl Examples**
```bash
# Login
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"password123"}' | \
  jq -r '.access_token')

# Get devices
curl -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/v1/devices

# Start monitoring
curl -X POST http://127.0.0.1:8000/api/v1/monitoring/start \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"device_id": 333, "modules": ["cpu", "memory"]}'
```

---

## 🔍 **Rate Limiting**

### **Default Limits:**
- **Authentication:** 10 requests/minute
- **Device Operations:** 100 requests/minute
- **Monitoring Data:** 1000 requests/minute
- **Discovery:** 5 scans/hour per user

### **Rate Limit Headers:**
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1692878400
```

---

## 📖 **Interactive API Documentation**

Visit the interactive Swagger UI documentation at:
- **Development:** `http://127.0.0.1:8000/docs`
- **Production:** `https://your-domain.com/docs`

---

**🎯 This API documentation covers all available endpoints for NMS integration!** 📡