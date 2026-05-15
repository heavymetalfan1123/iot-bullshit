import os, json
from aiohttp import web

ALLOWED = ["esp12_security"]
esp_ws = None
web_clients = set()

HTML = """<html><head><meta charset="UTF-8"><title>Security</title>
<style>body{font-family:Arial;background:#0a0a0f;color:#fff;text-align:center;padding:30px}
.circle{width:150px;height:150px;border-radius:50%;margin:20px auto;line-height:150px;font-size:20px;font-weight:bold;border:4px solid}
.disarmed{background:rgba(0,255,0,0.1);border-color:#0f0;color:#0f0}
.armed{background:rgba(255,165,0,0.1);border-color:#fa0;color:#fa0}
.alarm{background:rgba(255,0,0,0.2);border-color:#f00;color:#f00;animation:pulse 0.5s infinite}
@keyframes pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.05)}}
.btn{padding:20px;font-size:20px;font-weight:bold;border:3px solid;border-radius:15px;cursor:pointer;margin:10px;width:80%}
.btn.arm{background:rgba(255,165,0,0.2);border-color:#fa0;color:#fa0}
.btn.disarm{background:rgba(0,255,0,0.2);border-color:#0f0;color:#0f0}
.dist-btn{padding:15px;margin:5px;font-size:14px;background:rgba(255,255,255,0.05);border:2px solid rgba(255,255,255,0.1);color:#aaa;border-radius:10px;cursor:pointer}
.dist-btn.active{background:rgba(255,102,0,0.2);border-color:#f60;color:#f60}
</style></head><body>
<div><span id="dot" style="color:red">●</span> <span id="conn">Connecting...</span></div>
<div class="circle disarmed" id="circle">DISARMED</div>
<div id="alarms" style="display:none;font-size:40px;color:#f44">🚨 ALARMS: 0</div>
<div style="font-size:22px;color:#888">Distance: <span style="color:#0ff" id="dist">--- cm</span></div>
<button class="btn arm" id="armBtn" onclick="toggle()">🔒 ARM SYSTEM</button>
<div style="font-size:13px;color:#666;margin:20px 0">DETECTION RANGE</div>
<div style="font-size:28px;color:#fa0" id="thr">200 cm</div>
<button class="dist-btn active" onclick="setDist(100)">1m</button>
<button class="dist-btn" onclick="setDist(150)">1.5m</button>
<button class="dist-btn" onclick="setDist(200)">2m</button>
<button class="dist-btn" onclick="setDist(300)">3m</button>
<button class="dist-btn" onclick="setDist(400)">4m</button>
<button class="dist-btn" onclick="setDist(500)">5m</button>
<div style="margin-top:20px;font-size:12px;color:#555">
<span>Signal: <span id="rssi">---</span></span> |
<span>Uptime: <span id="uptime">0s</span></span>
</div>
<script>
let ws, armed=false, thr=200;
function connect(){
 ws=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/ws');
 ws.onopen=()=>{document.getElementById('dot').style.color='#0f0';document.getElementById('conn').textContent='Connected';ws.send(JSON.stringify({type:'web_client'}));};
 ws.onmessage=e=>{let d=JSON.parse(e.data);if(d.type==='update')update(d.data);};
 ws.onclose=()=>{document.getElementById('dot').style.color='red';document.getElementById('conn').textContent='Reconnecting...';setTimeout(connect,3000);};
}
function update(d){
 document.getElementById('dist').textContent=(d.distance||0).toFixed(1)+' cm';
 let c=document.getElementById('circle');
 if(d.alarm){c.className='circle alarm';c.textContent='🚨 ALARM!';document.getElementById('alarms').style.display='block';document.getElementById('alarms').textContent='🚨 ALARMS: '+(d.alarm_count||0);}
 else if(d.security_mode){c.className='circle armed';c.textContent='ARMED';document.getElementById('alarms').style.display='none';}
 else{c.className='circle disarmed';c.textContent='DISARMED';document.getElementById('alarms').style.display='none';}
 let btn=document.getElementById('armBtn');
 if(d.security_mode){btn.textContent='🔓 DISARM';btn.className='btn disarm';armed=true;}
 else{btn.textContent='🔒 ARM SYSTEM';btn.className='btn arm';armed=false;}
 if(d.threshold!==thr){thr=d.threshold;document.getElementById('thr').textContent=thr+' cm';updateBtns(thr);}
 document.getElementById('rssi').textContent=(d.rssi||0)+' dBm';
 let u=d.uptime||0;document.getElementById('uptime').textContent=Math.floor(u/3600)+'h '+Math.floor((u%3600)/60)+'m '+u%60+'s';
}
function updateBtns(v){document.querySelectorAll('.dist-btn').forEach(b=>{b.classList.remove('active');let t=b.textContent;if((t==='1m'&&v===100)||(t==='1.5m'&&v===150)||(t==='2m'&&v===200)||(t==='3m'&&v===300)||(t==='4m'&&v===400)||(t==='5m'&&v===500))b.classList.add('active');});}
function setDist(v){thr=v;document.getElementById('thr').textContent=v+' cm';updateBtns(v);if(ws)ws.send(JSON.stringify({type:'set_threshold',value:v}));}
function toggle(){if(ws)ws.send(JSON.stringify({type:armed?'disarm':'arm'}));}
connect();
</script></body></html>"""

async def http_handler(request):
    return web.Response(text=HTML, content_type='text/html')

async def ws_handler(request):
    global esp_ws
    ws = web.WebSocketResponse(protocols=['arduino', ''])
    await ws.prepare(request)
    
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
                        print(f"✅ ESP: {did}")
                        await ws.send_json({"type": "registered"})
                
                elif t == "sensor_data":
                    sensor = data.get("data", {})
                    upd = json.dumps({"type": "update", "data": sensor})
                    dead = set()
                    for c in web_clients.copy():
                        try: await c.send_str(upd)
                        except: dead.add(c)
                    web_clients.difference_update(dead)
                
                elif t == "arm":
                    print("🔒 ARM command")
                    if esp_ws:
                        await esp_ws.send_str(json.dumps({"command": "arm"}))
                        print("✅ ARM sent")
                    else:
                        print("❌ No ESP connected!")
                
                elif t == "disarm":
                    print("🔓 DISARM command")
                    if esp_ws:
                        await esp_ws.send_str(json.dumps({"command": "disarm"}))
                        print("✅ DISARM sent")
                    else:
                        print("❌ No ESP connected!")
                
                elif t == "set_threshold":
                    v = int(data.get("value", 200))
                    print(f"📏 Threshold: {v}cm")
                    if esp_ws:
                        await esp_ws.send_str(json.dumps({"command": "set_threshold", "value": v}))
                        print(f"✅ Threshold sent: {v}")
                    else:
                        print("❌ No ESP connected!")
                
                elif t == "web_client":
                    web_clients.add(ws)
                    print(f"🌐 Web client")
    
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if esp_ws == ws:
            esp_ws = None
            print("❌ ESP disconnected")
        web_clients.discard(ws)
    
    return ws

if __name__ == '__main__':
    app = web.Application()
    app.router.add_get('/', http_handler)
    app.router.add_get('/ws', ws_handler)
    port = int(os.environ.get('PORT', 8000))
    print(f"Server on port {port}")
    web.run_app(app, port=port)
