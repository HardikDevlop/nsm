✅ Complete Service Management Commands Ready!
🛑 STOP All Services:
Option 1: Quick One-liner
bash

pkill -f "uvicorn.*backend.main" && pkill -f "simple_monitor.py" && pkill -f "vite.*dev" && echo "✅ All NMS services stopped!"
Option 2: Safe Script (Recommended)
bash

cd /home/agnigate/Desktop/NMS/
bash stop_all_services.sh
Option 3: Manual Commands
bash

# Stop each service individually
pkill -f uvicorn          # Backend API
pkill -f simple_monitor   # Monitoring scripts
pkill -f vite             # Frontend dev server
pkill node                # Any remaining node processes
🚀 START All Services:
Option 1: Smart Script (Recommended) 
bash

cd /home/agnigate/Desktop/NMS/
bash start_all_services.sh
Option 2: Manual Commands
bash

# Backend
cd /home/agnigate/Desktop/NMS/hardik && source .venv/bin/activate && uvicorn backend.main:app --host 127.0.0.1 --port 8000 &

# Frontend
cd "/home/agnigate/Desktop/NMS/figma design" && npm run dev &

# Monitoring (Optional)
cd /home/agnigate/Desktop/NMS/hardik && python3 simple_monitor.py &
🔍 CHECK Service Status:
bash

# Quick check
ps aux | grep -E "(uvicorn|simple_monitor|vite)" | grep -v grep

# Detailed status
curl http://127.0.0.1:8000/health        # Backend health
curl http://192.168.100.40:8443/         # Frontend health
🧹 FORCE Kill (Emergency):
bash

# If normal stop doesn't work
sudo pkill -9 -f uvicorn
sudo pkill -9 -f simple_monitor
sudo pkill -9 -f vite
sudo pkill -9 -f node
📊 Service Management Commands:
Action	Command	Description
Stop All	bash stop_all_services.sh	Safe shutdown with status
Start All	bash start_all_services.sh	Smart startup with health checks
Quick Stop	pkill -f "uvicorn|simple_monitor|vite"	One-liner stop
Check Status	ps aux | grep -E "(uvicorn|vite|simple_monitor)"	See running processes
Force Kill	sudo pkill -9 -f uvicorn	Emergency stop
🎯 Best Practices:
Always use scripts for clean shutdown/startup
Check status first before starting services
Use force kill only if normal stop fails
Wait 2-3 seconds between stop and start
Check logs if services don't start properly
Ab aap easily sab kuch ek command se stop kar sakte hain! 🎯





















Option 1: Updated Script (Recommended)
bash

cd /home/agnigate/Desktop/NMS/
bash stop_all_services.sh
Option 2: Simple killall
bash

killall uvicorn; killall node; killall python3; echo "✅ All services stopped!"
Option 3: Manual ps + kill
bash

ps aux | grep -E "(uvicorn|simple_monitor|vite)" | grep -v grep | awk '{print $2}' | xargs kill && echo "✅ Services stopped!"
🔍 Check what's running first:
bash

ps aux | grep -E "(uvicorn|simple_monitor|vite|node)" | grep -v grep