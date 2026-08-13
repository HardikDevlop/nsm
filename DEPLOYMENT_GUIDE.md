# 🚀 NMS Deployment Guide

## 📋 **Production Deployment Checklist**

### **Pre-deployment Setup:**
```bash
# 1. Check system requirements
python3 --version  # Python 3.8+
node --version      # Node 16+
postgres --version  # PostgreSQL 12+
```

### **Backend Deployment:**
```bash
# 1. Setup virtual environment
cd /home/agnigate/Desktop/NMS/hardik
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Setup database
createdb nms_production
export DATABASE_URL="postgresql://user:pass@localhost/nms_production"

# 4. Start production server
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### **Frontend Deployment:**
```bash
# 1. Install dependencies
cd "/home/agnigate/Desktop/NMS/figma design"
npm install

# 2. Build for production
npm run build

# 3. Serve with nginx/apache
cp -r dist/* /var/www/html/nms/
```

### **Services Setup:**
```bash
# 1. Create systemd services
sudo cp deploy/nms-backend.service /etc/systemd/system/
sudo cp deploy/nms-monitor.service /etc/systemd/system/

# 2. Enable and start
sudo systemctl enable nms-backend nms-monitor
sudo systemctl start nms-backend nms-monitor
```

## 📊 **Performance Tuning**

### **Database Optimization:**
```sql
-- Create indexes for performance
CREATE INDEX idx_device_metrics_created_at ON device_metrics(created_at);
CREATE INDEX idx_devices_status ON devices(status);
CREATE INDEX idx_alerts_severity ON alerts(severity, status);
```

### **Backend Optimization:**
```python
# In main.py - add these configurations
app = FastAPI(
    title="NMS API",
    docs_url="/docs" if DEBUG else None,  # Disable docs in production
)

# Add connection pooling
SQLALCHEMY_DATABASE_URL = "postgresql://user:pass@localhost/nms?pool_size=20&max_overflow=30"
```

### **Frontend Optimization:**
```typescript
// Enable production optimizations
// In vite.config.ts
export default defineConfig({
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom'],
          charts: ['recharts'],
        }
      }
    }
  }
})
```

## 🔒 **Security Hardening**

### **Backend Security:**
```bash
# 1. Generate strong JWT secret
openssl rand -base64 32 > jwt_secret.txt

# 2. Setup firewall
sudo ufw allow 8000/tcp  # API port
sudo ufw allow 8443/tcp  # Frontend port
sudo ufw enable

# 3. SSL/TLS certificates
certbot --nginx -d your-domain.com
```

### **Database Security:**
```sql
-- Create application user with limited privileges
CREATE USER nms_app WITH PASSWORD 'strong_password';
GRANT CONNECT ON DATABASE nms_production TO nms_app;
GRANT USAGE ON SCHEMA public TO nms_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO nms_app;
```

### **Environment Variables:**
```bash
# Create secure .env file
cat > .env << EOF
DATABASE_URL=postgresql://nms_app:strong_password@localhost/nms_production
JWT_SECRET_KEY=$(cat jwt_secret.txt)
CORS_ORIGINS=["https://your-domain.com"]
DEBUG=false
ENCRYPTION_KEY=$(openssl rand -base64 32)
EOF

chmod 600 .env
```

## 📈 **Monitoring & Logging**

### **Application Monitoring:**
```bash
# 1. Setup log rotation
sudo cp deploy/nms-logrotate /etc/logrotate.d/nms

# 2. Monitor service health
curl http://localhost:8000/health
```

### **Performance Monitoring:**
```python
# Add to main.py
import time
from fastapi import Request

@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response
```

## 🔄 **Backup & Recovery**

### **Database Backup:**
```bash
# Daily backup script
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
pg_dump nms_production > /backup/nms_backup_$DATE.sql
find /backup -name "nms_backup_*.sql" -mtime +7 -delete
```

### **Application Backup:**
```bash
# Backup configuration and code
tar -czf nms_app_backup_$(date +%Y%m%d).tar.gz \
  /home/agnigate/Desktop/NMS/ \
  --exclude=node_modules \
  --exclude=.venv \
  --exclude=dist
```

## 📊 **Health Checks**

### **Service Health Endpoints:**
```python
# Add to backend/api/health.py
@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc),
        "database": await check_database_health(),
        "services": await check_services_health()
    }
```

### **Monitoring Script:**
```bash
#!/bin/bash
# monitor_nms.sh
API_URL="http://localhost:8000/health"
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" $API_URL)

if [ $RESPONSE -eq 200 ]; then
    echo "NMS API is healthy"
else
    echo "NMS API is down (HTTP $RESPONSE)"
    systemctl restart nms-backend
fi
```

## 🌐 **Load Balancing**

### **Nginx Configuration:**
```nginx
upstream nms_backend {
    server 127.0.0.1:8000;
    server 127.0.0.1:8001;
    server 127.0.0.1:8002;
}

server {
    listen 80;
    server_name your-domain.com;
    
    location /api/ {
        proxy_pass http://nms_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    
    location / {
        root /var/www/html/nms;
        try_files $uri $uri/ /index.html;
    }
}
```

## 🐳 **Docker Deployment**

### **Dockerfile:**
```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### **Docker Compose:**
```yaml
version: '3.8'
services:
  db:
    image: postgres:13
    environment:
      POSTGRES_DB: nms_production
      POSTGRES_USER: nms_app
      POSTGRES_PASSWORD: strong_password
    volumes:
      - postgres_data:/var/lib/postgresql/data

  backend:
    build: ./hardik
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://nms_app:strong_password@db/nms_production
    depends_on:
      - db

  frontend:
    build: "./figma design"
    ports:
      - "8443:80"
    depends_on:
      - backend

volumes:
  postgres_data:
```

## 📋 **Maintenance Tasks**

### **Daily Tasks:**
```bash
# 1. Check service status
systemctl status nms-backend nms-monitor

# 2. Monitor disk space
df -h | grep -E "(/$|/var)"

# 3. Check application logs
tail -f /var/log/nms/application.log
```

### **Weekly Tasks:**
```bash
# 1. Update system packages
sudo apt update && sudo apt upgrade

# 2. Cleanup old logs
find /var/log/nms -name "*.log.*" -mtime +30 -delete

# 3. Database maintenance
psql -d nms_production -c "VACUUM ANALYZE;"
```

### **Monthly Tasks:**
```bash
# 1. Security updates
sudo apt list --upgradable | grep security

# 2. Performance review
analyze_performance.py --month $(date +%m) --year $(date +%Y)

# 3. Backup verification
verify_backup.sh /backup/latest_backup.sql
```

## 🚨 **Troubleshooting Guide**

### **Common Issues:**

**1. Database Connection Failed**
```bash
# Check PostgreSQL service
sudo systemctl status postgresql
sudo systemctl restart postgresql

# Verify connection
psql -h localhost -U nms_app -d nms_production -c "SELECT 1;"
```

**2. API Server Won't Start**
```bash
# Check port conflicts
sudo netstat -tlnp | grep 8000

# Check logs
journalctl -u nms-backend -f

# Restart service
sudo systemctl restart nms-backend
```

**3. Frontend Build Errors**
```bash
# Clear cache
rm -rf node_modules/.vite
npm ci

# Rebuild
npm run build
```

**4. SNMP Monitoring Issues**
```bash
# Test SNMP connection
snmpwalk -v2c -c public 192.168.1.1 1.3.6.1.2.1.1.1.0

# Check credentials
python3 -c "from backend.services.snmp_client import test_connection; test_connection('192.168.1.1')"
```

## 📞 **Support Contacts**

- **System Administrator:** Check logs in `/var/log/nms/`
- **Database Issues:** PostgreSQL logs in `/var/log/postgresql/`
- **Application Issues:** FastAPI logs via journalctl
- **Performance Issues:** Monitor with `htop` and `iotop`

---

**🎯 This deployment guide ensures production-ready NMS installation!** 🚀