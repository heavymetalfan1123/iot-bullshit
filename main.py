import os, json
from aiohttp import web

ALLOWED = ["esp12_sensor_1"]
esp_ws = None
web_clients = set()

HTML = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Exercise Counter</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Arial', sans-serif; background: #0a0a0f; color: #fff; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
        .container { text-align: center; padding: 40px; max-width: 500px; width: 100%; }
        .counter { font-size: 160px; font-weight: bold; color: #ff6600; text-shadow: 0 0 50px rgba(255,102,0,0.5); line-height: 1; margin: 20px 0; }
        .exercise-name { font-size: 24px; color: #888; letter-spacing: 3px; margin-bottom: 10px; }
        .distance { font-size: 28px; color: #888; margin: 10px 0; }
        .distance span { color: #00ffff; font-weight: bold; }
        .exercise-buttons { display: flex; flex-direction: column; gap: 15px; margin: 30px 0; }
        .exercise-btn { padding: 20px; font-size: 18px; font-weight: bold; background: rgba(255,255,255,0.05); border: 2px solid rgba(255,255,255,0.1); color: #aaa; border-radius: 15px; cursor: pointer; transition: all 0.3s; display: flex; justify-content: space-between; align-items: center; }
        .exercise-btn:hover { background: rgba(255,255,255,0.1); }
        .exercise-btn.active { background: rgba(255,102,0,0.2); border-color: #ff6600; color: #ff6600; box-shadow: 0 0 20px rgba(255,102,0,0.2); }
        .btn-name { font-size: 20px; }
        .btn-distance { font-size: 14px; color: #666; background: rgba(255,255,255,0.1); padding: 5px 15px; border-radius: 20px; }
        .exercise-btn.active .btn-distance { background: rgba(255,102,0,0.3); color: #ffaa00; }
        .controls { background: rgba(255,255,255,0.03); border-radius: 20px; padding: 25px; margin: 20px 0; }
        .slider-container { margin: 15px 0; }
        .slider-label { display: flex; justify-content: space-between; margin-bottom: 10px; font-size: 13px; color: #666; }
        input[type="range"] { width: 100%; height: 6px; border-radius: 3px; background: linear-gradient(90deg, #00ff00, #ffaa00, #ff0000); outline: none; -webkit-appearance: none; }
        input[type="range"]::-webkit-slider-thumb { -webkit-appearance: none; width: 28px; height: 28px; border-radius: 50%; background: #fff; cursor: pointer; }
        .threshold-display { font-size: 32px; font-weight: bold; color: #ffaa00; margin: 10px 0; }
        .reset-btn { width: 100%; padding: 18px; font-size: 18px; font-weight: bold; background: rgba(255,0,0,0.2); border: 2px solid rgba(255,0,0,0.3); color: #ff4444; border-radius: 15px; cursor: pointer; letter-spacing: 3px; margin-top: 15px; }
        .reset-btn:hover { background: rgba(255,0,0,0.3); }
        .info-row { display: flex; justify-content: space-between; margin-top: 20px; font-size: 12px; color: #555; }
        .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }
        .dot.online { background: #00ff00; }
        .dot.offline { background: #ff0000; }
    </style>
</head>
<body>
    <div class="container">
        <div style="margin-bottom: 10px;">
            <span class="dot" id="dot"></span>
            <span style="color: #888; font-size: 12px;" id="connStatus">Connecting...</span>
        </div>
        
        <div class="exercise-name" id="exerciseName">STANDARD</div>
        <div class="counter" id="counter">0</div>
        <div class="distance">Distance: <span id="distDisplay">--- mm</span></div>
        
        <div class="exercise-buttons">
            <button class="exercise-btn active" id="btnPushup" onclick="setExercise('pushup')">
                <span class="btn-name">Отжимания</span>
                <span class="btn-distance">15 см</span>
            </button>
            <button class="exercise-btn" id="btnSquat" onclick="setExercise('squat')">
                <span class="btn-name">Приседания</span>
                <span class="btn-distance">40 см</span>
            </button>
            <button class="exercise-btn" id="btnCustom" onclick="setExercise('custom')">
                <span class="btn-name">Стандартное</span>
                <span class="btn-distance">10 см</span>
            </button>
        </div>
        
        <div class="controls">
            <div style="font-size: 14px; color: #666; letter-spacing: 2px; margin-bottom: 10px;">CUSTOM DISTANCE</div>
            <div class="threshold-display" id="thresholdValue">150 mm</div>
            <div class="slider-container">
                <div class="slider-label"><span>10mm</span><span>500mm</span></div>
                <input type="range" id="thresholdSlider" min="10" max="500" value="150" step="5">
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
        let currentExercise = 'pushup';
        let currentThreshold = 150;
        let isUpdatingFromServer = false;
        
        const exercises = {
            pushup: { name: 'ОТЖИМАНИЯ', distance: 150 },
            squat: { name: 'ПРИСЕДАНИЯ', distance: 400 },
            custom: { name: 'СТАНДАРТНОЕ', distance: 100 }
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
                if (data.type === 'update') {
                    updateDisplay(data.data);
                } else if (data.type === 'reset_confirm') {
                    document.getElementById('counter').textContent = '0';
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
            const threshold = d.threshold || 150;
            
            document.getElementById('distDisplay').textContent = dist.toFixed(1) + ' mm';
            
            document.getElementById('rssi').textContent = (d.rssi || 0) + ' dBm';
            
            const uptime = d.uptime || 0;
            const h = Math.floor(uptime / 3600);
            const m = Math.floor((uptime % 3600) / 60);
            const s = uptime % 60;
            document.getElementById('uptime').textContent = h + 'h ' + m + 'm ' + s + 's';
            
            // Обновляем порог только если он реально изменился на ESP
            if (threshold !== currentThreshold && !isUpdatingFromServer) {
                currentThreshold = threshold;
                document.getElementById('thresholdValue').textContent = threshold + ' mm';
                document.getElementById('thresholdSlider').value = threshold;
                
                // Определяем упражнение
                if (threshold === 150) currentExercise = 'pushup';
                else if (threshold === 400) currentExercise = 'squat';
                else if (threshold === 100) currentExercise = 'custom';
                else currentExercise = 'custom';
                
                updateActiveButton();
                document.getElementById('exerciseName').textContent = exercises[currentExercise].name;
            }
        }
        
        function setExercise(type) {
            const exercise = exercises[type];
            currentExercise = type;
            currentThreshold = exercise.distance;
            
            document.getElementById('exerciseName').textContent = exercise.name;
            document.getElementById('thresholdValue').textContent = exercise.distance + ' mm';
            document.getElementById('thresholdSlider').value = exercise.distance;
            updateActiveButton();
            
            // Отправляем порог на ESP
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({
                    type: 'set_threshold',
                    deviceId: 'esp12_sensor_1',
                    value: exercise.distance
                }));
            }
        }
        
        function updateActiveButton() {
            document.querySelectorAll('.exercise-btn').forEach(btn => btn.classList.remove('active'));
            if (currentExercise === 'pushup') document.getElementById('btnPushup').classList.add('active');
            if (currentExercise === 'squat') document.getElementById('btnSquat').classList.add('active');
            if (currentExercise === 'custom') document.getElementById('btnCustom').classList.add('active');
        }
        
        // Слайдер
        document.getElementById('thresholdSlider').addEventListener('input', function(e) {
            const value = parseInt(e.target.value);
            document.getElementById('thresholdValue').textContent = value + ' mm';
        });
        
        document.getElementById('thresholdSlider').addEventListener('change', function(e) {
            const value = parseInt(e.target.value);
            currentThreshold = value;
            currentExercise = 'custom';
            document.getElementById('exerciseName').textContent = exercises.custom.name;
            updateActiveButton();
            
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({
                    type: 'set_threshold',
                    deviceId: 'esp12_sensor_1',
                    value: value
                }));
            }
        });
        
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
    return web.Response(text=HTML, content_type='text/html')

async def handle_ws(request):
    global esp_ws
    ws = web.WebSocketResponse(protocols=['arduino', ''])
    await ws.prepare(request)
    
    client_type = None
    device_id = None
    
    print("🔌 New connection")
    
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                data = json.loads(msg.data)
                t = data.get("type", "")
                
                if t == "register":
                    did = data.get("deviceId", "")
                    if did in ALLOWED:
                        esp_ws = ws
                        client_type = "esp"
                        print(f"✅ ESP: {did}")
                        await ws.send_json({"type": "registered"})
                
                elif t == "sensor_data":
                    sensor = data.get("data", {})
                    upd = json.dumps({"type": "update", "data": sensor})
                    dead = set()
                    for c in web_clients.copy():
                        try:
                            await c.send_str(upd)
                        except:
                            dead.add(c)
                    web_clients.difference_update(dead)
                
                elif t == "reset":
                    target = data.get("deviceId", "esp12_sensor_1")
                    print(f"🔄 RESET {target}")
                    if esp_ws:
                        await esp_ws.send_str(json.dumps({"command": "reset"}))
                        # Подтверждение веб-клиентам
                        confirm = json.dumps({"type": "reset_confirm"})
                        for c in web_clients:
                            try:
                                await c.send_str(confirm)
                            except:
                                pass
                
                elif t == "set_threshold":
                    target = data.get("deviceId", "esp12_sensor_1")
                    value = int(data.get("value", 100))
                    print(f"📏 Threshold: {value}mm for {target}")
                    if esp_ws:
                        await esp_ws.send_str(json.dumps({"command": "set_threshold", "value": value}))
                
                elif t == "web_client":
                    client_type = "web"
                    web_clients.add(ws)
                    print(f"🌐 Web client (total: {len(web_clients)})")
    
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if client_type == "esp":
            esp_ws = None
        else:
            web_clients.discard(ws)
    
    return ws

if __name__ == '__main__':
    app = web.Application()
    app.router.add_get('/', handle_http)
    app.router.add_get('/ws', handle_ws)
    port = int(os.environ.get('PORT', 8000))
    print(f"Server on port {port}")
    web.run_app(app, port=port)
