/**
 * @file NetworkService.h
 * @brief Wi-Fi AP + STA profiles, mDNS, MQTT bridge (no WebSocket).
 *
 * CLI surface (via CliEngine):
 *   wifi status | wifi set <ssid> <pass>
 *   wifi profile list|save|use|delete ...
 *   mqtt status | mqtt set <host> [port] | mqtt user <u> <p> | mqtt enable|disable
 */
#pragma once

#include "Config.h"
#include "ResponseChannel.h"
#include "WifiProfiles.h"

class CliEngine;

class NetworkService : public IReplySink {
public:
  void begin(CliEngine &cli);
  void poll();

  void reply(const Channel &ch, const char *text) override;
  bool isRemoteAlive() const override;

  void broadcastText(const char *text);

  // Wi-Fi
  void wifiStatus(const Channel &ch);
  bool wifiSetQuick(const char *ssid, const char *pass, const Channel &ch);
  void wifiReconnect(const Channel &ch);
  void wifiProfileList(const Channel &ch);
  bool wifiProfileSave(const char *name, const char *ssid, const char *pass, const Channel &ch);
  bool wifiProfileUse(const char *name, const Channel &ch);
  bool wifiProfileDelete(const char *name, const Channel &ch);

  // MQTT
  void mqttStatus(const Channel &ch);
  bool mqttSetHost(const char *host, uint16_t port, const Channel &ch);
  bool mqttSetAuth(const char *user, const char *pass, const Channel &ch);
  void mqttSetEnabled(bool en, const Channel &ch);

  bool staConnected() const;
  bool mqttConnected() const;

  /** After `id set`: refresh MQTT topics + mDNS hostname (reconnect MQTT). */
  void applyDeviceIdentity();

  const char *topicCmd() const { return _topicCmd; }
  const char *mqttClientId() const { return _mqttClientId; }

private:
  enum class StaPhase : uint8_t {
    Idle = 0,
    Connecting,
    Connected,
    Failed,
    WaitingRetry,
  };

  CliEngine *_cli = nullptr;
  bool _started = false;

  WifiProfiles _profiles;
  char _staSsid[WIFI_SSID_MAX + 1] = {};
  char _staPass[WIFI_PASS_MAX + 1] = {};
  bool _hasStaCreds = false;
  StaPhase _staPhase = StaPhase::Idle;
  uint32_t _staPhaseAt = 0;
  bool _mdnsOk = false;
  uint32_t _lastMdnsRefresh = 0;

  // MQTT config
  char _mqttHost[MQTT_HOST_MAX + 1] = {};
  uint16_t _mqttPort = MQTT_DEFAULT_PORT;
  char _mqttUser[MQTT_USER_MAX + 1] = {};
  char _mqttPass[MQTT_PASS_MAX + 1] = {};
  char _mqttClientId[MQTT_ID_MAX + 1] = {};
  char _topicCmd[80] = {};
  char _topicRsp[80] = {};
  char _topicTel[80] = {};
  char _topicStat[80] = {};
  bool _mqttEnabled = true;
  bool _mqttConnected = false;
  uint32_t _mqttNextTry = 0;

  void loadMqttConfig();
  void saveMqttConfig() const;
  void buildTopics();

  void setupWifi();
#if BOARD_HAS_ETHERNET
  void setupEthernet();
#endif
  void applyActiveProfile();
  void startStaConnect();
  void pollSta();
  void setupMdns();
  void refreshMdns();

  void pollMqtt();
  void mqttEnsureConnected();
  void mqttPublish(const char *topic, const char *payload, bool retained = false);

  void replyf(const Channel &ch, const char *fmt, ...);
};
