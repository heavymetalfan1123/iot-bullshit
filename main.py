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
    return {"allowed_devices": ["esp12_sensor_1"], "default_threshold": 100}

config = load_config()
ALLOWED_DEVICES = config.get("allowed_devices", ["esp12_sensor_1"])
DEFAULT_THRESHOLD = 100

esp_clients = {}
web_clients = set()
current_threshold = DEFAULT_THRESHOLD

HTML_PAGE = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Touch Counter</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Arial', sans-serif;
            background: #0a0a0a;
            color: #fff;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .container { text-align: center; padding: 40px; max-width: 600px; width: 100%; }
        
        .counter {
            font-size: 180px;
            font-weight: bold;
            color: #ff6600;
            text-shadow: 0 0 50px rgba(255,102,0,0.5), 0 0 100px rgba(255,102,0,0.3);
            line-height: 1;
            margin: 20px 0;
        }
        
        .label {
            font-size: 20px;
            color: #888;
            letter-spacing: 5px;
            text-transform: uppercase;
        }
        
        .distance {
            font-size: 36px;
            margin: 10px 0;
        }
        
        .distance.near { color: #ff0000; }
        .distance.far { color: #00ff00; }
        
        .controls {
            background: rgba(255,255,255,0.05);
            border-radius: 20px;
            padding: 30px;
            margin: 30px 0;
        }
        
        .slider-container {
            margin: 20px 0;
        }
        
        .slider-label {
            display: flex;
            justify-content: space-between;
            margin-bottom: 10px;
            font-size: 14px;
            color: #888;
        }
        
        input[type="range"] {
            width: 100%;
            height: 8px;
            border-radius: 5px;
            background: linear-gradient(90deg, #00ff00, #ffaa00, #ff0000);
            outline: none;
            -webkit-appearance: none;
        }
        
        input[type="range"]::-webkit-slider-thumb {
            -webkit-appearance: none;
            width: 30px;
            height: 30px;
            border-radius: 50%;
            background: white;
            cursor: pointer;
            box-shadow: 0 0 20px rgba(255,255,255,0.5);
        }
        
        .threshold-display {
            font-size: 48px;
            font-weight: bold;
            color: #ffaa00;
            margin: 10px 0;
        }
        
        .reset-btn {
            padding: 20px 60px;
            font-size: 24px;
            font-weight: bold;
            background: #ff0000;
            color: white;
            border: none;
            border-radius: 50px;
            cursor: pointer;
            letter-spacing: 3px;
            transition: 0.3s;
            box-shadow: 0 5px 20px rgba(255,0,0,0.3);
        }
        
        .reset-btn:hover {
            background: #ff3333;
            transform: translateY(-2px);
        }
        
        .reset-btn:active {
            transform: scale(0.95);
        }
        
        .info-row {
            display: flex;
            justify-content: space-around;
            margin-top: 20px;
            font-size: 14px;
            color: #666;
        }
        
        .dot {
            display: inline-block;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            margin-right: 10px;
        }
        
        .dot.online { background: #00ff00; box-shadow: 0 0 10px #00ff00; }
        .dot.offline { background: #ff0000; box-shadow: 0 0 10px #ff0000; }
        
        .preset-buttons {
            display: flex;
            gap: 10px;
            justify-content: center;
            margin: 15px 0;
        }
        
        .preset-btn {
            padding: 10px 20px;
            background: rgba(255,255,255,0.1);
            border: 1px solid rgba(255,255,255,0.2);
            color: white;
            border-radius: 20px;
            cursor: pointer;
            font-size: 14px;
            transition: 0.3s;
        }
        
        .preset-btn:hover {
            background: rgba(255,255,255,0.2);
        }
        
        .preset-btn.active {
            background: #ffaa00;
            border-color: #ffaa00;
        }
    </style>
</head>
<body>
    <div class="container">
        <div>
            <span class="dot" id="dot"></span>
            <span style="color: #888;" id="connStatus">Connecting...</span>
        </div>
        
        <div class="label">Touch Counter</div>
        <div class="counter" id="counter">0</div>
        
        <div class="distance" id="distDisplay">--- mm</div>
        
        <div class="controls">
            <div style="font-size: 18px; color: #888; margin-bottom: 15px;">DISTANCE THRESHOLD</div>
            
            <div class="threshold-display" id="thresholdValue">100 mm</div>
            
            <div class="slider-container">
                <div class="slider-label">
                    <span>10mm</span>
                    <span>500mm</span>
                </div>
                <input type="range" id="thresholdSlider" min="10" max="500" value="100" step="10">
            </div>
            
            <div class="preset-buttons">
                <button class="preset-btn active" onclick="setThreshold(100)">10cm</button>
                <button class="preset-btn" onclick="setThreshold(200)">20cm</button>
                <button class="preset-btn" onclick="setThreshold(300)">30cm</button>
                <button class="preset-btn" onclick="setThreshold(500)">50cm</button>
            </div>
        </div>
        
        <button class="reset-btn" onclick="resetCounter()">RESET COUNTER</button>
        
        <div class="info-row">
            <span>Signal: <span id="rssi">---</span></span>
            <span>Uptime: <span id="uptime">0s</span></span>
        </div>
    </div>
    
    <script>
        const wsUrl = (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws';
        let ws;
        let currentThreshold = 100;
        
        function connect() {
            ws = new WebSocket(wsUrl);
            
            ws.onopen = () => {
                document.getElementById('dot').className = 'dot online';
                document.getElementById('connStatus').textContent = 'Connected';
                ws.send(JSON.stringify({type: 'web_client'}));
            };
            
            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                
                if (data.type === 'update') {
                    updateDisplay(data.data);
                }
            };
            
            ws.onclose = () => {
                document.getElementById('dot').className = 'dot offline';
                document.getElementById('connStatus').textContent = 'Reconnecting...';
                setTimeout(connect, 3000);
            };
        }
        
        function updateDisplay(d) {
            document.getElementById('counter').textContent = d.touch_count || 0;
            
            const distEl = document.getElementById('distDisplay');
            const dist = d.distance || 0;
            const threshold = d.threshold || 100;
            
            distEl.textContent = dist.toFixed(1) + ' mm';
            distEl.className = 'distance ' + (dist <= threshold ? 'near' : 'far');
            
            document.getElementById('rssi').textContent = (d.rssi || 0) + ' dBm';
            
            const uptime = d.uptime || 0;
            const h = Math.floor(uptime / 3600);
            const m = Math.floor((uptime % 3600) / 60);
            const s = uptime % 60;
            document.getElementById('uptime').textContent = h + 'h ' + m + 'm ' + s + 's';
            
            // Обновляем слайдер если threshold поменялся
            if (threshold !== currentThreshold) {
                currentThreshold = threshold;
                document.getElementById('thresholdSlider').value = threshold;
                document.getElementById('thresholdValue').textContent = threshold + ' mm';
            }
        }
        
        // Слайдер дистанции
        document.getElementById('thresholdSlider').addEventListener('input', function(e) {
            const value = parseInt(e.target.value);
            document.getElementById('thresholdValue').textContent = value + ' mm';
        });
        
        document.getElementById('thresholdSlider').addEventListener('change', function(e) {
            const value = parseInt(e.target.value);
            sendThreshold(value);
        });
        
        function setThreshold(value) {
            document.getElementById('thresholdSlider').value = value;
            document.getElementById('thresholdValue').textContent = value + ' mm';
            sendThreshold(value);
            
            // Обновляем пресеты
            document.querySelectorAll('.preset-btn').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
        }
        
        function sendThreshold(value) {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({
                    type: 'set_threshold',
                    deviceId: 'esp12_sensor_1',
                    value: value
                }));
            }
        }
        
        function resetCounter() {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({
                    type: 'reset',
                    deviceId: 'esp12_sensor_1'
                }));
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
    
    print("🔌 New connection")
    
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    
                    # Регистрация ESP
                    if data.get("type") == "register":
                        device_id = data.get("deviceId", "")
                        
                        if device_id not in ALLOWED_DEVICES:
                            await ws.send_json({"type": "error"})
                            continue
                        
                        client_type = "esp"
                        esp_clients[device_id] = ws
                        print(f"✅ ESP: {device_id}")
                        await ws.send_json({"type": "registered"})
                        
                        # Отправляем текущий порог
                        threshold_cmd = json.dumps({
                            "type": "command",
                            "command": "set_threshold",
                            "value": current_threshold
                        })
                        await ws.send_str(threshold_cmd)
                    
                    # Данные с датчика
                    elif data.get("type") == "sensor_data":
                        device_id = data.get("deviceId", "unknown")
                        sensor = data.get("data", {})
                        
                        touches = sensor.get("touch_count", 0)
                        dist = sensor.get("distance", 0)
                        threshold = sensor.get("threshold", 100)
                        
                        # Обновляем глобальный порог
                        global current_threshold
                        current_threshold = threshold
                        
                        print(f"📊 {device_id} | Touches: {touches} | Dist: {dist:.1f}mm | Thr: {threshold}mm")
                        
                        # Рассылаем веб-клиентам
                        update_msg = json.dumps({
                            "type": "update",
                            "deviceId": device_id,
                            "data": sensor
                        })
                        
                        dead = set()
                        for client in web_clients.copy():
                            try:
                                await client.send_str(update_msg)
                            except:
                                dead.add(client)
                        web_clients.difference_update(dead)
                    
                    # Сброс счетчика
                    elif data.get("type") == "reset":
                        target = data.get("deviceId", "esp12_sensor_1")
                        print(f"🔄 RESET {target}")
                        
                        if target in esp_clients:
                            try:
                                await esp_clients[target].send_str(json.dumps({
                                    "type": "command",
                                    "command": "reset"
                                }))
                            except:
                                pass
                    
                    # Изменение порога
                    elif data.get("type") == "set_threshold":
                        target = data.get("deviceId", "esp12_sensor_1")
                        value = data.get("value", 100)
                        print(f"📏 Threshold {target} -> {value}mm")
                        
                        global current_threshold
                        current_threshold = value
                        
                        if target in esp_clients:
                            try:
                                await esp_clients[target].send_str(json.dumps({
                                    "type": "command",
                                    "command": "set_threshold",
                                    "value": value
                                }))
                            except:
                                pass
                    
                    # Веб-клиент
                    elif data.get("type") == "web_client":
                        client_type = "web"
                        web_clients.add(ws)
                        print(f"🌐 Web client (total: {len(web_clients)})")
                
                except Exception as e:
                    print(f"Error: {e}")
    
    except Exception as e:
        print(f"Connection error: {e}")
    finally:
        if client_type == "esp" and device_id:
            if device_id in esp_clients:
                del esp_clients[device_id]
        elif client_type == "web":
            web_clients.discard(ws)
    
    return ws

if __name__ == '__main__':
    app = web.Application()
    app.router.add_get('/', handle_http)
    app.router.add_get('/ws', handle_ws)
    
    port = int(os.environ.get('PORT', 8000))
    print(f"Server on port {port}")
    web.run_app(app, port=port)
