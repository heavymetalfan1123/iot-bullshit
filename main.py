# server_security.py
import os
import json
from pathlib import Path
from aiohttp import web

def load_config():
    config_file = Path("config.json")
    if config_file.exists():
        with open(config_file, 'r') as f:
            return json.load(f)
    return {"allowed_devices": ["esp12_security"]}

config = load_config()
ALLOWED_DEVICES = config.get("allowed_devices", ["esp12_security"])

esp_clients = {}
web_clients = set()

HTML_PAGE = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Security System</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Arial', sans-serif; background: #0a0a0f; color: #fff; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
        .container { text-align: center; padding: 40px; max-width: 500px; width: 100%; }
        .status-circle { width: 180px; height: 180px; border-radius: 50%; margin: 0 auto 20px; display: flex; align-items: center; justify-content: center; font-size: 18px; font-weight: bold; letter-spacing: 2px; transition: all 0.5s; border: 4px solid; }
        .status-circle.disarmed { background: rgba(0,255,0,0.1); border-color: #00ff00; color: #00ff00; box-shadow: 0 0 40px rgba(0,255,0,0.2); }
        .status-circle.armed { background: rgba(255,165,0,0.1); border-color: #ffaa00; color: #ffaa00; box-shadow: 0 0 40px rgba(255,165,0,0.3); }
        .status-circle.alarm { background: rgba(255,0,0,0.2); border-color: #ff0000; color: #ff0000; box-shadow: 0 0 60px rgba(255,0,0,0.5); animation: pulse 0.5s infinite; }
        @keyframes pulse { 0%,100% { transform: scale(1); } 50% { transform: scale(1.05); } }
        .alarm-count { font-size: 40px; font-weight: bold; color: #ff4444; margin: 15px 0; }
        .distance-display { font-size: 22px; color: #888; margin: 10px 0; }
        .distance-display span { color: #00ffff; }
        .arm-btn { width: 100%; padding: 22px; font-size: 20px; font-weight: bold; border: 3px solid; border-radius: 15px; cursor: pointer; transition: all 0.3s; letter-spacing: 3px; margin-bottom: 20px; }
        .arm-btn.arm { background: rgba(255,165,0,0.2); border-color: #ffaa00; color: #ffaa00; }
        .arm-btn.arm:hover { background: rgba(255,165,0,0.3); }
        .arm-btn.disarm { background: rgba(0,255,0,0.2); border-color: #00ff00; color: #00ff00; }
        .arm-btn.disarm:hover { background: rgba(0,255,0,0.3); }
        .section-title { font-size: 13px; color: #666; letter-spacing: 3px; margin-bottom: 15px; }
        .distance-buttons { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 15px; }
        .dist-btn { padding: 15px 10px; font-size: 14px; font-weight: bold; background: rgba(255,255,255,0.05); border: 2px solid rgba(255,255,255,0.1); color: #aaa; border-radius: 12px; cursor: pointer; transition: all 0.3s; }
        .dist-btn:hover { background: rgba(255,255,255,0.1); }
        .dist-btn.active { background: rgba(255,102,0,0.2); border-color: #ff6600; color: #ff6600; }
        .dist-value { font-size: 28px; font-weight: bold; color: #ffaa00; margin: 10px 0; }
        .info-row { display: flex; justify-content: space-around; margin-top: 20px; font-size: 12px; color: #555; }
        .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }
        .dot.online { background: #00ff00; }
        .dot.offline { background: #ff0000; }
    </style>
</head>
<body>
    <div class="container">
        <div><span class="dot" id="dot"></span><span style="color:#888;font-size:12px;" id="connStatus">Connecting...</span></div>
        <div class="status-circle disarmed" id="statusCircle">DISARMED</div>
        <div class="alarm-count" id="alarmCount" style="display:none;">🚨 ALARMS: 0</div>
        <div class="distance-display">Distance: <span id="distDisplay">--- cm</span></div>
        <button class="arm-btn arm" id="armBtn" onclick="toggleArm()">🔒 ARM SYSTEM</button>
        <div class="section-title">DETECTION RANGE</div>
        <div class="dist-value" id="thresholdDisplay">200 cm</div>
        <div class="distance-buttons">
            <button class="dist-btn" onclick="setDistance(100)">1m</button>
            <button class="dist-btn" onclick="setDistance(150)">1.5m</button>
            <button class="dist-btn active" onclick="setDistance(200)">2m</button>
            <button class="dist-btn" onclick="setDistance(300)">3m</button>
            <button class="dist-btn" onclick="setDistance(400)">4m</button>
            <button class="dist-btn" onclick="setDistance(500)">5m</button>
        </div>
        <div class="info-row"><span>Signal: <span id="rssi">---</span></span><span>Uptime: <span id="uptime">0s</span></span></div>
    </div>
    <script>
        const wsUrl = (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws';
        let ws, isArmed = false, hasAlarm = false, currentThreshold = 200;
        function connect() {
            ws = new WebSocket(wsUrl);
            ws.onopen = () => {
                document.getElementById('dot').className = 'dot online';
                document.getElementById('connStatus').textContent = 'Connected';
                ws.send(JSON.stringify({type:'web_client'}));
            };
            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                if (data.type === 'update') updateDisplay(data.data);
                else if (data.type === 'alarm_notification') showNotification(data.message);
            };
            ws.onclose = () => { document.getElementById('dot').className='dot offline'; document.getElementById('connStatus').textContent='Reconnecting...'; setTimeout(connect,3000); };
        }
        function updateDisplay(d) {
            const dist=d.distance||0, threshold=d.threshold||200, securityMode=d.security_mode, alarm=d.alarm, alarmCnt=d.alarm_count||0;
            document.getElementById('distDisplay').textContent=dist.toFixed(1)+' cm';
            const circle=document.getElementById('statusCircle'), armBtn=document.getElementById('armBtn');
            if(alarm){circle.className='status-circle alarm';circle.textContent='🚨 ALARM!';document.getElementById('alarmCount').style.display='block';document.getElementById('alarmCount').textContent='🚨 ALARMS: '+alarmCnt;if(!hasAlarm){showNotification('INTRUDER DETECTED!');hasAlarm=true;}}
            else if(securityMode){circle.className='status-circle armed';circle.textContent='ARMED';hasAlarm=false;}
            else{circle.className='status-circle disarmed';circle.textContent='DISARMED';document.getElementById('alarmCount').style.display='none';hasAlarm=false;}
            if(securityMode){armBtn.textContent='🔓 DISARM';armBtn.className='arm-btn disarm';isArmed=true;}
            else{armBtn.textContent='🔒 ARM SYSTEM';armBtn.className='arm-btn arm';isArmed=false;}
            if(threshold!==currentThreshold){currentThreshold=threshold;document.getElementById('thresholdDisplay').textContent=threshold+' cm';updateDistButtons(threshold);}
            document.getElementById('rssi').textContent=(d.rssi||0)+' dBm';
            const uptime=d.uptime||0; document.getElementById('uptime').textContent=Math.floor(uptime/3600)+'h '+Math.floor((uptime%3600)/60)+'m '+uptime%60+'s';
        }
        function updateDistButtons(v){document.querySelectorAll('.dist-btn').forEach(b=>{b.classList.remove('active');const t=b.textContent;if((t==='1m'&&v===100)||(t==='1.5m'&&v===150)||(t==='2m'&&v===200)||(t==='3m'&&v===300)||(t==='4m'&&v===400)||(t==='5m'&&v===500))b.classList.add('active');});}
        function setDistance(v){currentThreshold=v;document.getElementById('thresholdDisplay').textContent=v+' cm';updateDistButtons(v);if(ws&&ws.readyState===WebSocket.OPEN)ws.send(JSON.stringify({type:'set_threshold',deviceId:'esp12_security',value:v}));}
        function toggleArm(){if(ws&&ws.readyState===WebSocket.OPEN){if(isArmed)ws.send(JSON.stringify({type:'disarm',deviceId:'esp12_security'}));else ws.send(JSON.stringify({type:'arm',deviceId:'esp12_security'}));}}
        function showNotification(m){if(Notification.permission==='granted')new Notification('Security',{body:m});else if(Notification.permission!=='denied')Notification.requestPermission().then(p=>{if(p==='granted')new Notification('Security',{body:m});});}
        if(Notification.permission==='default')Notification.requestPermission();
        connect();
    </script>
</body>
</html>"""

async def handle_http(request):
    return web.Response(text=HTML_PAGE, content_type='text/html')

async def handle_ws(request):
    ws = web.WebSocketResponse(protocols=['arduino', ''])  # ПОДДЕРЖКА ПРОТОКОЛОВ
    await ws.prepare(request)
    
    client_type = None
    device_id = None
    last_alarm = False
    
    print("🔌 New WebSocket connection")
    
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    msg_type = data.get("type", "")
                    
                    # ESP registration
                    if msg_type == "register":
                        device_id = data.get("deviceId", "")
                        if device_id in ALLOWED_DEVICES:
                            client_type = "esp"
                            esp_clients[device_id] = ws
                            print(f"✅ ESP connected: {device_id}")
                            await ws.send_json({"type": "registered"})
                    
                    # Sensor data
                    elif msg_type == "sensor_data":
                        sensor = data.get("data", {})
                        
                        if sensor.get("alarm") and not last_alarm:
                            print(f"🚨 ALARM! Distance: {sensor.get('distance')}cm")
                            notif = json.dumps({"type": "alarm_notification", "message": "INTRUDER DETECTED!"})
                            for client in web_clients.copy():
                                try: await client.send_str(notif)
                                except: pass
                        last_alarm = sensor.get("alarm", False)
                        
                        update_msg = json.dumps({"type": "update", "data": sensor})
                        dead = set()
                        for client in web_clients.copy():
                            try: await client.send_str(update_msg)
                            except: dead.add(client)
                        web_clients.difference_update(dead)
                    
                    # ARM command
                    elif msg_type == "arm":
                        target = data.get("deviceId", "esp12_security")
                        print(f"🔒 ARM command for {target}")
                        
                        if target in esp_clients:
                            cmd = json.dumps({"type": "command", "command": "arm"})
                            await esp_clients[target].send_str(cmd)
                            print(f"✅ ARM sent to {target}")
                        else:
                            print(f"❌ {target} not connected! Connected devices: {list(esp_clients.keys())}")
                    
                    # DISARM command
                    elif msg_type == "disarm":
                        target = data.get("deviceId", "esp12_security")
                        print(f"🔓 DISARM command for {target}")
                        
                        if target in esp_clients:
                            cmd = json.dumps({"type": "command", "command": "disarm"})
                            await esp_clients[target].send_str(cmd)
                            print(f"✅ DISARM sent to {target}")
                        else:
                            print(f"❌ {target} not connected! Connected devices: {list(esp_clients.keys())}")
                    
                    # Set threshold
                    elif msg_type == "set_threshold":
                        target = data.get("deviceId", "esp12_security")
                        value = int(data.get("value", 200))
                        print(f"📏 Set threshold {value}cm for {target}")
                        
                        if target in esp_clients:
                            cmd = json.dumps({"type": "command", "command": "set_threshold", "value": value})
                            await esp_clients[target].send_str(cmd)
                            print(f"✅ Threshold sent: {value}cm")
                        else:
                            print(f"❌ {target} not connected! Connected devices: {list(esp_clients.keys())}")
                    
                    # Web client
                    elif msg_type == "web_client":
                        client_type = "web"
                        web_clients.add(ws)
                        print(f"🌐 Web client connected")
                
                except Exception as e:
                    print(f"Error processing message: {e}")
    
    except Exception as e:
        print(f"Connection error: {e}")
    finally:
        if client_type == "esp" and device_id:
            if device_id in esp_clients:
                del esp_clients[device_id]
            print(f"❌ ESP disconnected: {device_id}")
        elif client_type == "web":
            web_clients.discard(ws)
    
    return ws

if __name__ == '__main__':
    app = web.Application()
    app.router.add_get('/', handle_http)
    app.router.add_get('/ws', handle_ws)
    
    port = int(os.environ.get('PORT', 8000))
    print(f"Security Server on port {port}")
    print(f"Allowed devices: {ALLOWED_DEVICES}")
    web.run_app(app, port=port)
