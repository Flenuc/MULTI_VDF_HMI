#include "NetworkService.h"
#include "CliEngine.h"
#include "Config.h"
#include "BtIo.h"

#include <WiFi.h>
#include <ESPmDNS.h>
#include <Preferences.h>
#include <PubSubClient.h>
#include <WiFiClient.h>
#if BOARD_HAS_ETHERNET
#include <ETH.h>
#endif

#include <stdarg.h>
#include <stdio.h>
#include <string.h>

static WiFiClient g_wifiClient;
static PubSubClient g_mqtt(g_wifiClient);
static NetworkService *g_self = nullptr;
static CliEngine *g_cliPtr = nullptr;
#if BOARD_HAS_ETHERNET
static bool g_ethUp = false;
#endif

// PubSubClient callback — static trampoline
static void mqttCallback(char *topic, byte *payload, unsigned int length) {
  (void)topic;
  if (!g_cliPtr || !payload || length == 0) return;
  char line[CLI_LINE_MAX];
  unsigned int n = length < (CLI_LINE_MAX - 1) ? length : (CLI_LINE_MAX - 1);
  memcpy(line, payload, n);
  line[n] = '\0';
  // strip CR/LF
  for (unsigned int i = 0; i < n; i++) {
    if (line[i] == '\r' || line[i] == '\n') {
      line[i] = '\0';
      break;
    }
  }
  if (line[0]) {
    g_cliPtr->handleLine(Channel::mqtt(), line);
  }
}

void NetworkService::begin(CliEngine &cli) {
  _cli = &cli;
  g_self = this;
  g_cliPtr = &cli;

  _profiles.begin();
  loadMqttConfig();
  buildTopics();

#if BOARD_HAS_ETHERNET
  setupEthernet();
#endif
  setupWifi();
  setupMdns();

  g_mqtt.setCallback(mqttCallback);
  g_mqtt.setBufferSize(1024);
  g_mqtt.setKeepAlive(MQTT_KEEPALIVE_S);

  _started = true;
}

void NetworkService::loadMqttConfig() {
  Preferences prefs;
  _mqttHost[0] = '\0';
  _mqttPort = MQTT_DEFAULT_PORT;
  _mqttUser[0] = '\0';
  _mqttPass[0] = '\0';
  _mqttEnabled = true;

  if (prefs.begin(MQTT_NVS_NAMESPACE, true)) {
    prefs.getString("host", _mqttHost, sizeof(_mqttHost));
    _mqttPort = (uint16_t)prefs.getUInt("port", MQTT_DEFAULT_PORT);
    prefs.getString("user", _mqttUser, sizeof(_mqttUser));
    prefs.getString("pass", _mqttPass, sizeof(_mqttPass));
    _mqttEnabled = prefs.getBool("en", true);
    prefs.end();
  }
  if (_mqttHost[0] == '\0' && MQTT_HOST_DEFAULT[0] != '\0') {
    strncpy(_mqttHost, MQTT_HOST_DEFAULT, MQTT_HOST_MAX);
  }
  // client id from chip
  uint64_t mac = ESP.getEfuseMac();
  snprintf(_mqttClientId, sizeof(_mqttClientId), "saj-%04X",
           (unsigned)((mac >> 32) & 0xFFFF));
}

void NetworkService::saveMqttConfig() const {
  Preferences prefs;
  if (!prefs.begin(MQTT_NVS_NAMESPACE, false)) return;
  prefs.putString("host", _mqttHost);
  prefs.putUInt("port", _mqttPort);
  prefs.putString("user", _mqttUser);
  prefs.putString("pass", _mqttPass);
  prefs.putBool("en", _mqttEnabled);
  prefs.end();
}

void NetworkService::buildTopics() {
  // saj/pdm30/saj-pdm30/cmd|rsp|telemetry|status
  snprintf(_topicCmd, sizeof(_topicCmd), "%s/%s/cmd", MQTT_TOPIC_ROOT, MDNS_HOSTNAME);
  snprintf(_topicRsp, sizeof(_topicRsp), "%s/%s/rsp", MQTT_TOPIC_ROOT, MDNS_HOSTNAME);
  snprintf(_topicTel, sizeof(_topicTel), "%s/%s/telemetry", MQTT_TOPIC_ROOT, MDNS_HOSTNAME);
  snprintf(_topicStat, sizeof(_topicStat), "%s/%s/status", MQTT_TOPIC_ROOT, MDNS_HOSTNAME);
}

void NetworkService::applyActiveProfile() {
  WifiProfile p;
  if (_profiles.getActive(p)) {
    strncpy(_staSsid, p.ssid, WIFI_SSID_MAX);
    _staSsid[WIFI_SSID_MAX] = '\0';
    strncpy(_staPass, p.pass, WIFI_PASS_MAX);
    _staPass[WIFI_PASS_MAX] = '\0';
    _hasStaCreds = (_staSsid[0] != '\0');
  } else {
    _hasStaCreds = false;
    _staSsid[0] = '\0';
    _staPass[0] = '\0';
  }
}

#if BOARD_HAS_ETHERNET
static void onEthEvent(arduino_event_id_t event, arduino_event_info_t info) {
  (void)info;
  switch (event) {
    case ARDUINO_EVENT_ETH_START:
      ETH.setHostname(MDNS_HOSTNAME);
      break;
    case ARDUINO_EVENT_ETH_CONNECTED:
      Serial.println(F("[eth] link up"));
      break;
    case ARDUINO_EVENT_ETH_GOT_IP:
      g_ethUp = true;
      Serial.printf("[eth] IP=%s\n", ETH.localIP().toString().c_str());
      if (g_self) {
        // allow MDNS + MQTT to attach
      }
      break;
    case ARDUINO_EVENT_ETH_DISCONNECTED:
    case ARDUINO_EVENT_ETH_STOP:
      g_ethUp = false;
      Serial.println(F("[eth] link down"));
      break;
    default:
      break;
  }
}

void NetworkService::setupEthernet() {
  WiFi.onEvent(onEthEvent);
  // Guition P4 uses the same IP101 + RMII pins as ESP32-P4 Function EV board
  // (defaults in variants/esp32p4/pins_arduino.h → ETH.begin())
  bool ok = ETH.begin();
  Serial.printf("[eth] begin %s (MDC=%d MDIO=%d PWR=%d CLK=%d)\n",
                ok ? "OK" : "FAIL", PIN_ETH_MDC, PIN_ETH_MDIO, PIN_ETH_POWER, PIN_ETH_CLK);
}
#endif

void NetworkService::setupWifi() {
#if !BOARD_HAS_WIFI
  applyActiveProfile();
  _staPhase = StaPhase::Idle;
  Serial.println(F("[wifi] disabled on this board build"));
  return;
#else
  WiFi.mode(WIFI_AP_STA);
  WiFi.setHostname(MDNS_HOSTNAME);
  WiFi.setSleep(false);
  WiFi.persistent(false);
  WiFi.softAP(WIFI_AP_SSID, WIFI_AP_PASS, WIFI_AP_CHANNEL);

  applyActiveProfile();
  if (_hasStaCreds) startStaConnect();
  else _staPhase = StaPhase::Idle;
#endif
}

static int findStaChannel(const char *ssid) {
  if (!ssid || !ssid[0]) return -1;
  int n = WiFi.scanNetworks(false, true);
  int ch = -1;
  int best = -999;
  for (int i = 0; i < n; i++) {
    if (WiFi.SSID(i) == ssid) {
      int r = WiFi.RSSI(i);
      if (r > best) {
        best = r;
        ch = WiFi.channel(i);
      }
    }
  }
  WiFi.scanDelete();
  if (ch > 0) {
    Serial.printf("[wifi] scan hit ssid=%s ch=%d rssi=%d\n", ssid, ch, best);
  }
  return ch;
}

void NetworkService::startStaConnect() {
  if (!_hasStaCreds || !_staSsid[0]) {
    _staPhase = StaPhase::Idle;
    return;
  }
  WiFi.disconnect(false, false);
  int ch = findStaChannel(_staSsid);
  if (ch > 0) {
    WiFi.softAP(WIFI_AP_SSID, WIFI_AP_PASS, ch);
  }
  WiFi.begin(_staSsid, _staPass);
  _staPhase = StaPhase::Connecting;
  _staPhaseAt = millis();
  Serial.printf("[wifi] STA connecting \"%s\"…\n", _staSsid);
}

void NetworkService::pollSta() {
  const uint32_t now = millis();
  switch (_staPhase) {
    case StaPhase::Idle:
      break;
    case StaPhase::Connecting:
      if (WiFi.status() == WL_CONNECTED) {
        _staPhase = StaPhase::Connected;
        Serial.printf("[wifi] STA OK IP=%s RSSI=%d\n",
                      WiFi.localIP().toString().c_str(), WiFi.RSSI());
        refreshMdns();
        _mqttNextTry = 0;  // try MQTT ASAP
      } else if ((int32_t)(now - _staPhaseAt) >= (int32_t)WIFI_STA_CONNECT_TIMEOUT_MS) {
        _staPhase = StaPhase::Failed;
        _staPhaseAt = now;
        Serial.println(F("[wifi] STA timeout"));
        WiFi.disconnect(false, false);
      }
      break;
    case StaPhase::Connected:
      if (WiFi.status() != WL_CONNECTED) {
        Serial.println(F("[wifi] STA lost"));
        _staPhase = StaPhase::WaitingRetry;
        _staPhaseAt = now;
        _mqttConnected = false;
      } else if ((int32_t)(now - _lastMdnsRefresh) >= (int32_t)WIFI_MDNS_REFRESH_MS) {
        if (!_mdnsOk) refreshMdns();
        _lastMdnsRefresh = now;
      }
      break;
    case StaPhase::Failed:
    case StaPhase::WaitingRetry:
      if ((int32_t)(now - _staPhaseAt) >= (int32_t)WIFI_STA_RETRY_MS) {
        startStaConnect();
      }
      break;
  }
}

void NetworkService::setupMdns() { refreshMdns(); }

void NetworkService::refreshMdns() {
  MDNS.end();
  _mdnsOk = false;
  if (!MDNS.begin(MDNS_HOSTNAME)) {
    Serial.println(F("[mdns] fail"));
    return;
  }
  MDNS.addService("mqtt", "tcp", _mqttPort > 0 ? _mqttPort : MQTT_DEFAULT_PORT);
  _mdnsOk = true;
  _lastMdnsRefresh = millis();
  Serial.printf("[mdns] %s.local ok\n", MDNS_HOSTNAME);
}

static bool networkIpReady() {
  // STA linked to upstream AP
  if (WiFi.status() == WL_CONNECTED) return true;
  // SoftAP-only: device is 192.168.4.1 and can open TCP to associated stations
  // (e.g. PC on SAJ_Diag_Tool running Mosquitto). Without this, MQTT never
  // attempts connect when STA is not configured.
#if BOARD_HAS_WIFI
  wifi_mode_t mode = WiFi.getMode();
  if ((mode & WIFI_MODE_AP) && WiFi.softAPgetStationNum() >= 0) {
    // SoftAP interface has a valid IP once softAP() succeeded
    if (WiFi.softAPIP()[0] != 0) return true;
  }
#endif
#if BOARD_HAS_ETHERNET
  if (g_ethUp) return true;
#endif
  return false;
}

void NetworkService::pollMqtt() {
  if (!_mqttEnabled || _mqttHost[0] == '\0') return;
  if (!networkIpReady()) {
    _mqttConnected = false;
    return;
  }

  if (g_mqtt.connected()) {
    g_mqtt.loop();
    _mqttConnected = true;
    return;
  }

  _mqttConnected = false;
  const uint32_t now = millis();
  if ((int32_t)(now - _mqttNextTry) < 0) return;
  _mqttNextTry = now + MQTT_RECONNECT_MS;
  mqttEnsureConnected();
}

void NetworkService::mqttEnsureConnected() {
  g_mqtt.setServer(_mqttHost, _mqttPort);
  Serial.printf("[mqtt] connect %s:%u as %s…\n", _mqttHost, _mqttPort, _mqttClientId);

  bool ok;
  if (_mqttUser[0]) {
    ok = g_mqtt.connect(_mqttClientId, _mqttUser, _mqttPass,
                        _topicStat, 0, true, "offline");
  } else {
    ok = g_mqtt.connect(_mqttClientId, _topicStat, 0, true, "offline");
  }
  if (!ok) {
    Serial.printf("[mqtt] failed rc=%d\n", g_mqtt.state());
    return;
  }
  g_mqtt.subscribe(_topicCmd, 0);
  g_mqtt.publish(_topicStat, "online", true);
  _mqttConnected = true;
  Serial.printf("[mqtt] OK  cmd=%s  rsp=%s\n", _topicCmd, _topicRsp);
}

void NetworkService::mqttPublish(const char *topic, const char *payload, bool retained) {
  if (!g_mqtt.connected() || !topic || !payload) return;
  g_mqtt.publish(topic, payload, retained);
}

void NetworkService::poll() {
  if (!_started) return;
  pollSta();
  pollMqtt();
}

void NetworkService::replyf(const Channel &ch, const char *fmt, ...) {
  char buf[CLI_REPLY_MAX];
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(buf, sizeof(buf), fmt, ap);
  va_end(ap);
  reply(ch, buf);
}

void NetworkService::reply(const Channel &ch, const char *text) {
  if (!text) return;

  switch (ch.kind) {
    case ChannelKind::UsbSerial:
      Serial.println(text);
      btMirrorLine(text);  // Bluetooth SPP = wireless serial
      if (text[0] != '{') {
        Serial.print("> ");
        btMirrorPrompt();
      }
      break;

    case ChannelKind::Mqtt:
      // multi-line: publish each line separately for easy app parsing
      {
        const char *p = text;
        while (*p) {
          const char *nl = strchr(p, '\n');
          char line[CLI_REPLY_MAX];
          if (nl) {
            size_t n = (size_t)(nl - p);
            if (n >= sizeof(line)) n = sizeof(line) - 1;
            memcpy(line, p, n);
            line[n] = '\0';
            if (n && line[n - 1] == '\r') line[n - 1] = '\0';
            mqttPublish(_topicRsp, line, false);
            p = nl + 1;
          } else {
            mqttPublish(_topicRsp, p, false);
            break;
          }
        }
      }
      // also mirror to USB + BT for debug
      Serial.println(text);
      btMirrorLine(text);
      break;

    case ChannelKind::Broadcast:
      // telemetry JSON → MQTT telemetry topic + local serial mirrors
      if (text[0] == '{') {
        mqttPublish(_topicTel, text, false);
      } else {
        mqttPublish(_topicRsp, text, false);
      }
      Serial.println(text);
      btMirrorLine(text);
      break;
  }
}

bool NetworkService::isRemoteAlive() const {
  return _mqttConnected && g_mqtt.connected();
}

void NetworkService::broadcastText(const char *text) {
  reply(Channel::broadcast(), text);
}

bool NetworkService::staConnected() const {
  return WiFi.status() == WL_CONNECTED;
}

bool NetworkService::mqttConnected() const {
  return _mqttConnected && g_mqtt.connected();
}

// ----- Wi-Fi CLI helpers -----
void NetworkService::wifiStatus(const Channel &ch) {
  replyf(ch, "board=%s", BOARD_NAME);
#if BOARD_HAS_WIFI
  char apIp[20] = {}, staIp[20] = {};
  strncpy(apIp, WiFi.softAPIP().toString().c_str(), sizeof(apIp) - 1);
  if (WiFi.status() == WL_CONNECTED) {
    strncpy(staIp, WiFi.localIP().toString().c_str(), sizeof(staIp) - 1);
  }
  const char *phase = "idle";
  switch (_staPhase) {
    case StaPhase::Connecting:   phase = "connecting"; break;
    case StaPhase::Connected:    phase = "connected"; break;
    case StaPhase::Failed:       phase = "failed"; break;
    case StaPhase::WaitingRetry: phase = "retry-wait"; break;
    default: break;
  }
  replyf(ch, "wifi AP  ssid=%s  ip=%s", WIFI_AP_SSID, apIp);
  if (_hasStaCreds) {
    replyf(ch, "wifi STA profile=%s ssid=%s phase=%s ip=%s rssi=%d",
           _profiles.activeName()[0] ? _profiles.activeName() : "-",
           _staSsid, phase, staIp[0] ? staIp : "-",
           WiFi.status() == WL_CONNECTED ? WiFi.RSSI() : 0);
  } else {
    replyf(ch, "wifi STA not configured");
  }
#else
  replyf(ch, "wifi n/a on this board build (use ethernet or USB)");
#endif
#if BOARD_HAS_ETHERNET
  replyf(ch, "eth  %s  ip=%s",
         g_ethUp ? "UP" : "DOWN",
         g_ethUp ? ETH.localIP().toString().c_str() : "-");
#endif
  replyf(ch, "mdns %s.local (%s)", MDNS_HOSTNAME, _mdnsOk ? "ok" : "down");
  replyf(ch, "mqtt %s host=%s:%u %s",
         _mqttEnabled ? "enabled" : "disabled",
         _mqttHost[0] ? _mqttHost : "(none)",
         (unsigned)_mqttPort,
         mqttConnected() ? "CONNECTED" : "offline");
  if (_mqttHost[0]) {
    replyf(ch, "mqtt topics cmd=%s rsp=%s tel=%s", _topicCmd, _topicRsp, _topicTel);
  }
}

bool NetworkService::wifiSetQuick(const char *ssid, const char *pass, const Channel &ch) {
  // Save as profile "default" and activate
  if (!wifiProfileSave("default", ssid, pass, ch)) return false;
  return wifiProfileUse("default", ch);
}

void NetworkService::wifiReconnect(const Channel &ch) {
  applyActiveProfile();
  if (!_hasStaCreds) {
    replyf(ch, "ERR: no active profile");
    return;
  }
  replyf(ch, "wifi reconnecting to %s…", _staSsid);
  startStaConnect();
}

void NetworkService::wifiProfileList(const Channel &ch) {
  int n = _profiles.count();
  if (n == 0) {
    replyf(ch, "wifi profiles: (empty)");
    return;
  }
  replyf(ch, "wifi profiles (%d) active=%s", n,
         _profiles.activeName()[0] ? _profiles.activeName() : "-");
  for (int i = 0; i < n; i++) {
    WifiProfile p;
    if (!_profiles.get(i, p)) continue;
    const char *mark = (strcmp(p.name, _profiles.activeName()) == 0) ? "*" : " ";
    replyf(ch, "  %s %s  ssid=%s", mark, p.name, p.ssid);
  }
}

bool NetworkService::wifiProfileSave(const char *name, const char *ssid, const char *pass,
                                     const Channel &ch) {
  if (!_profiles.upsert(name, ssid, pass ? pass : "")) {
    replyf(ch, "ERR: cannot save profile (full or invalid)");
    return false;
  }
  _profiles.save();
  replyf(ch, "OK profile saved name=%s ssid=%s", name, ssid);
  return true;
}

bool NetworkService::wifiProfileUse(const char *name, const Channel &ch) {
  if (!_profiles.setActive(name)) {
    replyf(ch, "ERR: profile not found");
    return false;
  }
  _profiles.save();
  applyActiveProfile();
  replyf(ch, "OK using profile %s — connecting…", name);
  startStaConnect();
  return true;
}

bool NetworkService::wifiProfileDelete(const char *name, const Channel &ch) {
  if (!_profiles.remove(name)) {
    replyf(ch, "ERR: profile not found");
    return false;
  }
  _profiles.save();
  applyActiveProfile();
  replyf(ch, "OK profile deleted %s", name);
  return true;
}

void NetworkService::mqttStatus(const Channel &ch) {
  replyf(ch, "mqtt enabled=%d host=%s port=%u user=%s client=%s state=%s",
         _mqttEnabled ? 1 : 0,
         _mqttHost[0] ? _mqttHost : "-",
         (unsigned)_mqttPort,
         _mqttUser[0] ? _mqttUser : "-",
         _mqttClientId,
         mqttConnected() ? "connected" : "offline");
  replyf(ch, "mqtt cmd=%s", _topicCmd);
  replyf(ch, "mqtt rsp=%s", _topicRsp);
  replyf(ch, "mqtt tel=%s", _topicTel);
}

bool NetworkService::mqttSetHost(const char *host, uint16_t port, const Channel &ch) {
  if (!host || !host[0]) {
    replyf(ch, "ERR: empty host");
    return false;
  }
  strncpy(_mqttHost, host, MQTT_HOST_MAX);
  _mqttHost[MQTT_HOST_MAX] = '\0';
  if (port > 0) _mqttPort = port;
  saveMqttConfig();
  buildTopics();
  if (g_mqtt.connected()) g_mqtt.disconnect();
  _mqttNextTry = 0;
  replyf(ch, "OK mqtt host=%s port=%u", _mqttHost, (unsigned)_mqttPort);
  return true;
}

bool NetworkService::mqttSetAuth(const char *user, const char *pass, const Channel &ch) {
  if (!user) user = "";
  if (!pass) pass = "";
  strncpy(_mqttUser, user, MQTT_USER_MAX);
  _mqttUser[MQTT_USER_MAX] = '\0';
  strncpy(_mqttPass, pass, MQTT_PASS_MAX);
  _mqttPass[MQTT_PASS_MAX] = '\0';
  saveMqttConfig();
  replyf(ch, "OK mqtt auth user=%s", _mqttUser[0] ? _mqttUser : "(none)");
  return true;
}

void NetworkService::mqttSetEnabled(bool en, const Channel &ch) {
  _mqttEnabled = en;
  saveMqttConfig();
  if (!en && g_mqtt.connected()) g_mqtt.disconnect();
  _mqttNextTry = 0;
  replyf(ch, "OK mqtt %s", en ? "enabled" : "disabled");
}
