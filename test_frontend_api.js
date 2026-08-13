// Test frontend API calls
async function testDevices() {
    const devices = [333, 334];
    
    console.log('Testing Frontend API Calls:\n');
    
    for (const deviceId of devices) {
        try {
            const response = await fetch('http://127.0.0.1:8000/api/v1/monitoring/data', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    device_id: deviceId,
                    modules: ['cpu', 'memory', 'storage', 'interfaces', 'vlan', 'lldp'],
                    include_history: false
                })
            });
            
            if (response.ok) {
                const data = await response.json();
                console.log(`✅ Device ${deviceId} (${data.hostname}):`);
                console.log(`   IP: ${data.ip_address}`);
                console.log(`   Status: ${data.status}`);
                console.log(`   Capabilities: ${Object.values(data.capabilities).filter(Boolean).length}/${Object.keys(data.capabilities).length}`);
                
                // Show supported modules with data
                Object.entries(data.modules || {}).forEach(([module, info]) => {
                    if (info.supported) {
                        const hasData = info.data !== null;
                        console.log(`   ${module}: ${hasData ? '✅ Data' : '⚠️ No Data'}`);
                        
                        if (hasData && module === 'cpu' && info.data.utilization_percent) {
                            console.log(`     CPU: ${info.data.utilization_percent}%`);
                        }
                        if (hasData && module === 'memory' && info.data.utilization_percent) {
                            console.log(`     Memory: ${info.data.utilization_percent}%`);
                        }
                    }
                });
                
                console.log(`   Monitoring: ${Object.values(data.monitoring_configs || {}).filter(c => c.enabled && c.status === 'running').length} active`);
                console.log('');
                
            } else {
                console.log(`❌ Device ${deviceId}: HTTP ${response.status}`);
            }
        } catch (error) {
            console.log(`❌ Device ${deviceId}: ${error.message}`);
        }
    }
}

// Run if Node.js
if (typeof require !== 'undefined') {
    const fetch = require('node-fetch');
    testDevices();
}