#!/bin/bash

# Complete NMS Startup Script
echo "🚀 Starting Complete NMS System..."

# Stop any existing processes
echo "🛑 Stopping existing services..."
pkill -f simple_monitor.py 2>/dev/null
pkill -f continuous_monitoring.py 2>/dev/null

# Navigate to project directory
cd "/home/agnigate/Desktop/NMS/hardik"

# Check if backend is running
check_backend() {
    curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/api/v1/devices
}

# Start backend if needed
if [ "$(check_backend)" != "200" ] && [ "$(check_backend)" != "401" ]; then
    echo "🔧 Backend not running, starting..."
    
    # Activate venv if exists
    if [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
    fi
    
    # Start backend
    nohup python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 > backend.log 2>&1 &
    echo "📡 Backend starting..."
    
    # Wait for backend
    for i in {1..15}; do
        if [ "$(check_backend)" = "200" ] || [ "$(check_backend)" = "401" ]; then
            echo "✅ Backend ready!"
            break
        fi
        sleep 2
    done
else
    echo "✅ Backend already running"
fi

# Setup sample data
echo "📊 Setting up data..."
python3 setup_monitoring.py > setup.log 2>&1

# Start monitoring service
echo "📈 Starting continuous monitoring..."
nohup python3 simple_monitor.py > monitoring_live.log 2>&1 &

# Wait and verify
sleep 3

if pgrep -f simple_monitor.py > /dev/null; then
    echo "✅ Monitoring service started successfully!"
else
    echo "❌ Failed to start monitoring service"
    exit 1
fi

echo ""
echo "🎉 NMS System Status:"
echo "   Backend:    $(check_backend) - $([ "$(check_backend)" = "200" ] || [ "$(check_backend)" = "401" ] && echo 'Running ✅' || echo 'Stopped ❌')"
echo "   Frontend:   http://192.168.100.40:8443 🌐"
echo "   Monitoring: $(pgrep -f simple_monitor.py > /dev/null && echo 'Running ✅' || echo 'Stopped ❌')"
echo ""
echo "📁 Log files:"
echo "   Backend:    tail -f backend.log"
echo "   Monitoring: tail -f monitoring_live.log" 
echo "   Setup:      tail -f setup.log"
echo ""
echo "🛑 To stop all:"
echo "   pkill -f uvicorn && pkill -f simple_monitor.py"