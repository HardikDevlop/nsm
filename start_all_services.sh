#!/bin/bash

# NMS Services Start Script  
# Usage: bash start_all_services.sh

echo "🚀 Starting All NMS Services..."
echo ""

# Check if processes are already running
EXISTING=$(ps aux | grep -E "(uvicorn.*backend.main|simple_monitor.py|vite.*dev)" | grep -v grep | wc -l)
if [ $EXISTING -gt 0 ]; then
    echo "⚠️  Some NMS services are already running:"
    ps aux | grep -E "(uvicorn.*backend.main|simple_monitor.py|vite.*dev)" | grep -v grep
    echo ""
    read -p "Stop existing services and restart? (y/n): " RESTART
    if [ "$RESTART" = "y" ] || [ "$RESTART" = "Y" ]; then
        echo "🛑 Stopping existing services..."
        bash /home/agnigate/Desktop/NMS/stop_all_services.sh
        sleep 2
    else
        echo "❌ Cancelled. Stop services manually first."
        exit 1
    fi
fi

# Start Backend API Server
echo "1️⃣ Starting FastAPI Backend..."
cd /home/agnigate/Desktop/NMS/hardik
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
    nohup uvicorn backend.main:app --host 127.0.0.1 --port 8000 > backend.log 2>&1 &
    BACKEND_PID=$!
    echo "   ✅ Backend started (PID: $BACKEND_PID)"
    echo "   📊 API: http://127.0.0.1:8000"
    echo "   📚 Docs: http://127.0.0.1:8000/docs"
else
    echo "   ❌ Virtual environment not found at .venv/"
    echo "   💡 Run: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# Start Frontend Dev Server
echo ""
echo "2️⃣ Starting Frontend Dev Server..."
cd "/home/agnigate/Desktop/NMS/figma design"
if [ -f "package.json" ]; then
    nohup npm run dev > frontend.log 2>&1 &
    FRONTEND_PID=$!
    echo "   ✅ Frontend started (PID: $FRONTEND_PID)"
    echo "   🌐 URL: http://192.168.100.40:8443/"
else
    echo "   ❌ package.json not found"
    echo "   💡 Run: npm install"
    exit 1
fi

# Start Monitoring Scripts (Optional)
echo ""
echo "3️⃣ Starting Real-time Monitoring..."
cd /home/agnigate/Desktop/NMS/hardik
if [ -f "simple_monitor.py" ]; then
    nohup python3 simple_monitor.py > monitoring.log 2>&1 &
    MONITOR_PID=$!
    echo "   ✅ Monitoring started (PID: $MONITOR_PID)"
    echo "   📊 Collecting metrics every 2 seconds"
else
    echo "   ⚠️  simple_monitor.py not found - skipping"
    echo "   💡 Real-time monitoring is optional"
fi

# Wait for services to initialize
echo ""
echo "⏳ Waiting for services to initialize..."
sleep 5

# Check service health
echo ""
echo "🔍 Checking Service Health..."

# Check Backend
BACKEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/health 2>/dev/null || echo "000")
if [ "$BACKEND_STATUS" = "200" ]; then
    echo "   ✅ Backend API: Healthy (HTTP 200)"
else
    echo "   ⚠️  Backend API: Not responding (HTTP $BACKEND_STATUS)"
fi

# Check Frontend
FRONTEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://192.168.100.40:8443/ 2>/dev/null || echo "000")
if [ "$FRONTEND_STATUS" = "200" ]; then
    echo "   ✅ Frontend: Healthy (HTTP 200)"
else
    echo "   ⚠️  Frontend: Not responding (HTTP $FRONTEND_STATUS)"
fi

# Show running processes
echo ""
echo "📊 NMS Processes Status:"
ps aux | grep -E "(uvicorn.*backend.main|simple_monitor.py|vite.*dev)" | grep -v grep | while read line; do
    echo "   🟢 $line"
done

echo ""
echo "🎉 NMS System Started Successfully!"
echo ""
echo "🌐 Access Points:"
echo "   📊 Main Dashboard: http://192.168.100.40:8443/"
echo "   🔧 API Documentation: http://127.0.0.1:8000/docs"
echo "   🖥️  Device Management: http://192.168.100.40:8443/snmp/devices"
echo "   🔍 Network Discovery: http://192.168.100.40:8443/snmp/discovery"
echo ""
echo "📝 Logs Location:"
echo "   🔙 Backend: /home/agnigate/Desktop/NMS/hardik/backend.log"
echo "   🎨 Frontend: /home/agnigate/Desktop/NMS/figma design/frontend.log"
echo "   📊 Monitoring: /home/agnigate/Desktop/NMS/hardik/monitoring.log"
echo ""
echo "🛑 To stop all services: bash stop_all_services.sh"