# 👤 NMS User Manual - Complete Guide

## 🎯 **Getting Started**

### **Login to System**
1. Open browser and go to: `http://192.168.100.40:8443/`
2. Enter your credentials:
   - **Email:** admin@example.com
   - **Password:** password123
3. Click **"Login"** button

### **First Time Setup**
After login, you'll see the main dashboard. System is ready to use immediately!

---

## 🏠 **Dashboard Overview**

### **Main Dashboard Features:**
- **Real-time Statistics:** Live device counts, CPU averages, data rates
- **System Health:** Overall network health score
- **Active Alerts:** Critical notifications and warnings
- **Traffic Overview:** Network utilization charts
- **Device Status:** Online/offline device summary

### **Real-time Controls (Top Right):**
Click on **"REAL-TIME"** button to access:
- **Refresh Intervals:** 2s, 5s, 10s, 15s, 30s, 1m
- **Time Windows:** 5s, 10s, 15s, 20s, 25s, 30s, 1m, 2m, 5m
- **Live/Pause:** Start/stop real-time updates
- **Advanced Stats:** Data points, memory usage, next refresh

---

## 🖥️ **Device Management**

### **View All Devices**
1. Go to **"Device Management"** or visit: `http://192.168.100.40:8443/snmp/devices`
2. You'll see a list of all network devices with:
   - Device name and IP address
   - Current status (Online/Offline)
   - Device type (Router, Switch, etc.)
   - Last seen timestamp

### **Add New Device**
1. Click **"Add Device"** button
2. Fill in the form:
   - **Hostname:** Device name (e.g., "Router-01")
   - **IP Address:** Device IP (e.g., "192.168.1.100")
   - **SNMP Community:** Usually "public" or "private"
   - **SNMP Version:** v2c (recommended) or v3
3. Click **"Save"** to add the device

### **Edit Device**
1. Find the device in the list
2. Click the **"Edit"** (pencil) icon
3. Modify the information
4. Click **"Save Changes"**

### **Delete Device**
1. Find the device in the list
2. Click the **"Delete"** (trash) icon
3. Confirm deletion in the popup
4. Device will be removed from monitoring

---

## 🔍 **Network Discovery**

### **Automatic Device Discovery**
1. Go to **"Discovery"** page: `http://192.168.100.40:8443/snmp/discovery`
2. Enter network range (e.g., "192.168.1.0/24")
3. Configure scan options:
   - **ICMP Ping:** Check device availability
   - **SNMP Scan:** Detect SNMP-enabled devices
   - **Port Scan:** Check open ports
4. Click **"Start Scan"**

### **View Discovery Results**
1. Wait for scan to complete (shows progress bar)
2. Review discovered devices list:
   - **IP Address:** Device IP
   - **Hostname:** Detected device name
   - **Capabilities:** What the device supports
   - **SNMP Status:** Yes/No badges
3. Select devices you want to add
4. Click **"Add Selected Devices"**

### **Advanced Discovery Options**
- **Authentication:** Choose MD5 or SHA for SNMP v3
- **Privacy:** Select DES or AES encryption
- **Timeout:** Adjust scan timeout (default: 3 seconds)
- **Max Hosts:** Limit number of IPs to scan

---

## 📊 **Device Monitoring**

### **Per-Device Monitoring**
1. Go to **"Device Monitoring"**: `http://192.168.100.40:8443/device-monitoring`
2. Select a device from the list
3. View detailed monitoring dashboard:
   - **Live Status:** Current UP/DOWN status
   - **Availability Stats:** Uptime percentage
   - **Latency Charts:** Network response times
   - **Status History:** Timeline of changes

### **Start/Stop Monitoring**
1. On device monitoring page
2. Click **"START MONITORING"** or **"STOP MONITORING"**
3. System will begin/stop collecting data every 2 seconds
4. View real-time ping results in the **"Live Ping History"** section

### **Understanding Device Status**
- **UP (Green):** Device is responding normally
- **DOWN (Red):** Device is not responding
- **? (Yellow):** Status unknown or timeout

---

## 📈 **Performance Monitoring**

### **CPU Monitoring** (for supported devices)
- **URL:** `http://192.168.100.40:8443/snmp/cpu/333`
- **Shows:** CPU utilization percentage, load averages, core usage
- **Updates:** Real-time data every 30 seconds

### **Memory Monitoring** (for supported devices)
- **URL:** `http://192.168.100.40:8443/snmp/memory/333`
- **Shows:** Memory usage, available RAM, swap usage
- **Charts:** Usage trends over time

### **Storage Monitoring** (for supported devices)
- **URL:** `http://192.168.100.40:8443/snmp/storage/333`
- **Shows:** Disk usage per volume, filesystem types
- **Alerts:** Warns when storage is above 80%

### **Interface Monitoring** (for all devices)
- **URL:** `http://192.168.100.40:8443/snmp/interfaces/333`
- **Shows:** Network interface status, traffic statistics
- **Metrics:** RX/TX bytes, interface speed, errors

---

## 🌐 **Server Monitoring**

### **System Servers**
1. Go to **"Server Monitoring"**: `http://192.168.100.40:8443/servers`
2. View server health dashboards
3. Monitor system resources:
   - CPU usage across servers
   - Memory utilization
   - Service status
   - Application performance

---

## 🚨 **Alerts & Notifications**

### **View Active Alerts**
- Dashboard shows alert summary
- Red badges indicate critical alerts
- Yellow badges show warnings
- Green means everything is normal

### **Alert Types**
- **Critical:** Immediate attention required (device down, high CPU)
- **Warning:** Potential issues (high memory usage, interface errors)
- **Info:** Informational messages (device state changes)

### **Alert Management**
- Alerts auto-resolve when conditions improve
- Historical alerts visible in device monitoring pages
- Status change notifications in real-time

---

## ⚙️ **Settings & Configuration**

### **User Account**
- Change password via user menu (top right)
- Update email preferences
- Set default dashboard settings

### **System Preferences**
- **Default Refresh Rate:** Set preferred update frequency
- **Time Window:** Choose default historical data range
- **Timezone:** System uses India Standard Time (IST)

### **Device Settings**
- **SNMP Credentials:** Secure storage of community strings
- **Monitoring Intervals:** Per-device polling frequency
- **Alert Thresholds:** Custom alert triggers

---

## 📱 **Mobile Usage**

### **Responsive Design**
- Full functionality on smartphones and tablets
- Touch-friendly interface
- Optimized charts and graphs for small screens

### **Mobile Tips**
- Use landscape mode for better chart viewing
- Swipe to navigate between dashboard sections
- Tap and hold for additional options

---

## 🔧 **Troubleshooting**

### **Common Issues**

**1. Device Shows as Offline**
- **Check:** Device is powered on and connected
- **Verify:** IP address is correct and reachable
- **Test:** Ping device manually: `ping 192.168.1.100`
- **Solution:** Update device IP or check network connectivity

**2. SNMP Data Not Available**
- **Check:** SNMP community string is correct
- **Verify:** Device supports SNMP (most routers/switches do)
- **Test:** Use SNMP walk tool to verify: `snmpwalk -v2c -c public 192.168.1.100`
- **Solution:** Correct community string or enable SNMP on device

**3. Discovery Not Finding Devices**
- **Check:** Network range is correct (e.g., 192.168.1.0/24)
- **Verify:** Devices are in the same subnet
- **Increase:** Scan timeout if network is slow
- **Solution:** Try smaller IP ranges or check firewall settings

**4. Real-time Data Not Updating**
- **Check:** Internet connection is stable
- **Verify:** Browser is not blocking JavaScript
- **Refresh:** Page with Ctrl+F5 (hard refresh)
- **Solution:** Clear browser cache or try different browser

**5. Login Issues**
- **Check:** Username and password are correct
- **Verify:** Caps Lock is not enabled
- **Try:** Default credentials: admin@example.com / password123
- **Solution:** Contact administrator for password reset

### **Performance Tips**

**For Better Performance:**
- Use moderate refresh intervals (5-10 seconds)
- Limit time windows to needed data (30s-2m for real-time)
- Monitor only necessary devices
- Close unused browser tabs

**For Large Networks:**
- Discover devices in smaller batches
- Use longer polling intervals (60+ seconds)
- Monitor critical devices more frequently
- Set up device groups for easier management

---

## 📚 **Advanced Features**

### **Real-time Data Controls**
```
🎛️ Access via Dashboard header:
├── Refresh Rate: How often data updates
├── Time Window: How much history to show
├── Live/Pause: Control real-time updates
└── Statistics: Data points, memory usage
```

### **Device Capabilities**
```
✅ Supported Features per Device:
├── CPU Monitoring (servers, routers)
├── Memory Monitoring (servers, routers)
├── Storage Monitoring (servers)
├── Interface Monitoring (all network devices)
├── SNMP v2c/v3 Support
└── Real-time Status Monitoring
```

### **Data Export** (Planned)
- Export device lists to CSV
- Generate PDF reports
- Historical data exports
- Custom dashboard screenshots

---

## 🎯 **Best Practices**

### **Device Management**
1. **Use descriptive hostnames** (e.g., "Core-Switch-01" not "Switch1")
2. **Group related devices** by location or function
3. **Regular health checks** - monitor critical devices more frequently
4. **Keep credentials secure** - use strong SNMP community strings
5. **Update device info** when making network changes

### **Monitoring Setup**
1. **Start with critical devices** - routers, core switches, servers
2. **Use appropriate intervals** - 60 seconds for most devices
3. **Set meaningful thresholds** for CPU, memory, storage alerts
4. **Monitor key interfaces** - uplinks, high-traffic ports
5. **Review alerts regularly** and tune thresholds

### **Performance Optimization**
1. **Monitor resource usage** of the NMS system itself
2. **Clean old data periodically** if disk space is limited
3. **Use efficient polling intervals** based on device importance
4. **Optimize SNMP queries** for faster response times
5. **Scale horizontally** for very large networks (1000+ devices)

---

## 📞 **Support & Help**

### **Getting Help**
- **Documentation:** This manual covers all features
- **API Docs:** `http://127.0.0.1:8000/docs` for technical integration
- **System Health:** Check `/health` endpoint for system status
- **Logs:** Check browser console (F12) for error messages

### **Feature Requests**
- Most common network monitoring scenarios are supported
- SNMP-based devices work best (routers, switches, servers)
- Custom OID monitoring can be added for specific devices
- Integration APIs available for external systems

### **System Information**
- **Version:** 1.0.0 (Production Ready)
- **Technology:** React + FastAPI + PostgreSQL
- **Update Frequency:** Real-time (2-second intervals)
- **Device Support:** SNMP v2c/v3, ICMP ping, HTTP checks

---

## 🎉 **Success Tips**

### **Quick Wins**
1. **Start Simple:** Add 2-3 critical devices first
2. **Use Discovery:** Let the system find devices automatically  
3. **Monitor Key Metrics:** Focus on CPU, memory, interface status
4. **Set Realistic Intervals:** 60 seconds is usually sufficient
5. **Check Dashboard Daily:** Review health scores and alerts

### **Advanced Usage**
1. **Historical Analysis:** Use time windows to spot trends
2. **Capacity Planning:** Monitor growth in CPU/memory over weeks
3. **Network Optimization:** Identify high-traffic interfaces
4. **Troubleshooting:** Use real-time data during network issues
5. **Reporting:** Export data for management reports

---

**🎯 You now have everything needed to effectively use the NMS system!** 🚀

**Remember:** Start simple, add devices gradually, and monitor what matters most to your network operations.