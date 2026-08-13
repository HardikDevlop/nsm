#!/bin/bash

# Continuous Monitoring Startup Script
# Automatically starts backend + monitoring service

echo "🚀 Starting NMS with Continuous Monitoring..."

# Check if Python dependencies are available
if ! python3 -c "import requests, sqlalchemy, asyncio" 2>/dev/null; then
    echo "📦 Installing required Python packages..."
    pip3 install requests sqlalchemy asyncio psycopg2-binary
fi

# Function to check if backend is running
check_backend() {
    curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/api/v1/devices
}

# Start backend if not running
if [ "$(check_backend)" != "200" ] && [ "$(check_backend)" != "401" ]; then
    echo "🔧 Starting backend server..."
    cd "/home/agnigate/Desktop/NMS/hardik"
    
    # Activate virtual environment if it exists
    if [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
        echo "✅ Activated Python virtual environment"
    fi
    
    # Start backend in background
    nohup python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 > backend.log 2>&1 &
    BACKEND_PID=$!
    echo "📡 Backend started with PID: $BACKEND_PID"
    
    # Wait for backend to be ready
    echo "⏳ Waiting for backend to be ready..."
    for i in {1..30}; do
        if [ "$(check_backend)" = "200" ] || [ "$(check_backend)" = "401" ]; then
            echo "✅ Backend is ready!"
            break
        fi
        sleep 2
        echo "   Attempt $i/30..."
    done
else
    echo "✅ Backend already running"
fi

# Setup sample data
echo "📊 Setting up sample data..."
python3 setup_monitoring.py

# Check if monitoring is already running
if pgrep -f "continuous_monitoring.py" > /dev/null; then
    echo "⚠️ Monitoring service already running"
    echo "   To restart: pkill -f continuous_monitoring.py && ./start_monitoring.sh"
else
    # Start continuous monitoring
    echo "📈 Starting continuous monitoring service..."
    nohup python3 continuous_monitoring.py > monitoring.log 2>&1 &
    MONITORING_PID=$!
    echo "✅ Monitoring started with PID: $MONITORING_PID"
    
    # Wait a moment and check if it's still running
    sleep 3
    if pgrep -f "continuous_monitoring.py" > /dev/null; then
        echo "✅ Monitoring service is running successfully!"
    else
        echo "❌ Monitoring service failed to start. Check monitoring.log for errors."
        exit 1
    fi
fi

echo ""
echo "🎉 NMS with Continuous Monitoring is now running!"
echo ""
echo "📊 Services Status:"
echo "   Backend:    http://127.0.0.1:8000 ($(check_backend))"
echo "   Frontend:   http://192.168.100.40:8443"
echo "   Monitoring: $(pgrep -f 'continuous_monitoring.py' > /dev/null && echo 'Running ✅' || echo 'Stopped ❌')"
echo ""
echo "📁 Log Files:"
echo "   Backend:    backend.log"
echo "   Monitoring: monitoring.log"
echo ""
echo "🛑 To stop services:"
echo "   pkill -f uvicorn"
echo "   pkill -f continuous_monitoring.py"
echo ""
echo "💡 Monitor logs in real-time:"
echo "   tail -f monitoring.log"
echo "   tail -f backend.log"