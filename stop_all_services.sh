#!/bin/bash

# NMS Services Stop Script
# Usage: bash stop_all_services.sh

echo "🛑 Stopping All NMS Services..."
echo ""

# Function to kill processes by pattern
kill_by_pattern() {
    local pattern=$1
    local name=$2
    local pids=$(ps aux | grep "$pattern" | grep -v grep | awk '{print $2}')
    
    if [ -n "$pids" ]; then
        echo $pids | xargs kill 2>/dev/null
        if [ $? -eq 0 ]; then
            echo "   ✅ $name stopped"
            return 0
        else
            echo "   ⚠️  Failed to stop $name"
            return 1
        fi
    else
        echo "   ℹ️  $name not running"
        return 0
    fi
}

# Stop Backend API Server
echo "1️⃣ Stopping FastAPI Backend..."
kill_by_pattern "uvicorn.*backend.main" "Backend API server"

# Stop Frontend Dev Server  
echo "2️⃣ Stopping Frontend Dev Server..."
kill_by_pattern "vite.*dev" "Frontend dev server"

# Stop Monitoring Scripts
echo "3️⃣ Stopping Monitoring Scripts..."
kill_by_pattern "simple_monitor.py" "Monitoring scripts"

# Stop any remaining Node processes
echo "4️⃣ Stopping Node.js processes..."
kill_by_pattern "node.*figma design" "Node.js processes"

# Alternative killall method (fallback)
echo ""
echo "🔄 Trying alternative stop methods..."
killall uvicorn 2>/dev/null && echo "   ✅ uvicorn killed via killall"
killall node 2>/dev/null && echo "   ✅ node killed via killall"  
killall python3 2>/dev/null && echo "   ✅ python3 killed via killall"

# Check for any remaining processes
echo ""
echo "🔍 Checking for remaining NMS processes..."
REMAINING=$(ps aux | grep -E "(uvicorn|simple_monitor|vite|figma design)" | grep -v grep | wc -l)

if [ $REMAINING -eq 0 ]; then
    echo "✅ All NMS services stopped successfully!"
    echo ""
    echo "📊 System is now clean. You can safely:"
    echo "   - Restart services with start commands"
    echo "   - Shutdown the system"
    echo "   - Update code without conflicts"
else
    echo "⚠️  Found $REMAINING remaining processes:"
    ps aux | grep -E "(uvicorn|simple_monitor|vite|figma design)" | grep -v grep
    echo ""
    echo "💡 Use 'kill -9 <PID>' to force stop if needed"
fi

echo ""
echo "🎯 To restart services, use:"
echo "   bash start_all_services.sh"
echo "   OR follow README_COMPLETE_PROJECT.md"