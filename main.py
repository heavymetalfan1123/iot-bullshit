# server_wss.py
import os
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

# Хранилище данных
devices_data = {}
web_clients = set()

HTML_PAGE = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>ESP12 Potentiometer Monitor</title>
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
            overflow: hidden;
        }
        .container { text-align: center; padding: 40px; width: 100%; max-width: 800px; }
        
        .main-value {
            font-size: 140px;
            font-weight: bold;
            color: #ffaa00;
            text-shadow: 0 0 30px rgba(255, 170, 0, 0.5), 0 0 60px rgba(255, 170, 0, 0.3);
            animation: glow 2s infinite alternate;
            transition: all 0.1s;
        }
        
        @keyframes glow {
            from { text-shadow: 0 0 30px rgba(255, 170, 0, 0.5); }
            to { text-shadow: 0 0 60px rgba(255, 170, 0, 1); }
        }
        
        .voltage {
            font-size: 48px;
            color: #00ff00;
            margin-top: 10px;
            text-shadow: 0 0 20px rgba(0, 255, 0, 0.5);
        }
        
        .bar-container {
            width: 100%;
            height: 40px;
            background: rgba(255, 170, 0, 0.1);
            border: 2px solid rgba(255, 170, 0, 0.3);
            border-radius: 20px;
            margin-top: 30px;
            overflow: hidden;
            position: relative;
        }
        
        .bar-fill {
            height: 100%;
            background: linear-gradient(90deg, #00ff00, #ffaa00, #ff0000);
            border-radius: 18px;
            transition: width 0.1s;
            box-shadow: 0 0 20px rgba(255, 170, 0, 0.5);
        }
        
        .bar-label {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            color: white;
            font-weight: bold;
            font-size: 18px;
            text-shadow: 0 0 10px rgba(0,0,0,0.8);
        }
        
        .info {
            font-size: 18px;
            color: #888;
            margin-top: 20px;
        }
        
        .status {
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 10px;
            animation: blink 1s infinite;
        }
        
        .status.connected {
            background: #00ff00;
            box-shadow: 0 0 10px #00ff00;
        }
        
        .status.disconnected {
            background: #ff0000;
            box-shadow: 0 0 10px #ff0000;
            animation: none;
        }
        
        @keyframes blink {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.3; }
        }
        
        .stats {
            margin-top: 40px;
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 30px;
            max-width: 600px;
            margin-left: auto;
            margin-right: auto;
        }
        
        .stat-box {
            background: rgba(0, 255, 0, 0.05);
            border: 1px solid rgba(0, 255, 0, 0.2);
            border-radius: 10px;
            padding: 20px;
        }
        
        .stat-label {
            font-size: 11px;
            color: #666;
            text-transform: uppercase;
            letter-spacing: 2px;
            margin-bottom: 10px;
        }
        
        .stat-value {
            font-size: 22px;
            color: #00ff00;
        }
        
        .min-max {
            display: flex;
            justify-content: space-between;
            margin-top: 10px;
            color: #666;
            font-size: 14px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div style="margin-bottom: 20px;">
            <span class="status" id="statusDot"></span>
            <span style="color: #888;" id="deviceName">Connecting...</span>
        </div>
        
        <div class="voltage" id="voltageValue">0.00V</div>
        <div class="main-value" id="potValue">0</div>
        
        <div class="bar-container">
            <div class="bar-fill" id="potBar" style="width: 0%;"></div>
            <div class="bar-label" id="barLabel">0%</div>
        </div>
        
        <div class="min-max">
            <span>0 (GND)</span>
            <span>1023 (3.3V)</span>
        </div>
        
        <div class="info" id="infoText">Waiting for data...</div>
        
        <div class="stats">
            <div class="stat-box">
                <div class="stat-label">Signal (RSSI)</div>
                <div class="stat-value" id="rssi">0 dBm</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Uptime</div>
                <div class="stat-value" id="uptime">0s</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">Percent</div>
                <div class="stat-value" id="percent">0%</div>
            </div>
        </div>
    </div>
    
    <script>
        const wsUrl = (window.location.protocol === 'https:' ? 'wss://' : 'ws://') + window.location.host + '/ws';
        let ws;
        let maxValue = 0;
        let minValue = 1023;
        
        function connect() {
            ws = new WebSocket(wsUrl);
            
            ws.onopen = () => {
                console.log('Connected');
                document.getElementById('statusDot').className = 'status connected';
                document.getElementById('deviceName').textContent = 'Online';
                ws.send(JSON.stringify({type: 'web_client'}));
            };
            
            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                if (data.type === 'update') {
                    updateDisplay(data.data);
                }
            };
            
            ws.onclose = () => {
                document.getElementById('statusDot').className = 'status disconnected';
                document.getElementById('deviceName').textContent = 'Reconnecting...';
                setTimeout(connect, 3000);
            };
        }
        
        function updateDisplay(d) {
            const pot = d.potentiometer || 0;
            const volt = d.voltage || 0;
            const rssi = d.rssi || 0;
            const uptime = d.uptime || 0;
            
            // Процент
            const percent = (pot / 1023) * 100;
            
            // Обновляем значения
            document.getElementById('potValue').textContent = pot;
            document.getElementById('voltageValue').textContent = volt.toFixed(2) + 'V';
            
            // Прогресс-бар
            document.getElementById('potBar').style.width = percent + '%';
            document.getElementById('barLabel').textContent = percent.toFixed(1) + '%';
            
            // Цвет в зависимости от значения
            const hue = (1 - percent / 100) * 120; // 120=зеленый, 0=красный
            document.getElementById('potValue').style.color = `hsl(${hue}, 100%, 50%)`;
            document.getElementById('potValue').style.textShadow = `0 0 30px hsl(${hue}, 100%, 50%)`;
            
            // Статистика
            document.getElementById('rssi').textContent = rssi + ' dBm';
            document.getElementById('percent').textContent = percent.toFixed(1) + '%';
            
            // Uptime
            const h = Math.floor(uptime / 3600);
            const m = Math.floor((uptime % 3600) / 60);
            const s = uptime % 60;
            document.getElementById('uptime').textContent = h + 'h ' + m + 'm ' + s + 's';
            
            document.getElementById('infoText').textContent = 
                'ADC: ' + pot + ' / 1023 | Voltage: ' + volt.toFixed(2) + 'V';
        }
        
        connect();
    </script>
</body>
</html>"""

async def handle_http(request):
    return web.Response(text=HTML_PAGE, content_type='text/html')

async def handle_ws(request):
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
                        
                        pot = sensor.get("potentiometer", 0)
                        volt = sensor.get("voltage", 0)
                        print(f"📊 {device_id} | Pot: {pot} | Voltage: {volt:.2f}V")
                        
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
                        
                        # Отправляем последние данные
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

if __name__ == '__main__':
    app = web.Application()
    app.router.add_get('/', handle_http)
    app.router.add_get('/ws', handle_ws)
    
    port = int(os.environ.get('PORT', 8000))
    print(f"Server on port {port}")
    print(f"Allowed devices: {ALLOWED_DEVICES}")
    web.run_app(app, port=port)
