# server.py
import asyncio
import websockets
import json
from datetime import datetime
from pathlib import Path

# Загружаем конфиг
def load_config():
    config_file = Path("config.json")
    if config_file.exists():
        with open(config_file, 'r') as f:
            return json.load(f)
    return {"allowed_devices": []}

# Сохраняем конфиг
def save_config(config):
    with open("config.json", 'w') as f:
        json.dump(config, f, indent=2)

# Загружаем или создаем конфиг
config = load_config()
if not config.get("allowed_devices"):
    config["allowed_devices"] = []
    save_config(config)

ALLOWED_DEVICES = config["allowed_devices"]

# Хранилище данных устройств
devices_data = {}
web_clients = set()  # Клиенты веб-интерфейса

print("=" * 60)
print("ESP12 MONITOR SERVER")
print("=" * 60)
print(f"Allowed devices: {ALLOWED_DEVICES}")
print("Add device IDs to config.json")
print("=" * 60)

async def handle_websocket(websocket, path):
    """Обработчик WebSocket соединений"""
    client_type = None  # 'esp' или 'web'
    device_id = None
    
    try:
        async for message in websocket:
            data = json.loads(message)
            
            # Регистрация устройства
            if data.get("type") == "register":
                device_id = data.get("deviceId", "")
                
                # Проверяем разрешено ли устройство
                if device_id not in ALLOWED_DEVICES:
                    print(f"❌ DENIED: {device_id} (not in config.json)")
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": f"Device {device_id} not allowed. Add to config.json"
                    }))
                    await websocket.close()
                    return
                
                client_type = "esp"
                devices_data[device_id] = {
                    "connected": True,
                    "last_data": None,
                    "last_update": None,
                    "websocket": websocket
                }
                print(f"✅ ESP Connected: {device_id}")
                
                await websocket.send(json.dumps({
                    "type": "registered",
                    "status": "success"
                }))
            
            # Данные с датчика
            elif data.get("type") == "sensor_data":
                device_id = data.get("deviceId", "unknown")
                sensor = data.get("data", {})
                
                # Обновляем данные
                if device_id in devices_data:
                    devices_data[device_id]["last_data"] = sensor
                    devices_data[device_id]["last_update"] = datetime.now().isoformat()
                
                # Выводим в консоль
                pin = "HIGH" if sensor.get("pin_state") else "LOW"
                freq = sensor.get("frequency", 0)
                rssi = sensor.get("rssi", 0)
                print(f"📡 {device_id} | Pin D0: {pin} | Freq: {freq}Hz | RSSI: {rssi}dBm")
                
                # Рассылаем всем веб-клиентам
                message_to_web = json.dumps({
                    "type": "update",
                    "deviceId": device_id,
                    "data": sensor,
                    "timestamp": datetime.now().isoformat()
                })
                
                disconnected_clients = set()
                for client in web_clients:
                    try:
                        await client.send(message_to_web)
                    except:
                        disconnected_clients.add(client)
                
                # Удаляем отключенных веб-клиентов
                web_clients.difference_update(disconnected_clients)
            
            # Если сообщение не от ESP - значит веб-клиент
            elif data.get("type") == "web_client":
                client_type = "web"
                web_clients.add(websocket)
                print(f"🌐 Web client connected (total: {len(web_clients)})")
                
                # Отправляем текущие данные всех устройств
                for dev_id, dev_data in devices_data.items():
                    if dev_data.get("last_data"):
                        await websocket.send(json.dumps({
                            "type": "update",
                            "deviceId": dev_id,
                            "data": dev_data["last_data"],
                            "timestamp": dev_data.get("last_update")
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
            print(f"🌐 Web client disconnected (total: {len(web_clients)})")

async def main():
    print("Starting WebSocket server on ws://0.0.0.0:8765")
    async with websockets.serve(handle_websocket, "0.0.0.0", 8765):
        await asyncio.Future()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped")
