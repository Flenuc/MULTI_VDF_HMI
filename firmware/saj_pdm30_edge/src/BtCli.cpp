#include "Config.h"

#if BOARD_HAS_BT_CLASSIC

#include "BtCli.h"

#include <esp_bt.h>
#include <esp_bt_main.h>
#include <esp_gap_bt_api.h>
#include <string.h>
#include <stdio.h>

#if __has_include(<esp_coexist.h>)
#include <esp_coexist.h>
#define HAS_ESP_COEX 1
#else
#define HAS_ESP_COEX 0
#endif

BtCli *BtCli::s_self = nullptr;

bool BtCli::s_hasClient() { return s_self && s_self->hasClient(); }
void BtCli::s_println(const char *t) {
  if (s_self) s_self->println(t);
}
void BtCli::s_print(const char *t) {
  if (s_self) s_self->print(t);
}
void BtCli::s_refresh() {
  if (s_self) s_self->refreshDiscoverable();
}
void BtCli::s_fillStatus(char *buf, size_t n) {
  if (s_self) s_self->fillStatus(buf, n);
  else if (buf && n) {
    buf[0] = '\0';
  }
}
void BtCli::s_clearBonds() {
  if (s_self) s_self->clearBonds();
}

bool BtCli::hasClient() {
  return _ok && _bt.hasClient();
}

void BtCli::println(const char *text) {
  if (!_ok || !text || !_bt.hasClient()) return;
  _bt.println(text);
}

void BtCli::print(const char *text) {
  if (!_ok || !text || !_bt.hasClient()) return;
  _bt.print(text);
}

void BtCli::refreshDiscoverable() {
  if (!_ok) return;
  // Re-assert after Wi-Fi SoftAP/STA channel hops (coexistence).
#if defined(ESP_IDF_VERSION_MAJOR) && (ESP_IDF_VERSION_MAJOR >= 4)
  esp_bt_gap_set_scan_mode(ESP_BT_CONNECTABLE, ESP_BT_GENERAL_DISCOVERABLE);
#else
  esp_bt_gap_set_scan_mode(ESP_BT_SCAN_MODE_CONNECTABLE_DISCOVERABLE);
#endif
  _lastAdvMs = millis();
}

void BtCli::clearBonds() {
  if (!_ok) return;
  _bt.deleteAllBondedDevices();
  Serial.println(F("[bt] all bonds cleared"));
  refreshDiscoverable();
}

void BtCli::fillStatus(char *buf, size_t n) {
  if (!buf || n == 0) return;
  if (!_ok) {
    snprintf(buf, n, "bt ready=0");
    return;
  }
  String mac = _bt.getBtAddressString();
  snprintf(buf, n,
           "bt ready=1 name=%s mac=%s client=%d pin=%s bonds=%d",
           BT_DEVICE_NAME,
           mac.c_str(),
           _bt.hasClient() ? 1 : 0,
           BT_PIN_CODE,
           _bt.getNumberOfBondedDevices());
}

void BtCli::begin() {
  s_self = this;
  g_btIo.hasClient = &BtCli::s_hasClient;
  g_btIo.println = &BtCli::s_println;
  g_btIo.print = &BtCli::s_print;
  g_btIo.refreshDiscoverable = &BtCli::s_refresh;
  g_btIo.fillStatus = &BtCli::s_fillStatus;
  g_btIo.clearBonds = &BtCli::s_clearBonds;

  // --- Pairing: Just Works (IO_CAP_NONE) must be set BEFORE begin() ---
  // Hosts like BlueZ often request numeric confirmation; without auto-accept
  // the link stays Connected but not Paired and RFCOMM fails (ENOMEM / timeout).
  _bt.enableSSP(false, false);

  _bt.onConfirmRequest([](uint32_t num_val) {
    Serial.printf("[bt] SSP confirm %06lu — auto-accept\n",
                  (unsigned long)num_val);
    if (s_self) {
      s_self->_bt.confirmReply(true);
    }
  });

  _bt.onKeyRequest([]() {
    // CAP_IN not used; if a host still asks, reply with fixed PIN as passkey.
    Serial.println(F("[bt] SSP key request — respond with fixed PIN"));
    if (s_self) {
      uint32_t pk = (uint32_t)strtoul(BT_PIN_CODE, nullptr, 10);
      s_self->_bt.respondPasskey(pk);
    }
  });

  _bt.onAuthComplete([](bool ok) {
    Serial.printf("[bt] auth %s\n", ok ? "OK" : "FAIL");
    if (s_self) {
      if (ok) {
        Serial.println(F("[bt] paired — RFCOMM/SPP should work now"));
      }
      s_self->refreshDiscoverable();
    }
  });

  // Slave SPP, Classic-only (disableBLE=true frees BLE RAM, more stable SPP)
  if (!_bt.begin(String(BT_DEVICE_NAME), /*isMaster=*/false, /*disableBLE=*/true)) {
    Serial.println(F("[bt] SerialBT begin FAILED"));
    _ok = false;
    return;
  }
  _ok = true;

  // Legacy PIN pairing (Windows/old phones). Non-fatal if stack rejects.
  if (!_bt.setPin(BT_PIN_CODE, (uint8_t)strlen(BT_PIN_CODE))) {
    Serial.println(F("[bt] setPin failed (non-fatal)"));
  }

  refreshDiscoverable();

#if HAS_ESP_COEX
  // Prefer BT scheduling slightly under SoftAP+STA load (SPP latency).
  esp_coex_preference_set(ESP_COEX_PREFER_BT);
#endif

  Serial.printf("[bt] SPP ready  name=%s  mac=%s  pin=%s\n",
                BT_DEVICE_NAME,
                _bt.getBtAddressString().c_str(),
                BT_PIN_CODE);
  Serial.println(F("[bt] pair: Just Works / PIN; then RFCOMM ch1 as serial"));
}

void BtCli::poll() {
  if (!_ok) return;

  const bool client = _bt.hasClient();
  if (client != _hadClient) {
    _hadClient = client;
    if (client) {
      Serial.println(F("[bt] SPP client connected"));
      // Banner so host tools know the link is live
      _bt.println("SAJ-PDM30-Edge SPP ready");
      _bt.print("> ");
    } else {
      Serial.println(F("[bt] SPP client disconnected"));
      refreshDiscoverable();
    }
  }

  // Wi-Fi SoftAP/STA can make us non-discoverable; refresh while idle.
  const uint32_t now = millis();
  if (!client && (now - _lastAdvMs) >= 15000UL) {
    refreshDiscoverable();
  }

  while (_bt.available()) {
    char c = (char)_bt.read();
    if (c == '\r') continue;
    if (c == '\n') {
      _line[_lineLen] = '\0';
      if (_lineLen > 0) {
        // Same reply channel as USB so NetworkService mirrors Serial + BT
        _cli.handleLine(Channel::usb(), _line);
      }
      _lineLen = 0;
    } else if (_lineLen + 1 < CLI_LINE_MAX) {
      if (c >= 32 && c < 127) {
        _line[_lineLen++] = c;
      }
    } else {
      _lineLen = 0;
    }
  }
}

#endif  // BOARD_HAS_BT_CLASSIC
