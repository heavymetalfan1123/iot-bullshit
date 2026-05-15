#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <DNSServer.h>
#include <WebSocketsClient.h>
#include <WiFiClientSecure.h>

// ============ НАСТРОЙКИ ТОЧКИ ДОСТУПА ============
const char* AP_SSID = "ESP12_Setup";
const char* AP_PASSWORD = "";  // Без пароля

// Настройки сервера (куда подключаться после авторизации)
const char* WS_SERVER = "iot-bullshit.onrender.com";
const int WS_PORT = 443;
const char* WS_PATH = "/ws";
const char* DEVICE_ID = "esp12_sensor_1";
// ==================================================

// Датчик HC-SR04
const int TRIG_PIN = D1;
const int ECHO_PIN = D2;
int distanceThreshold = 100;
const unsigned long DEBOUNCE_TIME = 1000;

ESP8266WebServer webServer(80);
DNSServer dnsServer;
WebSocketsClient webSocket;

// Переменные состояния
bool configured = false;
float distance = 0;
int touchCount = 0;
bool wasClose = false;
bool isClose = false;
unsigned long lastTouchTime = 0;
bool wsConnected = false;
unsigned long lastSend = 0;
unsigned long lastMeasure = 0;

// Временные настройки WiFi
String userSSID = "";
String userPass = "";

// HTML страница для ввода WiFi
const char authPage[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>ESP12 Setup</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: Arial, sans-serif;
            background: linear-gradient(135deg, #667eea, #764ba2);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .container {
            background: white;
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            max-width: 400px;
            width: 100%;
        }
        h2 { text-align: center; color: #333; margin-bottom: 10px; }
        .subtitle { text-align: center; color: #666; margin-bottom: 30px; font-size: 14px; }
        .form-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 8px; color: #555; font-weight: bold; font-size: 14px; }
        input {
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 10px;
            font-size: 16px;
            background: #f8f9fa;
        }
        input:focus { outline: none; border-color: #667eea; background: white; }
        button {
            width: 100%;
            padding: 14px;
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            margin-top: 10px;
        }
        button:hover { opacity: 0.9; transform: translateY(-2px); }
        .status { margin-top: 20px; padding: 15px; border-radius: 10px; text-align: center; display: none; }
        .success { background: #d4edda; color: #155724; display: block; }
        .error { background: #f8d7da; color: #721c24; display: block; }
        .info-text { text-align: center; color: #888; font-size: 13px; margin-top: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <h2>ESP12 Setup</h2>
        <p class="subtitle">Enter your WiFi credentials</p>
        
        <form id="wifiForm">
            <div class="form-group">
                <label>WiFi Name (SSID):</label>
                <input type="text" id="ssid" required placeholder="Your WiFi name">
            </div>
            <div class="form-group">
                <label>WiFi Password:</label>
                <input type="password" id="password" placeholder="WiFi password">
            </div>
            <button type="submit">Connect</button>
        </form>
        
        <div id="status" class="status"></div>
        <div class="info-text">ESP will connect and start counting touches</div>
    </div>
    
    <script>
        document.getElementById('wifiForm').addEventListener('submit', function(e) {
            e.preventDefault();
            const status = document.getElementById('status');
            status.className = 'status';
            status.style.display = 'block';
            status.innerHTML = 'Connecting...';
            
            const ssid = document.getElementById('ssid').value;
            const password = document.getElementById('password').value;
            
            fetch('/connect?ssid=' + encodeURIComponent(ssid) + '&pass=' + encodeURIComponent(password))
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        status.className = 'status success';
                        status.innerHTML = 'Connected! IP: ' + data.ip + '<br>ESP is now working.';
                        setTimeout(() => {
                            document.body.innerHTML = '<div class="container" style="text-align:center;"><h2>Connected!</h2><p>ESP is counting touches.</p></div>';
                        }, 2000);
                    } else {
                        status.className = 'status error';
                        status.innerHTML = 'Connection failed! Check password.';
                    }
                });
        });
    </script>
</body>
</html>
)rawliteral";

// Измерение расстояния
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

// JSON данные
String makeJSON(int touches, float dist, int threshold, unsigned long uptime, int rssi) {
  String json = "{\"type\":\"sensor_data\",\"deviceId\":\"";
  json += DEVICE_ID;
  json += "\",\"data\":{";
  json += "\"touch_count\":" + String(touches);
  json += ",\"distance\":" + String(dist, 1);
  json += ",\"threshold\":" + String(threshold);
  json += ",\"uptime\":" + String(uptime);
  json += ",\"rssi\":" + String(rssi);
  json += "}}";
  return json;
}

String makeRegisterJSON() {
  return "{\"type\":\"register\",\"deviceId\":\"" + String(DEVICE_ID) + "\"}";
}

// Обработчик WebSocket
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
      
      // Команда RESET
      if (msg.indexOf("reset") >= 0) {
        touchCount = 0;
        lastTouchTime = 0;
        wasClose = false;
        Serial.println("🔄🔄🔄 COUNTER RESET! 🔄🔄🔄");
        
        String confirm = "{\"type\":\"reset_confirm\",\"deviceId\":\"" + String(DEVICE_ID) + "\"}";
        webSocket.sendTXT(confirm.c_str());
        Serial.println("✅ Reset confirmed");
      }
      
      // Команда изменения порога
      if (msg.indexOf("set_threshold") >= 0) {
        int valIdx = msg.indexOf("\"value\":");
        if (valIdx >= 0) {
          String valStr = msg.substring(valIdx + 8);
          valStr.replace("}", "");
          valStr.replace("\"", "");
          valStr.replace(" ", "");
          valStr.trim();
          
          int newVal = valStr.toInt();
          if (newVal >= 10 && newVal <= 500) {
            distanceThreshold = newVal;
            Serial.print("📏 NEW THRESHOLD: ");
            Serial.print(distanceThreshold);
            Serial.println("mm");
          }
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
  Serial.println("\n=== ACCESS POINT MODE ===");
  
  WiFi.mode(WIFI_AP);
  WiFi.softAP(AP_SSID, AP_PASSWORD);
  
  Serial.println("AP SSID: " + String(AP_SSID));
  Serial.println("No password");
  Serial.println("AP IP: " + WiFi.softAPIP().toString());
  
  dnsServer.start(53, "*", WiFi.softAPIP());
  
  webServer.on("/", []() {
    webServer.send(200, "text/html", authPage);
  });
  
  webServer.on("/connect", []() {
    userSSID = webServer.arg("ssid");
    userPass = webServer.arg("pass");
    
    Serial.println("\n=== WiFi Configuration ===");
    Serial.println("SSID: " + userSSID);
    
    WiFi.mode(WIFI_STA);
    WiFi.begin(userSSID.c_str(), userPass.c_str());
    
    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 30) {
      delay(500);
      Serial.print(".");
      attempts++;
    }
    
    if (WiFi.status() == WL_CONNECTED) {
      Serial.println("\nWiFi CONNECTED!");
      Serial.println("IP: " + WiFi.localIP().toString());
      
      configured = true;
      String ip = WiFi.localIP().toString();
      webServer.send(200, "application/json", "{\"success\":true,\"ip\":\"" + ip + "\"}");
      
      // Подключаем WebSocket к серверу
      Serial.print("Connecting to server: ");
      Serial.println(WS_SERVER);
      
      WiFiClientSecure* secureClient = new WiFiClientSecure;
      secureClient->setInsecure();
      webSocket.beginSSL(WS_SERVER, WS_PORT, WS_PATH);
      webSocket.onEvent(webSocketEvent);
      webSocket.setReconnectInterval(5000);
      
      // Ждем немного и отключаем AP
      delay(5000);
      WiFi.softAPdisconnect(true);
      Serial.println("AP disabled. Normal mode.\n");
    } else {
      Serial.println("\nWiFi FAILED!");
      webServer.send(200, "application/json", "{\"success\":false}");
      
      // Возвращаем AP
      WiFi.disconnect();
      WiFi.mode(WIFI_AP);
      WiFi.softAP(AP_SSID, AP_PASSWORD);
    }
  });
  
  webServer.onNotFound([]() {
    webServer.sendHeader("Location", "/", true);
    webServer.send(302, "text/plain", "");
  });
  
  webServer.begin();
  Serial.println("HTTP server started");
  Serial.println("Waiting for configuration...\n");
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  
  Serial.println("\n=== ESP12 TOUCH COUNTER ===");
  Serial.println("Device: " + String(DEVICE_ID));
  Serial.println("Default Threshold: " + String(distanceThreshold) + "mm");
  
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  digitalWrite(TRIG_PIN, LOW);
  
  // Всегда запускаем точку доступа для настройки
  startAPMode();
}

void loop() {
  // Если настроен и подключен к WiFi - работаем
  if (configured && WiFi.status() == WL_CONNECTED) {
    webSocket.loop();
    
    // Измеряем дистанцию
    if (millis() - lastMeasure >= 100) {
      lastMeasure = millis();
      distance = measureDistance();
      
      isClose = (distance > 0 && distance <= distanceThreshold);
      
      if (isClose && !wasClose) {
        if (millis() - lastTouchTime > DEBOUNCE_TIME) {
          touchCount++;
          lastTouchTime = millis();
          Serial.print("👆 TOUCH #");
          Serial.print(touchCount);
          Serial.print(" | Dist: ");
          Serial.print(distance, 1);
          Serial.print("mm | Threshold: ");
          Serial.print(distanceThreshold);
          Serial.println("mm");
        }
      }
      
      wasClose = isClose;
    }
    
    // Отправка данных
    if (wsConnected && millis() - lastSend >= 200) {
      lastSend = millis();
      String json = makeJSON(touchCount, distance, distanceThreshold, millis()/1000, WiFi.RSSI());
      webSocket.sendTXT(json.c_str());
    }
    
    // Переподключение WebSocket
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
  
  // Режим настройки
  dnsServer.processNextRequest();
  webServer.handleClient();
}
