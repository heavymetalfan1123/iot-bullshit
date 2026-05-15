import os, json
from aiohttp import web

ALLOWED = ["esp12_security"]
esp_ws = None
web_clients = set()
last_alarm = False

# HTML для сайта
HTML = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="theme-color" content="#0a0a0f">
    <link rel="manifest" href="/manifest.json">
    <title>Security</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Arial; background: #0a0a0f; color: #fff; text-align: center; padding: 20px; min-height: 100vh; }
        .circle { width: 150px; height: 150px; border-radius: 50%; margin: 20px auto; line-height: 150px; font-size: 20px; font-weight: bold; border: 4px solid; }
        .disarmed { background: rgba(0,255,0,0.1); border-color: #0f0; color: #0f0; }
        .armed { background: rgba(255,165,0,0.1); border-color: #fa0; color: #fa0; }
        .alarm { background: rgba(255,0,0,0.2); border-color: #f00; color: #f00; animation: pulse 0.5s infinite; }
        @keyframes pulse { 0%,100% { transform: scale(1); } 50% { transform: scale(1.05); } }
        .btn { padding: 20px; font-size: 20px; font-weight: bold; border: 3px solid; border-radius: 15px; cursor: pointer; margin: 10px; width: 90%; max-width: 400px; -webkit-tap-highlight-color: transparent; }
        .btn.arm { background: rgba(255,165,0,0.2); border-color: #fa0; color: #fa0; }
        .btn.disarm { background: rgba(0,255,0,0.2); border-color: #0f0; color: #0f0; }
        .dist-btn { padding: 15px 10px; margin: 5px; font-size: 14px; background: rgba(255,255,255,0.05); border: 2px solid rgba(255,255,255,0.1); color: #aaa; border-radius: 10px; cursor: pointer; -webkit-tap-highlight-color: transparent; }
        .dist-btn.active { background: rgba(255,102,0,0.2); border-color: #f60; color: #f60; }
        #installBtn { display: none; padding: 15px; background: #4CAF50; color: white; border: none; border-radius: 10px; font-size: 16px; cursor: pointer; margin: 20px 0; width: 90%; max-width: 400px; }
        #log { margin-top: 20px; font-size: 10px; color: #444; max-height: 80px; overflow-y: auto; text-align: left; padding: 10px; background: rgba(255,255,255,0.02); border-radius: 10px; }
    </style>
</head>
<body>
    <button id="installBtn" onclick="installApp()">📲 INSTALL APP</button>
    <div><span id="dot" style="color:red">●</span> <span id="conn">Connecting...</span></div>
    <div class="circle disarmed" id="circle">DISARMED</div>
    <div id="alarms" style="display:none;font-size:40px;color:#f44">🚨 ALARMS: 0</div>
    <div style="font-size:22px;color:#888">Distance: <span style="color:#0ff" id="dist">--- cm</span></div>
    <button class="btn arm" id="armBtn" onclick="toggle()">🔒 ARM SYSTEM</button>
    <div style="font-size:13px;color:#666;margin:20px 0">DETECTION RANGE</div>
    <div style="font-size:28px;color:#fa0" id="thr">200 cm</div>
    <div>
        <button class="dist-btn active" onclick="setDist(100)">1m</button>
        <button class="dist-btn" onclick="setDist(150)">1.5m</button>
        <button class="dist-btn" onclick="setDist(200)">2m</button>
    </div>
    <div>
        <button class="dist-btn" onclick="setDist(300)">3m</button>
        <button class="dist-btn" onclick="setDist(400)">4m</button>
        <button class="dist-btn" onclick="setDist(500)">5m</button>
    </div>
    <div style="margin-top:20px;font-size:12px;color:#555">
        <span>Signal: <span id="rssi">---</span></span> |
        <span>Uptime: <span id="uptime">0s</span></span>
    </div>
    <div id="log"></div>
    
    <script>
        // Service Worker для уведомлений
        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.register('/sw.js').then(function(reg) {
                log('✅ Service Worker registered');
            }).catch(function(err) {
                log('❌ SW error: ' + err);
            });
        }
        
        // PWA Install
        let deferredPrompt;
        window.addEventListener('beforeinstallprompt', function(e) {
            e.preventDefault();
            deferredPrompt = e;
            document.getElementById('installBtn').style.display = 'block';
            log('📲 App can be installed!');
        });
        
        function installApp() {
            if (deferredPrompt) {
                deferredPrompt.prompt();
                deferredPrompt.userChoice.then(function(result) {
                    log('Install: ' + result.outcome);
                    document.getElementById('installBtn').style.display = 'none';
                });
            }
        }
        
        let ws, armed = false, thr = 200;
        
        function log(msg) {
            let el = document.getElementById('log');
            el.innerHTML += new Date().toLocaleTimeString() + ': ' + msg + '<br>';
            el.scrollTop = el.scrollHeight;
            console.log(msg);
        }
        
        async function showNotification(title, body) {
            log('🔔 Showing notification: ' + title);
            
            if (Notification.permission === 'granted') {
                // Через Service Worker (работает даже в фоне)
                if (navigator.serviceWorker && navigator.serviceWorker.ready) {
                    let reg = await navigator.serviceWorker.ready;
                    reg.showNotification(title, {
                        body: body,
                        icon: '/icon.png',
                        badge: '/icon.png',
                        tag: 'alarm',
                        requireInteraction: true,
                        vibrate: [200, 100, 200, 100, 200],
                        actions: [
                            { action: 'open', title: 'Open App' },
                            { action: 'close', title: 'Close' }
                        ]
                    });
                    log('✅ Notification via SW');
                } else {
                    // Обычное уведомление
                    new Notification(title, {
                        body: body,
                        icon: '/icon.png',
                        tag: 'alarm',
                        requireInteraction: true,
                        vibrate: [200, 100, 200, 100, 200]
                    });
                    log('✅ Regular notification');
                }
            } else if (Notification.permission === 'default') {
                log('📝 Requesting permission...');
                let perm = await Notification.requestPermission();
                log('Permission: ' + perm);
                if (perm === 'granted') {
                    showNotification(title, body);
                }
            } else {
                log('❌ Notifications blocked!');
            }
        }
        
        function playSound() {
            try {
                let ctx = new (window.AudioContext || window.webkitAudioContext)();
                [0, 300, 600].forEach(function(delay) {
                    setTimeout(function() {
                        let o = ctx.createOscillator();
                        let g = ctx.createGain();
                        o.connect(g); g.connect(ctx.destination);
                        o.frequency.value = 800;
                        o.type = 'square';
                        g.gain.value = 0.3;
                        o.start();
                        setTimeout(function() { o.stop(); }, 200);
                    }, delay);
                });
            } catch(e) {}
        }
        
        function connect() {
            ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws');
            ws.onopen = function() {
                document.getElementById('dot').style.color = '#0f0';
                document.getElementById('conn').textContent = 'Connected';
                ws.send(JSON.stringify({type: 'web_client'}));
                log('✅ Connected');
                
                // Запрашиваем разрешение на уведомления
                if (Notification.permission === 'default') {
                    Notification.requestPermission();
                }
            };
            ws.onmessage = function(e) {
                let d = JSON.parse(e.data);
                if (d.type === 'update') update(d.data);
                else if (d.type === 'alarm') {
                    log('🚨 ALARM RECEIVED!');
                    showNotification('🚨 SECURITY ALARM!', 'Intruder detected! Distance: ' + (d.distance || 0) + 'cm');
                    playSound();
                }
            };
            ws.onclose = function() {
                document.getElementById('dot').style.color = 'red';
                document.getElementById('conn').textContent = 'Reconnecting...';
                setTimeout(connect, 3000);
            };
        }
        
        function update(d) {
            document.getElementById('dist').textContent = (d.distance || 0).toFixed(1) + ' cm';
            let c = document.getElementById('circle');
            if (d.alarm) {
                c.className = 'circle alarm';
                c.textContent = '🚨 ALARM!';
                document.getElementById('alarms').style.display = 'block';
                document.getElementById('alarms').textContent = '🚨 ALARMS: ' + (d.alarm_count || 0);
            } else if (d.security_mode) {
                c.className = 'circle armed';
                c.textContent = 'ARMED';
                document.getElementById('alarms').style.display = 'none';
            } else {
                c.className = 'circle disarmed';
                c.textContent = 'DISARMED';
                document.getElementById('alarms').style.display = 'none';
            }
            let btn = document.getElementById('armBtn');
            if (d.security_mode) { btn.textContent = '🔓 DISARM'; btn.className = 'btn disarm'; armed = true; }
            else { btn.textContent = '🔒 ARM SYSTEM'; btn.className = 'btn arm'; armed = false; }
            if (d.threshold !== thr) { thr = d.threshold; document.getElementById('thr').textContent = thr + ' cm'; updateBtns(thr); }
            document.getElementById('rssi').textContent = (d.rssi || 0) + ' dBm';
            let u = d.uptime || 0;
            document.getElementById('uptime').textContent = Math.floor(u / 3600) + 'h ' + Math.floor((u % 3600) / 60) + 'm ' + u % 60 + 's';
        }
        
        function updateBtns(v) {
            document.querySelectorAll('.dist-btn').forEach(function(b) {
                b.classList.remove('active');
                let t = b.textContent;
                if ((t === '1m' && v === 100) || (t === '1.5m' && v === 150) || (t === '2m' && v === 200) || (t === '3m' && v === 300) || (t === '4m' && v === 400) || (t === '5m' && v === 500)) b.classList.add('active');
            });
        }
        
        function setDist(v) { thr = v; document.getElementById('thr').textContent = v + ' cm'; updateBtns(v); if (ws) ws.send(JSON.stringify({type: 'set_threshold', value: v})); }
        function toggle() { if (ws) ws.send(JSON.stringify({type: armed ? 'disarm' : 'arm'})); }
        
        connect();
    </script>
</body>
</html>"""

# Service Worker
SW_JS = """
self.addEventListener('install', function(e) {
    console.log('SW installed');
    self.skipWaiting();
});

self.addEventListener('activate', function(e) {
    console.log('SW activated');
    e.waitUntil(self.clients.claim());
});

self.addEventListener('push', function(e) {
    let data = e.data.json();
    self.registration.showNotification(data.title, data.options);
});

self.addEventListener('notificationclick', function(e) {
    e.notification.close();
    e.waitUntil(
        clients.matchAll({type: 'window'}).then(function(clientList) {
            for (let client of clientList) {
                if (client.url && 'focus' in client) {
                    return client.focus();
                }
            }
            if (clients.openWindow) {
                return clients.openWindow('/');
            }
        })
    );
});
"""

# Manifest для PWA
MANIFEST = {
    "name": "Security System",
    "short_name": "Security",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#0a0a0f",
    "theme_color": "#0a0a0f",
    "icons": [
        {"src": "/icon.png", "sizes": "192x192", "type": "image/png"}
    ]
}

async def handle_http(request):
    return web.Response(text=HTML, content_type='text/html')

async def handle_sw(request):
    return web.Response(text=SW_JS, content_type='application/javascript')

async def handle_manifest(request):
    return web.json_response(MANIFEST)

async def handle_icon(request):
    # Простая иконка 1x1 пиксель PNG
    icon = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
    return web.Response(body=icon, content_type='image/png')

async def ws_handler(request):
    global esp_ws, last_alarm
    ws = web.WebSocketResponse(protocols=['arduino', ''])
    await ws.prepare(request)
    
    client_type = None
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
                    current_alarm = sensor.get("alarm", False)
                    distance = sensor.get("distance", 0)
                    
                    if current_alarm and not last_alarm:
                        print(f"🚨🚨🚨 ALARM! Distance: {distance}cm 🚨🚨🚨")
                        alarm_msg = json.dumps({
                            "type": "alarm",
                            "distance": distance
                        })
                        dead = set()
                        for c in web_clients.copy():
                            try:
                                await c.send_str(alarm_msg)
                            except:
                                dead.add(c)
                        web_clients.difference_update(dead)
                    
                    last_alarm = current_alarm
                    
                    upd = json.dumps({"type": "update", "data": sensor})
                    dead = set()
                    for c in web_clients.copy():
                        try:
                            await c.send_str(upd)
                        except:
                            dead.add(c)
                    web_clients.difference_update(dead)
                
                elif t == "arm":
                    print("🔒 ARM")
                    if esp_ws:
                        await esp_ws.send_str('{"command":"arm"}')
                
                elif t == "disarm":
                    print("🔓 DISARM")
                    if esp_ws:
                        await esp_ws.send_str('{"command":"disarm"}')
                
                elif t == "set_threshold":
                    v = int(data.get("value", 200))
                    print(f"📏 Threshold: {v}cm")
                    if esp_ws:
                        await esp_ws.send_str('{"command":"set_threshold","value":'+str(v)+'}')
                
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
    app.router.add_get('/sw.js', handle_sw)
    app.router.add_get('/manifest.json', handle_manifest)
    app.router.add_get('/icon.png', handle_icon)
    app.router.add_get('/ws', ws_handler)
    
    port = int(os.environ.get('PORT', 8000))
    print(f"Server on port {port}")
    web.run_app(app, port=port)
