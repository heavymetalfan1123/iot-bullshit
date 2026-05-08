# server.py
import asyncio
import websockets
import json
from datetime import datetime
from pathlib import Path
import http.server
import socketserver
import threading
import urllib.parse

# ====== КОНФИГУРАЦИЯ ======
WS_PORT = 8765
HTTP_PORT = 8000

# Загружаем конфиг
def load_config():
    config_file = Path("config.json")
    if config_file.exists():
        with open(config_file, 'r') as f:
            return json.load(f)
    return {"allowed_devices": ["esp12_sensor_1", "esp12_test"]}

config = load_config()
ALLOWED_DEVICES = config.get("allowed_devices", ["esp12_sensor_1"])

print("=" * 60)
print("ESP12 MONITOR SERVER")
print("=" * 60)
print(f"Allowed devices: {ALLOWED_DEVICES}")
print(f"Web UI: http://0.0.0.0:{HTTP_PORT}")
print(f"WebSocket: ws://0.0.0.0:{WS_PORT}")
print("=" * 60)

# Хранилище данных
devices_data = {}
web_clients = set()

# HTML страница
HTML_PAGE = """
<!DOCTYPE html>
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
            overflow: hidden;
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
            text-shadow: 0 0 20px rgba(255,0,0,0.5), 0 0 40px rgba(255,0,0,0.3);
        }
        @keyframes glow {
            from { text-shadow: 0 0 20px rgba(0,255,0,0.5); }
            to { text-shadow: 0 0 40px rgba(0,255,0,1); }
        }
        .info { font-size: 20px; color: #888; margin-top: 20px; }
        .status { display: inline-block; width: 12px; height: 12px; border-radius: 50%; margin-right: 10px; }
        .status.connected { background: #00ff00; box-shadow: 0 0 10px #00ff00; }
        .status.disconnected { background: #ff0000; box-shadow: 0 0 10px #ff0000; }
        .stats { margin-top: 40px; display: grid; grid-template-columns: repeat(3, 1fr); gap: 30px; }
        .stat-box { background: rgba(0,255,0,0.05); border: 1px solid rgba(0,255,0,0.2); border-radius: 10px; padding: 20px; }
        .stat-label { font-size: 12px; color: #666; margin-bottom: 10px; text-transform: uppercase; }
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
        const PORT = """ + str(WS_PORT) + """;
        const wsUrl = 'ws://' + window.location.hostname + ':' + PORT;
        let ws;
        
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
                    document.getElementById('frequency').textContent = (d.frequency || 0).toFixed(1) + ' Hz';
                    document.getElementById('rssi').textContent = (d.rssi || 0) + ' dBm';
                    const uptime = d.uptime || 0;
                    const h = Math.floor(uptime/3600);
                    const m = Math.floor((uptime%3600)/60);
                    const s = uptime % 60;
                    document.getElementById('uptime').textContent = h + 'h ' + m + 'm ' + s + 's';
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
</html>
"""

# HTTP сервер для веб-страницы
class WebHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode())
        elif self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())
        else:
            self.send_response(404)
            self.end_headers()

def run_http_server():
    """Запуск HTTP сервера в отдельном потоке"""
    server = socketserver.TCPServer(("0.0.0.0", HTTP_PORT), WebHandler)
    print(f"HTTP Server started on port {HTTP_PORT}")
    server.serve_forever()

# WebSocket сервер
async def handle_websocket(websocket, path=None):
    """Обработчик WebSocket"""
    client_type = None
    device_id = None
    
    try:
        async for message in websocket:
            data = json.loads(message)
            
            if data.get("type") == "register":
                device_id = data.get("deviceId", "")
                
                if device_id not in ALLOWED_DEVICES:
                    print(f"❌ DENIED: {device_id}")
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": "Device not allowed"
                    }))
                    continue
                
                client_type = "esp"
                devices_data[device_id] = {
                    "connected": True,
                    "last_data": None,
                    "last_update": None
                }
                print(f"✅ ESP Connected: {device_id}")
                
                await websocket.send(json.dumps({
                    "type": "registered",
                    "status": "success"
                }))
            
            elif data.get("type") == "sensor_data":
                device_id = data.get("deviceId", "unknown")
                sensor = data.get("data", {})
                
                if device_id in devices_data:
                    devices_data[device_id]["last_data"] = sensor
                    devices_data[device_id]["last_update"] = datetime.now().isoformat()
                
                pin = "HIGH" if sensor.get("pin_state") else "LOW"
                freq = sensor.get("frequency", 0)
                print(f"📡 {device_id} | Pin: {pin} | Freq: {freq}Hz")
                
                # Рассылка веб-клиентам
                msg = json.dumps({
                    "type": "update",
                    "deviceId": device_id,
                    "data": sensor
                })
                
                to_remove = set()
                for client in web_clients:
                    try:
                        await client.send(msg)
                    except:
                        to_remove.add(client)
                web_clients.difference_update(to_remove)
            
            elif data.get("type") == "web_client":
                client_type = "web"
                web_clients.add(websocket)
                print(f"🌐 Web client (total: {len(web_clients)})")
                
                # Отправляем последние данные
                for dev_id, dev_data in devices_data.items():
                    if dev_data.get("last_data"):
                        await websocket.send(json.dumps({
                            "type": "update",
                            "deviceId": dev_id,
                            "data": dev_data["last_data"]
                        }))
    
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        if client_type == "esp" and device_id:
            if device_id in devices_data:
                devices_data[device_id]["connected"] = False
            print(f"❌ ESP Disconnected: {device_id}")
        elif client_type == "web":
            web_clients.discard(websocket)

async def main():
    # Запускаем HTTP в потоке
    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()
    
    # Запускаем WebSocket
    print(f"Starting WebSocket on port {WS_PORT}")
    async with websockets.serve(handle_websocket, "0.0.0.0", WS_PORT):
        await asyncio.Future()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped")
