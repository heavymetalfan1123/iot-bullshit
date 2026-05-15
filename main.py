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
        
        .status-circle {
            width: 200px;
            height: 200px;
            border-radius: 50%;
            margin: 0 auto 30px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 20px;
            font-weight: bold;
            letter-spacing: 3px;
            transition: all 0.5s;
            border: 4px solid;
        }
        
        .status-circle.disarmed {
            background: rgba(0,255,0,0.1);
            border-color: #00ff00;
            color: #00ff00;
            box-shadow: 0 0 50px rgba(0,255,0,0.2);
        }
        
        .status-circle.armed {
            background: rgba(255,165,0,0.1);
            border-color: #ffaa00;
            color: #ffaa00;
            box-shadow: 0 0 50px rgba(255,165,0,0.3);
            animation: pulse-armed 2s infinite;
        }
        
        .status-circle.alarm {
            background: rgba(255,0,0,0.2);
            border-color: #ff0000;
            color: #ff0000;
            box-shadow: 0 0 80px rgba(255,0,0,0.5);
            animation: pulse-alarm 0.5s infinite;
        }
        
        @keyframes pulse-armed {
            0%, 100% { box-shadow: 0 0 30px rgba(255,165,0,0.3); }
            50% { box-shadow: 0 0 60px rgba(255,165,0,0.5); }
        }
        
        @keyframes pulse-alarm {
            0%, 100% { transform: scale(1); box-shadow: 0 0 50px rgba(255,0,0,0.5); }
            50% { transform: scale(1.05); box-shadow: 0 0 100px rgba(255,0,0,0.8); }
        }
        
        .alarm-count {
            font-size: 48px;
            font-weight: bold;
            color: #ff4444;
            margin: 20px 0;
        }
        
        .distance-display {
            font-size: 24px;
            color: #888;
            margin: 10px 0;
        }
        
        .distance-display span {
            color: #00ffff;
            font-weight: bold;
        }
        
        .controls {
            background: rgba(255,255,255,0.03);
            border-radius: 20px;
            padding: 30px;
            margin: 30px 0;
        }
        
        .arm-btn {
            width: 100%;
            padding: 25px;
            font-size: 22px;
            font-weight: bold;
            border: 3px solid;
            border-radius: 20px;
            cursor: pointer;
            transition: all 0.3s;
            letter-spacing: 3px;
            margin-bottom: 15px;
        }
        
        .arm-btn.arm {
            background: rgba(255,165,0,0.2);
            border-color: #ffaa00;
            color: #ffaa00;
        }
        
        .arm-btn.arm:hover {
            background: rgba(255,165,0,0.3);
            box-shadow: 0 0 30px rgba(255,165,0,0.3);
        }
        
        .arm-btn.disarm {
            background: rgba(0,255,0,0.2);
            border-color: #00ff00;
            color: #00ff00;
        }
        
        .arm-btn.disarm:hover {
            background: rgba(0,255,0,0.3);
            box-shadow: 0 0 30px rgba(0,255,0,0.3);
        }
        
        .arm-btn:active {
            transform: scale(0.97);
        }
        
        .threshold-section {
            margin-top: 20px;
        }
        
        .threshold-label {
            font-size: 14px;
            color: #666;
            letter-spacing: 2px;
            margin-bottom: 15px;
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
        }
        
        .threshold-value {
            font-size: 28px;
            color: #ffaa00;
            margin: 10px 0;
            font-weight: bold;
        }
        
        .reset-btn {
            padding: 15px 40px;
            font-size: 16px;
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.2);
            color: #888;
            border-radius: 10px;
            cursor: pointer;
            margin-top: 15px;
            transition: all 0.3s;
        }
        
        .reset-btn:hover {
            background: rgba(255,255,255,0.1);
            color: #fff;
        }
        
        .info-row {
            display: flex;
            justify-content: space-between;
            margin-top: 20px;
            font-size: 12px;
            color: #555;
        }
        
        .dot {
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            margin-right: 8px;
        }
        
        .dot.online { background: #00ff00; }
        .dot.offline { background: #ff0000; }
    </style>
</head>
<body>
    <div class="container">
        <div style="margin-bottom: 10px;">
            <span class="dot" id="dot"></span>
            <span style="color: #888; font-size: 13px;" id="connStatus">Connecting...</span>
        </div>
        
        <div class="status-circle disarmed" id="statusCircle">
            DISARMED
        </div>
        
        <div class="alarm-count" id="alarmCount" style="display: none;">
            🚨 ALARMS: 0
        </div>
        
        <div class="distance-display">
            Distance: <span id="distDisplay">--- mm</span>
        </div>
        
        <div class="controls">
            <button class="arm-btn arm" id="armBtn" onclick="toggleArm()">
                🔒 ARM SYSTEM
            </button>
            
            <div class="threshold-section">
                <div class="threshold-label">DETECTION RANGE</div>
                <div class="threshold-value" id="thresholdValue">200 cm</div>
                <input type="range" id="thresholdSlider" min="50" max="500" value="200" step="10">
                <div style="display: flex; justify-content: space-between; font-size: 11px; color: #555; margin-top: 5px;">
                    <span>50cm</span>
                    <span>500cm</span>
                </div>
            </div>
        </div>
        
        <button class="reset-btn" onclick="resetAlarms()">🔄 Reset Alarm Counter</button>
        
        <div class="info-row">
            <span>Signal: <span id="rssi">---</span></span>
            <span>Uptime: <span id="uptime">0s</span></span>
        </div>
    </div>
    
    <script>
        const wsUrl = (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws';
        let ws;
        let isArmed = false;
        let hasAlarm = false;
        
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
                } else if (data.type === 'alarm_notification') {
                    // Уведомление о тревоге
                    showNotification(data.message);
                }
            };
            
            ws.onclose = () => {
                document.getElementById('dot').className = 'dot offline';
                document.getElementById('connStatus').textContent = 'Reconnecting...';
                setTimeout(connect, 3000);
            };
        }
        
        function updateDisplay(d) {
            const dist = d.distance || 0;
            const threshold = d.threshold || 200;
            const securityMode = d.security_mode;
            const alarm = d.alarm;
            const alarmCnt = d.alarm_count || 0;
            
            document.getElementById('distDisplay').textContent = dist.toFixed(1) + ' mm';
            
            // Статус системы
            const circle = document.getElementById('statusCircle');
            const armBtn = document.getElementById('armBtn');
            
            if (alarm) {
                circle.className = 'status-circle alarm';
                circle.textContent = '🚨 ALARM!';
                document.getElementById('alarmCount').style.display = 'block';
                document.getElementById('alarmCount').textContent = '🚨 ALARMS: ' + alarmCnt;
                
                if (!hasAlarm) {
                    showNotification('🚨 INTRUDER DETECTED!');
                    hasAlarm = true;
                }
            } else if (securityMode) {
                circle.className = 'status-circle armed';
                circle.textContent = 'ARMED';
                hasAlarm = false;
            } else {
                circle.className = 'status-circle disarmed';
                circle.textContent = 'DISARMED';
                document.getElementById('alarmCount').style.display = 'none';
                hasAlarm = false;
            }
            
            // Кнопка ARM/DISARM
            if (securityMode) {
                armBtn.textContent = '🔓 DISARM';
                armBtn.className = 'arm-btn disarm';
                isArmed = true;
            } else {
                armBtn.textContent = '🔒 ARM SYSTEM';
                armBtn.className = 'arm-btn arm';
                isArmed = false;
            }
            
            // Обновляем слайдер
            if (threshold !== parseInt(document.getElementById('thresholdSlider').value)) {
                document.getElementById('thresholdSlider').value = threshold;
                document.getElementById('thresholdValue').textContent = threshold + ' cm';
            }
            
            document.getElementById('rssi').textContent = (d.rssi || 0) + ' dBm';
            
            const uptime = d.uptime || 0;
            const h = Math.floor(uptime / 3600);
            const m = Math.floor((uptime % 3600) / 60);
            const s = uptime % 60;
            document.getElementById('uptime').textContent = h + 'h ' + m + 'm ' + s + 's';
        }
        
        function toggleArm() {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({
                    type: isArmed ? 'disarm' : 'arm',
                    deviceId: 'esp12_security'
                }));
            }
        }
        
        function resetAlarms() {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({
                    type: 'reset_alarm',
                    deviceId: 'esp12_security'
                }));
            }
        }
        
        document.getElementById('thresholdSlider').addEventListener('input', function(e) {
            const value = parseInt(e.target.value);
            document.getElementById('thresholdValue').textContent = value + ' cm';
        });
        
        document.getElementById('thresholdSlider').addEventListener('change', function(e) {
            const value = parseInt(e.target.value);
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({
                    type: 'set_threshold',
                    deviceId: 'esp12_security',
                    value: value
                }));
            }
        });
        
        function showNotification(message) {
            // Браузерное уведомление
            if (Notification.permission === 'granted') {
                new Notification('Security System', {
                    body: message,
                    icon: '🔒'
                });
            } else if (Notification.permission !== 'denied') {
                Notification.requestPermission().then(permission => {
                    if (permission === 'granted') {
                        new Notification('Security System', {
                            body: message,
                            icon: '🔒'
                        });
                    }
                });
            }
            
            // Звуковой сигнал
            try {
                const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                const oscillator = audioCtx.createOscillator();
                const gainNode = audioCtx.createGain();
                oscillator.connect(gainNode);
                gainNode.connect(audioCtx.destination);
                oscillator.frequency.value = 800;
                oscillator.type = 'square';
                gainNode.gain.value = 0.3;
                oscillator.start();
                setTimeout(() => {
                    oscillator.stop();
                    audioCtx.close();
                }, 500);
            } catch(e) {}
        }
        
        // Запрашиваем разрешение на уведомления при загрузке
        if (Notification.permission === 'default') {
            Notification.requestPermission();
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
    last_alarm = False
    
    print("🔌 New connection")
    
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    
                    if data.get("type") == "register":
                        device_id = data.get("deviceId", "")
                        
                        if device_id not in ALLOWED_DEVICES:
                            await ws.send_json({"type": "error"})
                            continue
                        
                        client_type = "esp"
                        esp_clients[device_id] = ws
                        print(f"✅ ESP: {device_id}")
                        await ws.send_json({"type": "registered"})
                    
                    elif data.get("type") == "sensor_data":
                        sensor = data.get("data", {})
                        
                        # Проверяем новую тревогу
                        if sensor.get("alarm") and not last_alarm:
                            print(f"🚨 ALARM! Distance: {sensor.get('distance')}mm")
                            # Отправляем уведомление веб-клиентам
                            notif = json.dumps({
                                "type": "alarm_notification",
                                "message": f"🚨 INTRUDER DETECTED! Distance: {sensor.get('distance', 0):.1f}mm"
                            })
                            for client in web_clients.copy():
                                try:
                                    await client.send_str(notif)
                                except:
                                    pass
                        
                        last_alarm = sensor.get("alarm", False)
                        
                        # Рассылаем обновление
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
                    
                    elif data.get("type") in ["arm", "disarm"]:
                        target = data.get("deviceId", "esp12_security")
                        command = "arm" if data.get("type") == "arm" else "disarm"
                        print(f"🔒 {command.upper()} {target}")
                        
                        if target in esp_clients:
                            await esp_clients[target].send_str(json.dumps({
                                "type": "command",
                                "command": command
                            }))
                    
                    elif data.get("type") == "set_threshold":
                        target = data.get("deviceId", "esp12_security")
                        value = int(data.get("value", 200))
                        print(f"📏 Threshold {value}cm")
                        
                        if target in esp_clients:
                            await esp_clients[target].send_str(json.dumps({
                                "type": "command",
                                "command": "set_threshold",
                                "value": value
                            }))
                    
                    elif data.get("type") == "reset_alarm":
                        target = data.get("deviceId", "esp12_security")
                        print(f"🔄 Reset alarms {target}")
                        
                        if target in esp_clients:
                            await esp_clients[target].send_str(json.dumps({
                                "type": "command",
                                "command": "reset_alarm"
                            }))
                    
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
    print(f"Security Server on port {port}")
    web.run_app(app, port=port)
