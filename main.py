# server_wss.py
import os
import ssl
import json
from datetime import datetime
from pathlib import Path
from aiohttp import web

# Конфиг
def load_config():
    config_file = Path("config.json")
    if config_file.exists():
        with open(config_file, 'r') as f:
            return json.load(f)
    return {"allowed_devices": ["esp12_sensor_1", "esp12_test"]}

config = load_config()
ALLOWED_DEVICES = config.get("allowed_devices", ["esp12_sensor_1"])

# Хранилище
devices_data = {}
web_clients = set()

HTML_PAGE = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>ESP12 Monitor</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Courier New', monospace;
            background: #0a0a0a;
            color: #00ff00;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .container { text-align: center; padding: 40px; }
        .main-value {
            font-size: 120px;
            font-weight: bold;
            color: #00ff00;
            text-shadow: 0 0 20px rgba(0,255,0,0.5), 0 0 40px rgba(0,255,0,0.3);
            animation: glow 2s infinite alternate;
        }
        .main-value.high {
            color: #ff0000;
            text-shadow: 0 0 20px rgba(255,0,0,0.5);
        }
        @keyframes glow {
            from { text-shadow: 0 0 20px rgba(0,255,0,0.5); }
            to { text-shadow: 0 0 40px rgba(0,255,0,1); }
        }
        .info { font-size: 20px; color: #888; margin-top: 20px; }
        .status { display: inline-block; width: 12px; height: 12px; border-radius: 50%; margin-right: 10px; }
        .status.connected { background: #00ff00; box-shadow: 0 0 10px #00ff00; }
        .status.disconnected { background: #ff0000; }
        .stats { margin-top: 40px; display: grid; grid-template-columns: repeat(3, 1fr); gap: 30px; max-width: 600px; margin-left: auto; margin-right: auto; }
        .stat-box { background: rgba(0,255,0,0.05); border: 1px solid rgba(0,255,0,0.2); border-radius: 10px; padding: 20px; }
        .stat-label { font-size: 12px; color: #666; text-transform: uppercase; margin-bottom: 10px; }
        .stat-value { font-size: 24px; color: #00ff00; }
    </style>
</head>
<body>
    <div class="container">
        <div>
            <span class="status" id="statusDot"></span>
            <span style="color: #888;" id="deviceName">Connecting...</span>
        </div>
        <div class="main-value" id="mainValue">---</div>
        <div class="info" id="infoText">Waiting for data...</div>
        <div class="stats">
            <div class="stat-box">
                <div class="stat-label">Frequency</div>
                <div class="stat-value" id="frequency">0 Hz</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Signal</div>
                <div class="stat-value" id="rssi">0 dBm</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Uptime</div>
                <div class="stat-value" id="uptime">0s</div>
            </div>
        </div>
    </div>
    <script>
        const wsUrl = (window.location.protocol === 'https:' ? 'wss://' : 'ws://') + window.location.host + '/ws';
        let ws;
        
        function connect() {
            ws = new WebSocket(wsUrl);
            
            ws.onopen = () => {
                document.getElementById('statusDot').className = 'status connected';
                document.getElementById('deviceName').textContent = 'Connected';
                ws.send(JSON.stringify({type: 'web_client'}));
            };
            
            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                if (data.type === 'update') {
                    const d = data.data;
                    const el = document.getElementById('mainValue');
                    if (d.pin_state) {
                        el.textContent = 'HIGH';
                        el.className = 'main-value high';
                    } else {
                        el.textContent = 'LOW';
                        el.className = 'main-value';
                    }
                    document.getElementById('infoText').textContent = 'Pin D0: ' + (d.pin_state ? '3.3V' : '0V');
                    document.getElementById('frequency').textContent = (d.frequency||0).toFixed(1) + ' Hz';
                    document.getElementById('rssi').textContent = (d.rssi||0) + ' dBm';
                    const u = d.uptime||0;
                    document.getElementById('uptime').textContent = Math.floor(u/3600)+'h '+Math.floor((u%3600)/60)+'m '+u%60+'s';
                }
            };
            
            ws.onclose = () => {
                document.getElementById('statusDot').className = 'status disconnected';
                document.getElementById('deviceName').textContent = 'Reconnecting...';
                setTimeout(connect, 3000);
            };
        }
        connect();
    </script>
</body>
</html>"""

async def handle_http(request):
    """Отдаем HTML страницу"""
    return web.Response(text=HTML_PAGE, content_type='text/html')

async def handle_ws(request):
    """WebSocket обработчик"""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    client_type = None
    device_id = None
    
    print(f"🔌 New WebSocket connection")
    
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    
                    if data.get("type") == "register":
                        device_id = data.get("deviceId", "")
                        
                        if device_id not in ALLOWED_DEVICES:
                            print(f"❌ Device DENIED: {device_id}")
                            await ws.send_json({"type": "error", "message": "Device not allowed"})
                            continue
                        
                        client_type = "esp"
                        devices_data[device_id] = {
                            "connected": True,
                            "last_data": None,
                            "last_update": None
                        }
                        print(f"✅ ESP Connected: {device_id}")
                        await ws.send_json({"type": "registered", "status": "success"})
                    
                    elif data.get("type") == "sensor_data":
                        device_id = data.get("deviceId", "unknown")
                        sensor = data.get("data", {})
                        
                        devices_data[device_id] = {
                            "connected": True,
                            "last_data": sensor,
                            "last_update": datetime.now().isoformat()
                        }
                        
                        pin = "HIGH" if sensor.get("pin_state") else "LOW"
                        freq = sensor.get("frequency", 0)
                        rssi = sensor.get("rssi", 0)
                        print(f"📡 {device_id} | Pin: {pin} | Freq: {freq:.1f}Hz | RSSI: {rssi}dBm")
                        
                        # Рассылаем веб-клиентам
                        msg_data = json.dumps({
                            "type": "update",
                            "deviceId": device_id,
                            "data": sensor
                        })
                        
                        dead = set()
                        for client in web_clients.copy():
                            try:
                                await client.send_str(msg_data)
                            except:
                                dead.add(client)
                        web_clients.difference_update(dead)
                    
                    elif data.get("type") == "web_client":
                        client_type = "web"
                        web_clients.add(ws)
                        print(f"🌐 Web client (total: {len(web_clients)})")
                        
                        # Отправляем текущие данные
                        for dev_id, dev_data in devices_data.items():
                            if dev_data.get("last_data"):
                                await ws.send_json({
                                    "type": "update",
                                    "deviceId": dev_id,
                                    "data": dev_data["last_data"]
                                })
                
                except json.JSONDecodeError as e:
                    print(f"JSON error: {e}")
                except Exception as e:
                    print(f"Error: {e}")
            
            elif msg.type == web.WSMsgType.ERROR:
                print(f"WS error: {ws.exception()}")
    
    except Exception as e:
        print(f"Connection error: {e}")
    finally:
        if client_type == "esp" and device_id:
            if device_id in devices_data:
                devices_data[device_id]["connected"] = False
            print(f"❌ ESP Disconnected: {device_id}")
        elif client_type == "web":
            web_clients.discard(ws)
            print(f"🌐 Web client left (total: {len(web_clients)})")
    
    return ws

# Запуск
if __name__ == '__main__':
    app = web.Application()
    app.router.add_get('/', handle_http)
    app.router.add_get('/ws', handle_ws)
    
    port = int(os.environ.get('PORT', 8000))
    print(f"Server starting on port {port}")
    print(f"Allowed devices: {ALLOWED_DEVICES}")
    web.run_app(app, port=port)
