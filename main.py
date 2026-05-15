# server.py
import os
import json
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

HTML_PAGE = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Exercise Counter</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Arial', sans-serif;
            background: #0a0a0f;
            color: #fff;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .container { text-align: center; padding: 40px; max-width: 600px; width: 100%; }
        
        .title {
            font-size: 16px;
            color: #666;
            letter-spacing: 4px;
            text-transform: uppercase;
            margin-bottom: 10px;
        }
        
        .counter {
            font-size: 160px;
            font-weight: bold;
            color: #ff6600;
            text-shadow: 0 0 50px rgba(255,102,0,0.5), 0 0 100px rgba(255,102,0,0.3);
            line-height: 1;
            margin: 20px 0;
            transition: color 0.3s, text-shadow 0.3s;
        }
        
        .counter.reset-flash {
            color: #00ff00 !important;
            text-shadow: 0 0 80px rgba(0,255,0,0.8) !important;
        }
        
        .exercise-name {
            font-size: 24px;
            color: #888;
            margin-bottom: 10px;
            letter-spacing: 3px;
        }
        
        .distance {
            font-size: 28px;
            margin: 10px 0;
            color: #888;
        }
        
        .distance span {
            color: #00ffff;
            font-weight: bold;
        }
        
        .exercise-buttons {
            display: flex;
            flex-direction: column;
            gap: 15px;
            margin: 30px 0;
        }
        
        .exercise-btn {
            padding: 20px;
            font-size: 18px;
            font-weight: bold;
            background: rgba(255,255,255,0.05);
            border: 2px solid rgba(255,255,255,0.1);
            color: #aaa;
            border-radius: 15px;
            cursor: pointer;
            transition: all 0.3s;
            text-align: left;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .exercise-btn:hover {
            background: rgba(255,255,255,0.1);
            border-color: rgba(255,255,255,0.3);
        }
        
        .exercise-btn.active {
            background: rgba(255,102,0,0.2);
            border-color: #ff6600;
            color: #ff6600;
            box-shadow: 0 0 20px rgba(255,102,0,0.2);
        }
        
        .exercise-btn .btn-name {
            font-size: 20px;
        }
        
        .exercise-btn .btn-distance {
            font-size: 14px;
            color: #666;
            background: rgba(255,255,255,0.1);
            padding: 5px 15px;
            border-radius: 20px;
        }
        
        .exercise-btn.active .btn-distance {
            background: rgba(255,102,0,0.3);
            color: #ffaa00;
        }
        
        .controls {
            background: rgba(255,255,255,0.03);
            border-radius: 20px;
            padding: 25px;
            margin: 20px 0;
        }
        
        .slider-container { margin: 15px 0; }
        
        .slider-label {
            display: flex;
            justify-content: space-between;
            margin-bottom: 10px;
            font-size: 13px;
            color: #666;
        }
        
        input[type="range"] {
            width: 100%;
            height: 6px;
            border-radius: 3px;
            background: linear-gradient(90deg, #00ff00, #ffaa00, #ff0000);
            outline: none;
            -webkit-appearance: none;
        }
        
        input[type="range"]::-webkit-slider-thumb {
            -webkit-appearance: none;
            width: 28px;
            height: 28px;
            border-radius: 50%;
            background: #fff;
            cursor: pointer;
            box-shadow: 0 0 15px rgba(255,255,255,0.3);
        }
        
        .threshold-display {
            font-size: 32px;
            font-weight: bold;
            color: #ffaa00;
            margin: 10px 0;
        }
        
        .reset-btn {
            width: 100%;
            padding: 18px;
            font-size: 18px;
            font-weight: bold;
            background: rgba(255,0,0,0.2);
            border: 2px solid rgba(255,0,0,0.3);
            color: #ff4444;
            border-radius: 15px;
            cursor: pointer;
            letter-spacing: 3px;
            transition: all 0.3s;
            margin-top: 15px;
        }
        
        .reset-btn:hover {
            background: rgba(255,0,0,0.3);
            border-color: #ff0000;
            color: #ff0000;
        }
        
        .reset-btn:active {
            transform: scale(0.97);
        }
        
        .status-bar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            font-size: 13px;
            color: #666;
        }
        
        .dot {
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            margin-right: 8px;
        }
        
        .dot.online { background: #00ff00; box-shadow: 0 0 8px #00ff00; }
        .dot.offline { background: #ff0000; box-shadow: 0 0 8px #ff0000; }
        
        .info-row {
            display: flex;
            justify-content: space-between;
            margin-top: 20px;
            font-size: 12px;
            color: #555;
        }
        
        .info-row span {
            color: #888;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="status-bar">
            <span><span class="dot" id="dot"></span><span id="connStatus">Connecting...</span></span>
            <span id="espStatus">---</span>
        </div>
        
        <div class="exercise-name" id="exerciseName">STANDARD MODE</div>
        <div class="counter" id="counter">0</div>
        
        <div class="distance">
            Distance: <span id="distDisplay">--- mm</span>
        </div>
        
        <div class="exercise-buttons">
            <button class="exercise-btn active" id="btnPushup" onclick="setExercise('pushup')">
                <span class="btn-name">💪 Отжимания</span>
                <span class="btn-distance">15 см</span>
            </button>
            <button class="exercise-btn" id="btnSquat" onclick="setExercise('squat')">
                <span class="btn-name">🦵 Приседания</span>
                <span class="btn-distance">40 см</span>
            </button>
            <button class="exercise-btn" id="btnCustom" onclick="setExercise('custom')">
                <span class="btn-name">🎯 Стандартное</span>
                <span class="btn-distance">100 см</span>
            </button>
        </div>
        
        <div class="controls">
            <div style="font-size: 14px; color: #666; letter-spacing: 2px; margin-bottom: 10px;">CUSTOM DISTANCE</div>
            <div class="threshold-display" id="thresholdValue">100 mm</div>
            <div class="slider-container">
                <div class="slider-label">
                    <span>10mm</span>
                    <span>500mm</span>
                </div>
                <input type="range" id="thresholdSlider" min="10" max="500" value="100" step="5">
            </div>
        </div>
        
        <button class="reset-btn" onclick="resetCounter()">🔄 RESET COUNTER</button>
        
        <div class="info-row">
            <span>Signal: <span id="rssi">---</span></span>
            <span>Uptime: <span id="uptime">0s</span></span>
        </div>
    </div>
    
    <script>
        const wsUrl = (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws';
        let ws;
        let ignoreNextUpdate = false;
        let currentExercise = 'pushup';
        
        // Настройки упражнений
        const exercises = {
            pushup: { name: 'ОТЖИМАНИЯ', distance: 150, emoji: '💪' },
            squat: { name: 'ПРИСЕДАНИЯ', distance: 400, emoji: '🦵' },
            custom: { name: 'СТАНДАРТНОЕ', distance: 100, emoji: '🎯' }
        };
        
        function connect() {
            ws = new WebSocket(wsUrl);
            
            ws.onopen = () => {
                document.getElementById('dot').className = 'dot online';
                document.getElementById('connStatus').textContent = 'Connected';
                ws.send(JSON.stringify({type: 'web_client'}));
            };
            
            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                console.log('Received:', data);
                
                if (data.type === 'update') {
                    updateDisplay(data.data);
                } else if (data.type === 'reset_confirm') {
                    const counter = document.getElementById('counter');
                    counter.textContent = '0';
                    counter.classList.add('reset-flash');
                    setTimeout(() => counter.classList.remove('reset-flash'), 500);
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
            
            const dist = d.distance || 0;
            const threshold = d.threshold || 100;
            
            document.getElementById('distDisplay').textContent = dist.toFixed(1) + ' mm';
            
            // Проверяем близость
            const isNear = dist > 0 && dist <= threshold;
            document.getElementById('espStatus').textContent = isNear ? '🔴 DETECTED' : '🟢 WAITING';
            document.getElementById('espStatus').style.color = isNear ? '#ff0000' : '#00ff00';
            
            document.getElementById('rssi').textContent = (d.rssi || 0) + ' dBm';
            
            const uptime = d.uptime || 0;
            const h = Math.floor(uptime / 3600);
            const m = Math.floor((uptime % 3600) / 60);
            const s = uptime % 60;
            document.getElementById('uptime').textContent = h + 'h ' + m + 'm ' + s + 's';
            
            // Обновляем слайдер
            if (!ignoreNextUpdate && threshold !== parseInt(document.getElementById('thresholdSlider').value)) {
                document.getElementById('thresholdSlider').value = threshold;
                document.getElementById('thresholdValue').textContent = threshold + ' mm';
                
                // Определяем какое упражнение выбрано
                if (threshold === 150) {
                    currentExercise = 'pushup';
                } else if (threshold === 400) {
                    currentExercise = 'squat';
                } else if (threshold === 100) {
                    currentExercise = 'custom';
                }
                updateActiveButton();
            }
        }
        
        function setExercise(type) {
            const exercise = exercises[type];
            currentExercise = type;
            
            document.getElementById('exerciseName').textContent = exercise.name;
            document.getElementById('thresholdSlider').value = exercise.distance;
            document.getElementById('thresholdValue').textContent = exercise.distance + ' mm';
            
            updateActiveButton();
            
            // Отправляем новый порог
            ignoreNextUpdate = true;
            sendThreshold(exercise.distance);
            setTimeout(() => { ignoreNextUpdate = false; }, 2000);
        }
        
        function updateActiveButton() {
            document.querySelectorAll('.exercise-btn').forEach(btn => {
                btn.classList.remove('active');
            });
            
            const activeBtn = document.getElementById('btn' + currentExercise.charAt(0).toUpperCase() + currentExercise.slice(1));
            if (activeBtn) {
                activeBtn.classList.add('active');
            }
        }
        
        // Слайдер
        document.getElementById('thresholdSlider').addEventListener('input', function(e) {
            const value = parseInt(e.target.value);
            document.getElementById('thresholdValue').textContent = value + ' mm';
        });
        
        document.getElementById('thresholdSlider').addEventListener('change', function(e) {
            const value = parseInt(e.target.value);
            currentExercise = 'custom';
            document.getElementById('exerciseName').textContent = exercises.custom.name;
            updateActiveButton();
            ignoreNextUpdate = true;
            sendThreshold(value);
            setTimeout(() => { ignoreNextUpdate = false; }, 2000);
        });
        
        function sendThreshold(value) {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({
                    type: 'set_threshold',
                    deviceId: 'esp12_sensor_1',
                    value: value
                }));
                console.log('Threshold sent: ' + value + 'mm');
            }
        }
        
        function resetCounter() {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({
                    type: 'reset',
                    deviceId: 'esp12_sensor_1'
                }));
                console.log('RESET sent');
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
    
    print("🔌 New WebSocket connection")
    
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    print(f"📨 Received: {data.get('type', 'unknown')}")
                    
                    # ESP регистрация
                    if data.get("type") == "register":
                        device_id = data.get("deviceId", "")
                        
                        if device_id not in ALLOWED_DEVICES:
                            await ws.send_json({"type": "error"})
                            continue
                        
                        client_type = "esp"
                        esp_clients[device_id] = ws
                        print(f"✅ ESP connected: {device_id}")
                        await ws.send_json({"type": "registered"})
                    
                    # Данные с датчика
                    elif data.get("type") == "sensor_data":
                        sensor = data.get("data", {})
                        
                        update_msg = json.dumps({
                            "type": "update",
                            "data": sensor
                        })
                        
                        dead = set()
                        for client in web_clients.copy():
                            try:
                                await client.send_str(update_msg)
                            except:
                                dead.add(client)
                        web_clients.difference_update(dead)
                    
                    # Сброс от веб-клиента
                    elif data.get("type") == "reset":
                        target = data.get("deviceId", "esp12_sensor_1")
                        print(f"🔄 RESET command for {target}")
                        
                        if target in esp_clients:
                            try:
                                reset_cmd = json.dumps({
                                    "type": "command",
                                    "command": "reset"
                                })
                                await esp_clients[target].send_str(reset_cmd)
                                print(f"✅ Reset sent to {target}")
                            except Exception as e:
                                print(f"❌ Error: {e}")
                    
                    # Изменение порога
                    elif data.get("type") == "set_threshold":
                        target = data.get("deviceId", "esp12_sensor_1")
                        value = int(data.get("value", 100))
                        print(f"📏 Threshold {value}mm for {target}")
                        
                        if target in esp_clients:
                            try:
                                threshold_cmd = json.dumps({
                                    "type": "command",
                                    "command": "set_threshold",
                                    "value": value
                                })
                                await esp_clients[target].send_str(threshold_cmd)
                                print(f"✅ Threshold sent: {value}mm")
                            except Exception as e:
                                print(f"❌ Error: {e}")
                    
                    # Подтверждение сброса от ESP
                    elif data.get("type") == "reset_confirm":
                        print(f"✅ ESP confirmed reset!")
                        confirm = json.dumps({"type": "reset_confirm"})
                        for client in web_clients.copy():
                            try:
                                await client.send_str(confirm)
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
            print(f"❌ ESP disconnected: {device_id}")
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
