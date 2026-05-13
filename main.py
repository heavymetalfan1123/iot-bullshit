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

esp_clients = {}
web_clients = set()
current_threshold = 100  # Текущий порог

HTML_PAGE = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Touch Counter</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: Arial, sans-serif;
            background: #0a0a0a;
            color: white;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .container { text-align: center; padding: 20px; width: 100%; max-width: 600px; }
        
        .counter-box {
            background: rgba(255,0,255,0.1);
            border: 2px solid rgba(255,0,255,0.3);
            border-radius: 20px;
            padding: 40px;
            margin: 20px 0;
        }
        
        .counter {
            font-size: 180px;
            font-weight: bold;
            color: #ff00ff;
            text-shadow: 0 0 40px rgba(255,0,255,0.5);
            line-height: 1;
        }
        
        .label {
            font-size: 20px;
            color: #888;
            letter-spacing: 5px;
            margin-bottom: 10px;
        }
        
        .distance-display {
            font-size: 60px;
            font-weight: bold;
            margin: 10px 0;
            text-shadow: 0 0 20px rgba(0,255,255,0.5);
        }
        
        .threshold-display {
            font-size: 24px;
            color: #888;
            margin: 10px 0;
        }
        
        .threshold-display span {
            color: #ffaa00;
            font-weight: bold;
        }
        
        .threshold-slider {
            width: 100%;
            margin: 20px 0;
            -webkit-appearance: none;
            height: 15px;
            background: linear-gradient(90deg, #00ff00, #ffaa00, #ff0000);
            border-radius: 10px;
            outline: none;
        }
        
        .threshold-slider::-webkit-slider-thumb {
            -webkit-appearance: none;
            width: 40px;
            height: 40px;
            background: white;
            border-radius: 50%;
            cursor: pointer;
            box-shadow: 0 0 20px rgba(255,255,255,0.5);
        }
        
        .slider-labels {
            display: flex;
            justify-content: space-between;
            color: #666;
            font-size: 14px;
        }
        
        .buttons {
            display: flex;
            gap: 20px;
            justify-content: center;
            margin-top: 30px;
        }
        
        .btn {
            padding: 15px 40px;
            font-size: 20px;
            font-weight: bold;
            border: none;
            border-radius: 50px;
            cursor: pointer;
            letter-spacing: 2px;
            transition: 0.3s;
        }
        
        .btn-reset {
            background: #ff0000;
            color: white;
            box-shadow: 0 5px 20px rgba(255,0,0,0.3);
        }
        
        .btn-reset:hover {
            background: #ff3333;
            transform: translateY(-2px);
        }
        
        .btn-apply {
            background: #00aa00;
            color: white;
            box-shadow: 0 5px 20px rgba(0,255,0,0.3);
        }
        
        .btn-apply:hover {
            background: #00cc00;
            transform: translateY(-2px);
        }
        
        .status {
            margin-top: 20px;
            color: #888;
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
        
        .value-indicator {
            height: 30px;
            background: linear-gradient(90deg, #00ff00, #ffaa00, #ff0000);
            border-radius: 15px;
            margin: 10px 0;
            transition: width 0.1s;
            position: relative;
        }
        
        .marker {
            position: absolute;
            top: -5px;
            width: 4px;
            height: 40px;
            background: white;
            box-shadow: 0 0 10px white;
        }
    </style>
</head>
<body>
    <div class="container">
        <div>
            <span class="dot" id="dot"></span>
            <span style="color: #888;" id="connStatus">Connecting...</span>
        </div>
        
        <div class="counter-box">
            <div class="label">TOUCHES</div>
            <div class="counter" id="counter">0</div>
        </div>
        
        <div class="distance-display" id="distDisplay" style="color: #00ffff;">--- mm</div>
        
        <div class="value-indicator" id="valueBar" style="width: 0%;">
            <div class="marker" id="thresholdMarker" style="left: 25%;"></div>
        </div>
        
        <div class="threshold-display">
            Touch distance: <span id="thresholdValue">100</span> mm
        </div>
        
        <input type="range" class="threshold-slider" id="thresholdSlider" 
               min="30" max="400" value="100" step="10">
        
        <div class="slider-labels">
            <span>30mm</span>
            <span>400mm</span>
        </div>
        
        <div class="buttons">
            <button class="btn btn-apply" onclick="setThreshold()">APPLY</button>
            <button class="btn btn-reset" onclick="resetCounter()">RESET</button>
        </div>
        
        <div class="status" id="statusMsg"></div>
    </div>
    
    <script>
        const wsUrl = (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws';
        let ws;
        let deviceId = 'esp12_sensor_1';
        let currentThreshold = 100;
        
        // Обновление слайдера в реальном времени
        document.getElementById('thresholdSlider').addEventListener('input', function() {
            currentThreshold = parseInt(this.value);
            document.getElementById('thresholdValue').textContent = currentThreshold;
            document.getElementById('thresholdMarker').style.left = (currentThreshold / 400 * 100) + '%';
        });
        
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
                } else if (data.type === 'reset_confirm') {
                    document.getElementById('counter').textContent = '0';
                    showStatus('Counter reset!', '#00ff00');
                    setTimeout(() => showStatus('', ''), 2000);
                }
            };
            
            ws.onclose = () => {
                document.getElementById('dot').className = 'dot offline';
                document.getElementById('connStatus').textContent = 'Reconnecting...';
                setTimeout(connect, 3000);
            };
        }
        
        function updateDisplay(d) {
            const touches = d.touch_count || 0;
            const dist = d.distance || 0;
            const threshold = d.threshold || 100;
            
            // Счетчик
            document.getElementById('counter').textContent = touches;
            
            // Расстояние
            const distEl = document.getElementById('distDisplay');
            distEl.textContent = dist.toFixed(0) + ' mm';
            
            // Цвет в зависимости от близости к порогу
            if (dist <= threshold) {
                distEl.style.color = '#ff0000';
            } else if (dist <= threshold * 1.5) {
                distEl.style.color = '#ffaa00';
            } else {
                distEl.style.color = '#00ffff';
            }
            
            // Бар дистанции
            const barPercent = Math.min(dist / 400 * 100, 100);
            document.getElementById('valueBar').style.width = barPercent + '%';
            
            // Обновляем порог если пришел новый
            if (threshold !== currentThreshold) {
                currentThreshold = threshold;
                document.getElementById('thresholdSlider').value = threshold;
                document.getElementById('thresholdValue').textContent = threshold;
                document.getElementById('thresholdMarker').style.left = (threshold / 400 * 100) + '%';
            }
        }
        
        function setThreshold() {
            const newThreshold = parseInt(document.getElementById('thresholdSlider').value);
            
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({
                    type: 'set_threshold',
                    deviceId: deviceId,
                    value: newThreshold
                }));
                showStatus('Threshold set to ' + newThreshold + 'mm', '#00ff00');
                setTimeout(() => showStatus('', ''), 2000);
            }
        }
        
        function resetCounter() {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({
                    type: 'reset',
                    deviceId: deviceId
                }));
            }
        }
        
        function showStatus(msg, color) {
            const el = document.getElementById('statusMsg');
            el.textContent = msg;
            el.style.color = color;
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
                    
                    # Данные с датчика
                    elif data.get("type") == "sensor_data":
                        device_id = data.get("deviceId", "unknown")
                        sensor = data.get("data", {})
                        
                        touches = sensor.get("touch_count", 0)
                        dist = sensor.get("distance", 0)
                        threshold = sensor.get("threshold", 100)
                        
                        global current_threshold
                        current_threshold = threshold
                        
                        print(f"📊 {device_id} | Touches: {touches} | Dist: {dist:.0f}mm | Thr: {threshold}mm")
                        
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
                    
                    # Сброс счетчика
                    elif data.get("type") == "reset":
                        target = data.get("deviceId", "esp12_sensor_1")
                        print(f"🔄 Reset: {target}")
                        
                        if target in esp_clients:
                            reset_cmd = json.dumps({
                                "type": "command",
                                "command": "reset"
                            })
                            await esp_clients[target].send_str(reset_cmd)
                            print("✅ Reset sent to ESP")
                        
                        # Подтверждение веб-клиентам
                        confirm = json.dumps({"type": "reset_confirm"})
                        for client in web_clients.copy():
                            try:
                                await client.send_str(confirm)
                            except:
                                pass
                    
                    # Изменение порога
                    elif data.get("type") == "set_threshold":
                        target = data.get("deviceId", "esp12_sensor_1")
                        value = data.get("value", 100)
                        print(f"📏 Set threshold: {value}mm for {target}")
                        
                        if target in esp_clients:
                            threshold_cmd = json.dumps({
                                "type": "command",
                                "command": "set_threshold",
                                "value": value
                            })
                            await esp_clients[target].send_str(threshold_cmd)
                            print(f"✅ Threshold sent to ESP")
                    
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
    web.run_app(app, port=port)
