#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <DNSServer.h>
#include <WebSocketsClient.h>
#include <WiFiClientSecure.h>

// ============ НАСТРОЙКИ ============
const char* AP_SSID = "ESP12_Setup";
const char* AP_PASSWORD = "";

const char* WS_SERVER = "iot-bullshit.onrender.com";
const int WS_PORT = 443;
const char* WS_PATH = "/ws";
const char* DEVICE_ID = "esp12_security";
// ==================================

const int TRIG_PIN = D1;
const int ECHO_PIN = D2;
const int LED_PIN = D0;  // Встроенный светодиод

bool securityMode = false;
bool alarmActive = false;
int distanceThreshold = 200;
const unsigned long ALARM_COOLDOWN = 5000;

ESP8266WebServer webServer(80);
DNSServer dnsServer;
WebSocketsClient webSocket;

float distance = 0;
int alarmCount = 0;
unsigned long lastAlarmTime = 0;
bool wasClose = false;
bool isClose = false;
bool wsConnected = false;
bool configured = false;
unsigned long lastSend = 0;
unsigned long lastMeasure = 0;
unsigned long lastLedToggle = 0;
bool ledState = false;

String userSSID = "";
String userPass = "";

const char authPage[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Security Setup</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: Arial, sans-serif;
            background: linear-gradient(135deg, #1a1a2e, #16213e);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .container {
            background: #0f3460;
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.5);
            max-width: 400px;
            width: 100%;
            color: white;
        }
        h2 { text-align: center; margin-bottom: 10px; }
        .subtitle { text-align: center; color: #a0a0a0; margin-bottom: 30px; font-size: 14px; }
        .form-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 8px; color: #ccc; font-weight: bold; font-size: 14px; }
        input {
            width: 100%;
            padding: 12px;
            border: 2px solid #1a1a2e;
            border-radius: 10px;
            font-size: 16px;
            background: #16213e;
            color: white;
        }
        input:focus { outline: none; border-color: #e94560; }
        button {
            width: 100%;
            padding: 14px;
            background: linear-gradient(135deg, #e94560, #c23152);
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
        }
        button:hover { opacity: 0.9; }
        .status { margin-top: 20px; padding: 15px; border-radius: 10px; text-align: center; display: none; }
        .success { background: rgba(0,255,0,0.2); color: #00ff00; display: block; }
        .error { background: rgba(255,0,0,0.2); color: #ff4444; display: block; }
    </style>
</head>
<body>
    <div class="container">
        <h2>Security Setup</h2>
        <p class="subtitle">Connect to your WiFi</p>
        <form id="wifiForm">
            <div class="form-group">
                <label>WiFi Name (SSID):</label>
                <input type="text" id="ssid" required placeholder="WiFi name">
            </div>
            <div class="form-group">
                <label>WiFi Password:</label>
                <input type="password" id="password" placeholder="Password">
            </div>
            <button type="submit">Connect</button>
        </form>
        <div id="status" class="status"></div>
    </div>
    <script>
        document.getElementById('wifiForm').addEventListener('submit', function(e) {
            e.preventDefault();
            const status = document.getElementById('status');
            status.className = 'status';
            status.style.display = 'block';
            status.innerHTML = 'Connecting...';
            
            fetch('/connect?ssid=' + encodeURIComponent(document.getElementById('ssid').value) + 
                  '&pass=' + encodeURIComponent(document.getElementById('password').value))
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        status.className = 'status success';
                        status.innerHTML = 'Connected! System ready.';
                    } else {
                        status.className = 'status error';
                        status.innerHTML = 'Failed!';
                    }
                });
        });
    </script>
</body>
</html>
)rawliteral";

float measureDistance() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  
  long duration = pulseIn(ECHO_PIN, HIGH, 25000);
  if (duration == 0) return 999;
  return (duration * 0.343) / 2.0;
}

String makeJSON(float dist, int threshold, bool security, bool alarm, int alarmCnt, unsigned long uptime, int rssi) {
  String json = "{\"type\":\"sensor_data\",\"deviceId\":\"";
  json += DEVICE_ID;
  json += "\",\"data\":{";
  json += "\"distance\":" + String(dist, 1);
  json += ",\"threshold\":" + String(threshold);
  json += ",\"security_mode\":" + String(security ? "true" : "false");
  json += ",\"alarm\":" + String(alarm ? "true" : "false");
  json += ",\"alarm_count\":" + String(alarmCnt);
  json += ",\"uptime\":" + String(uptime);
  json += ",\"rssi\":" + String(rssi);
  json += "}}";
  return json;
}

String makeRegisterJSON() {
  return "{\"type\":\"register\",\"deviceId\":\"" + String(DEVICE_ID) + "\"}";
}

void webSocketEvent(WStype_t type, uint8_t * payload, size_t length) {
  switch(type) {
    case WStype_DISCONNECTED:
      Serial.println("[WS] DISCONNECTED");
      wsConnected = false;
      break;
      
    case WStype_CONNECTED:
      Serial.println("[WS] CONNECTED!");
      wsConnected = true;
      webSocket.sendTXT(makeRegisterJSON().c_str());
      Serial.println("[WS] Registered: " + String(DEVICE_ID));
      break;
      
    case WStype_TEXT: {
      String msg = String((char*)payload);
      Serial.print("[WS] RECEIVED: ");
      Serial.println(msg);
      
      // Проверяем command
      if (msg.indexOf("\"command\"") >= 0) {
        // ARM
        if (msg.indexOf("\"arm\"") >= 0) {
          securityMode = true;
          alarmActive = false;
          digitalWrite(LED_PIN, LOW);
          Serial.println("🔒 ARMED!");
        }
        // DISARM
        else if (msg.indexOf("\"disarm\"") >= 0) {
          securityMode = false;
          alarmActive = false;
          digitalWrite(LED_PIN, LOW);
          Serial.println("🔓 DISARMED!");
        }
        // SET THRESHOLD
        else if (msg.indexOf("set_threshold") >= 0) {
          int valIdx = msg.indexOf("\"value\":");
          if (valIdx >= 0) {
            String valStr = msg.substring(valIdx + 8);
            valStr.replace("}", "");
            valStr.replace("\"", "");
            valStr.replace(" ", "");
            valStr.trim();
            int newVal = valStr.toInt();
            if (newVal >= 50 && newVal <= 500) {
              distanceThreshold = newVal;
              Serial.print("📏 Threshold: ");
              Serial.print(distanceThreshold);
              Serial.println("cm");
            }
          }
        }
        // RESET ALARM COUNT
        else if (msg.indexOf("reset_alarm") >= 0) {
          alarmCount = 0;
          Serial.println("🔄 Alarm count reset");
        }
      }
      break;
    }
      
    case WStype_ERROR:
      Serial.println("[WS] ERROR");
      wsConnected = false;
      break;
  }
}

void startAPMode() {
  Serial.println("\n=== SECURITY SETUP ===");
  
  WiFi.mode(WIFI_AP);
  WiFi.softAP(AP_SSID, AP_PASSWORD);
  
  Serial.println("AP: " + String(AP_SSID));
  Serial.println("IP: " + WiFi.softAPIP().toString());
  
  dnsServer.start(53, "*", WiFi.softAPIP());
  
  webServer.on("/", []() {
    webServer.send(200, "text/html", authPage);
  });
  
  webServer.on("/connect", []() {
    userSSID = webServer.arg("ssid");
    userPass = webServer.arg("pass");
    
    Serial.println("\nWiFi: " + userSSID);
    
    WiFi.mode(WIFI_STA);
    WiFi.begin(userSSID.c_str(), userPass.c_str());
    
    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 30) {
      delay(500);
      Serial.print(".");
      attempts++;
    }
    
    if (WiFi.status() == WL_CONNECTED) {
      Serial.println("\nWiFi OK: " + WiFi.localIP().toString());
      configured = true;
      webServer.send(200, "application/json", "{\"success\":true,\"ip\":\"" + WiFi.localIP().toString() + "\"}");
      
      WiFiClientSecure* secureClient = new WiFiClientSecure;
      secureClient->setInsecure();
      webSocket.beginSSL(WS_SERVER, WS_PORT, WS_PATH);
      webSocket.onEvent(webSocketEvent);
      webSocket.setReconnectInterval(5000);
      
      delay(5000);
      WiFi.softAPdisconnect(true);
    } else {
      Serial.println("\nWiFi FAILED!");
      webServer.send(200, "application/json", "{\"success\":false}");
      WiFi.mode(WIFI_AP);
      WiFi.softAP(AP_SSID, AP_PASSWORD);
    }
  });
  
  webServer.onNotFound([]() {
    webServer.sendHeader("Location", "/", true);
    webServer.send(302, "text/plain", "");
  });
  
  webServer.begin();
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  
  Serial.println("\n=== SECURITY SYSTEM ===");
  Serial.println("Device: " + String(DEVICE_ID));
  
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(TRIG_PIN, LOW);
  digitalWrite(LED_PIN, LOW);
  
  startAPMode();
}

void loop() {
  if (configured && WiFi.status() == WL_CONNECTED) {
    webSocket.loop();
    
    // Измеряем дистанцию
    if (millis() - lastMeasure >= 100) {
      lastMeasure = millis();
      distance = measureDistance();
      
      isClose = (distance > 0 && distance <= distanceThreshold);
      
      // Тревога если режим охраны и обнаружено движение
      if (securityMode && isClose && !wasClose) {
        if (millis() - lastAlarmTime > ALARM_COOLDOWN) {
          alarmActive = true;
          alarmCount++;
          lastAlarmTime = millis();
          Serial.print("🚨 ALARM #");
          Serial.print(alarmCount);
          Serial.print("! Dist: ");
          Serial.print(distance, 1);
          Serial.println("cm");
        }
      }
      
      // Сброс тревоги если объект ушел
      if (alarmActive && !isClose && millis() - lastAlarmTime > 2000) {
        alarmActive = false;
        digitalWrite(LED_PIN, LOW);
      }
      
      wasClose = isClose;
    }
    
    // Мигаем светодиодом при тревоге
    if (alarmActive) {
      if (millis() - lastLedToggle >= 200) {
        lastLedToggle = millis();
        ledState = !ledState;
        digitalWrite(LED_PIN, ledState);
      }
    }
    
    // Отправка данных
    if (wsConnected && millis() - lastSend >= 300) {
      lastSend = millis();
      String json = makeJSON(distance, distanceThreshold, securityMode, alarmActive, alarmCount, millis()/1000, WiFi.RSSI());
      webSocket.sendTXT(json.c_str());
    }
    
    // Переподключение
    if (!wsConnected && millis() - lastSend > 10000) {
      webSocket.disconnect();
      delay(500);
      WiFiClientSecure* secureClient = new WiFiClientSecure;
      secureClient->setInsecure();
      webSocket.beginSSL(WS_SERVER, WS_PORT, WS_PATH);
      webSocket.onEvent(webSocketEvent);
      webSocket.setReconnectInterval(5000);
      lastSend = millis();
    }
    
    delay(10);
    return;
  }
  
  dnsServer.processNextRequest();
  webServer.handleClient();
}
