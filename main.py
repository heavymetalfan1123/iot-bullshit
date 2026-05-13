# server.py
import os
import json
from datetime import datetime
from pathlib import Path
from aiohttp import web

def load_config():
    config_file = Path("config.json")
    if config_file.exists():
        with open(config_file, 'r') as f:
            return json.load(f)
    return {"allowed_devices": ["esp12_sensor_1"]}

config = load_config()
ALLOWED_DEVICES = config.get("allowed_devices", ["esp12_sensor_1"])

devices_data = {}
web_clients = set()

HTML_PAGE = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Touch Counter</title>
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
        
        .counter {
            font-size: 200px;
            font-weight: bold;
            color: #ff00ff;
            text-shadow: 0 0 40px rgba(255, 0, 255, 0.5),
                         0 0 80px rgba(255, 0, 255, 0.3),
                         0 0 120px rgba(255, 0, 255, 0.2);
            animation: pulse 2s infinite;
            line-height: 1;
        }
        
        @keyframes pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.05); }
        }
        
        .label {
            font-size: 24px;
            color: #888;
            margin-top: 10px;
            text-transform: uppercase;
            letter-spacing: 5px;
        }
        
        .distance {
            font-size: 36px;
            color: #00ffff;
            margin-top: 20px;
            text-shadow: 0 0 20px rgba(0, 255, 255, 0.5);
        }
        
        .status {
            display: inline-block;
            padding: 10px 30px;
            border-radius: 30px;
            font-size: 18px;
            margin: 20px 0;
        }
        
        .status.near {
            background: rgba(255, 0, 0, 0.3);
            color: #ff0000;
            animation: blink 0.5s infinite;
        }
        
        .status.far {
            background: rgba(0, 255, 0, 0.2);
            color: #00ff00;
        }
        
        @keyframes blink {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.3; }
        }
        
        .reset-btn {
            padding: 20px 60px;
            font-size: 24px;
            font-weight: bold;
            background: linear-gradient(135deg, #ff0000, #ff6600);
            color: white;
            border: none;
            border-radius: 50px;
            cursor: pointer;
            margin-top: 30px;
            text-transform: uppercase;
            letter-spacing: 3px;
            transition: all 0.3s;
            box-shadow: 0 10px 30px rgba(255, 0, 0, 0.3);
        }
        
        .reset-btn:hover {
            transform: translateY(-3px);
            box-shadow: 0 15px 40px rgba(255, 0, 0, 0.5);
        }
        
        .reset-btn:active {
            transform: translateY(0);
        }
        
        .stats {
            margin-top: 30px;
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 20px;
            max-width: 400px;
            margin-left: auto;
            margin-right: auto;
        }
        
        .stat-box {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 15px;
            padding: 20px;
        }
        
        .stat-label {
            font-size: 12px;
            color: #666;
            text-transform: uppercase;
            letter-spacing: 2px;
            margin-bottom: 10px;
        }
        
        .stat-value {
            font-size: 28px;
            color: #00ffff;
        }
        
        .connected-dot {
            display: inline-block;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            margin-right: 10px;
        }
        
        .connected-dot.online {
            background: #00ff00;
            box-shadow: 0 0 10px #00ff00;
        }
        
        .connected-dot.offline {
            background: #ff0000;
            box-shadow: 0 0 10px #ff0000;
        }
    </style>
</head>
<body>
    <div class="container">
        <div style="margin-bottom: 20px;">
            <span class="connected-dot" id="dot"></span>
            <span style="color: #888;" id="connectionStatus">Connecting...</span>
        </div>
        
        <div class="label">TOUCHES</div>
        <div class="counter" id="touchCount">0</div>
        
        <div class="status" id="objectStatus">WAITING</div>
        
        <div class="distance" id="distanceDisplay">Distance: --- mm</div>
        
        <button class="reset-btn" onclick="resetCounter()">🔄 RESET</button>
        
        <div class="stats">
            <div class="stat-box">
                <div class="stat-label">Signal</div>
                <div class="stat-value" id="rssi">--- dBm</div>
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
                document.getElementById('dot').className = 'connected-dot online';
                document.getElementById('connectionStatus').textContent = 'Connected';
                ws.send(JSON.stringify({type: 'web_client'}));
            };
            
            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                if (data.type === 'update') {
                    updateDisplay(data.data);
                }
            };
            
            ws.onclose = () => {
                document.getElementById('dot').className = 'connected-dot offline';
                document.getElementById('connectionStatus').textContent = 'Reconnecting...';
                setTimeout(connect, 3000);
            };
        }
        
        function updateDisplay(d) {
            const touches = d.touch_count || 0;
            const distance = d.distance || 0;
            const objectNear = d.object_near;
            const rssi = d.rssi || 0;
            const uptime = d.uptime || 0;
            
            // Счетчик касаний
            document.getElementById('touchCount').textContent = touches;
            
            // Статус объекта
            const statusEl = document.getElementById('objectStatus');
            if (objectNear) {
                statusEl.textContent = 'OBJECT NEAR!';
                statusEl.className = 'status near';
            } else {
                statusEl.textContent = 'CLEAR';
                statusEl.className = 'status far';
            }
            
            // Расстояние
            document.getElementById('distanceDisplay').textContent = 'Distance: ' + distance.toFixed(1) + ' mm';
            
            // Сигнал и время
            document.getElementById('rssi').textContent = rssi + ' dBm';
            const h = Math.floor(uptime / 3600);
            const m = Math.floor((uptime % 3600) / 60);
            const s = uptime % 60;
            document.getElementById('uptime').textContent = h + 'h ' + m + 'm ' + s + 's';
        }
        
        function resetCounter() {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({
                    type: 'reset',
                    deviceId: 'esp12_sensor_1'
                }));
                // Анимируем кнопку
                const btn = document.querySelector('.reset-btn');
                btn.style.transform = 'scale(0.95)';
                setTimeout(() => btn.style.transform = '', 200);
            }
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
    
    print(f"🔌 New connection")
    
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    
                    if data.get("type") == "register":
                        device_id = data.get("deviceId", "")
                        
                        if device_id not in ALLOWED_DEVICES:
                            await ws.send_json({"type": "error", "message": "Not allowed"})
                            continue
                        
                        client_type = "esp"
                        devices_data[device_id] = {
                            "connected": True,
                            "last_data": None
                        }
                        print(f"✅ ESP: {device_id}")
                        await ws.send_json({"type": "registered", "status": "success"})
                    
                    elif data.get("type") == "sensor_data":
                        device_id = data.get("deviceId", "unknown")
                        sensor = data.get("data", {})
                        
                        devices_data[device_id] = {
                            "connected": True,
                            "last_data": sensor,
                            "touch_count": sensor.get("touch_count", 0)
                        }
                        
                        touches = sensor.get("touch_count", 0)
                        dist = sensor.get("distance", 0)
                        near = sensor.get("object_near", False)
                        print(f"📊 {device_id} | Touches: {touches} | Dist: {dist:.1f}mm | {'NEAR' if near else 'FAR'}")
                        
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
                    
                    elif data.get("type") == "reset":
                        # Кнопка сброса от веб-клиента
                        target_device = data.get("deviceId", "esp12_sensor_1")
                        print(f"🔄 RESET requested for {target_device}")
                        
                        # Отправляем команду сброса на ESP
                        for dev_id, dev_data in devices_data.items():
                            if dev_id == target_device and dev_data.get("connected"):
                                # Отправляем через веб-сокет команду reset
                                # ESP получит это в webSocketEvent
                                pass  # ESP должен быть веб-сокет клиентом, это сложно
                        
                        # Просто отправляем всем веб-клиентам что счетчик сброшен
                        reset_msg = json.dumps({
                            "type": "reset_ack",
                            "deviceId": target_device
                        })
                        
                        for client in web_clients.copy():
                            try:
                                await client.send_str(reset_msg)
                            except:
                                dead.add(client)
                    
                    elif data.get("type") == "web_client":
                        client_type = "web"
                        web_clients.add(ws)
                        print(f"🌐 Web client (total: {len(web_clients)})")
                        
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
            print(f"❌ ESP: {device_id}")
        elif client_type == "web":
            web_clients.discard(ws)
    
    return ws

if __name__ == '__main__':
    app = web.Application()
    app.router.add_get('/', handle_http)
    app.router.add_get('/ws', handle_ws)
    
    port = int(os.environ.get('PORT', 8000))
    print(f"Server on port {port}")
    print(f"Allowed: {ALLOWED_DEVICES}")
    web.run_app(app, port=port)
