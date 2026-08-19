/**
 * @file BleUartCli.h
 * @brief Nordic UART Service (NUS) over BLE — wireless serial for Guition (C6).
 *
 * Service  6E400001-B5A3-F393-E0A9-E50E24DCCA9E
 * RX char  6E400002-...  (central → peripheral write)
 * TX char  6E400003-...  (peripheral → central notify)
 *
 * Only when BOARD_HAS_BT_BLE_NUS.
 */
#pragma once

#include "Config.h"

#if BOARD_HAS_BT_BLE_NUS

#include "CliEngine.h"
#include "DeviceIdentity.h"
#include "ResponseChannel.h"
#include "BtIo.h"

#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

#include <string.h>

#ifndef BT_DEVICE_NAME
#define BT_DEVICE_NAME "SAJ-PDM30-Edge"
#endif

// Nordic UART Service UUIDs
static const char *NUS_SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E";
static const char *NUS_RX_UUID      = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E";  // write
static const char *NUS_TX_UUID      = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E";  // notify

// RX ring from BLE callback → drained in poll() (main loop)
static const size_t BLE_RX_RING = 1024;
static const size_t BLE_TX_CHUNK = 180;  // after MTU negotiation; fallback still works

class BleUartCli {
public:
  explicit BleUartCli(CliEngine &cli) : _cli(cli) {}

  void begin() {
    g_btIo.hasClient = &BleUartCli::s_hasClient;
    g_btIo.println = &BleUartCli::s_println;
    g_btIo.print = &BleUartCli::s_print;
    s_self = this;

    const char *btName = g_deviceId.btName();
    BLEDevice::init(btName);
    _server = BLEDevice::createServer();
    _server->setCallbacks(new ServerCbs(this));

    BLEService *svc = _server->createService(NUS_SERVICE_UUID);

    _tx = svc->createCharacteristic(
        NUS_TX_UUID,
        BLECharacteristic::PROPERTY_NOTIFY | BLECharacteristic::PROPERTY_READ);
    _tx->addDescriptor(new BLE2902());

    _rx = svc->createCharacteristic(
        NUS_RX_UUID,
        BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR);
    _rx->setCallbacks(new RxCbs(this));

    svc->start();

    BLEAdvertising *adv = BLEDevice::getAdvertising();
    adv->addServiceUUID(NUS_SERVICE_UUID);
    adv->setScanResponse(true);
    // Help legacy Android scanners
    adv->setMinPreferred(0x06);
    adv->setMaxPreferred(0x12);
    BLEDevice::startAdvertising();

    _ok = true;
    Serial.printf("[ble] NUS ready  name=%s  (Nordic UART Service)\n", btName);
  }

  bool ready() const { return _ok; }
  bool hasClient() const { return _ok && _connected; }

  void poll() {
    if (!_ok) return;
    // Drain ring → line parser (same as USB)
    for (;;) {
      int c = ringPop();
      if (c < 0) break;
      char ch = (char)c;
      if (ch == '\r') continue;
      if (ch == '\n') {
        _line[_lineLen] = '\0';
        if (_lineLen > 0) {
          _cli.handleLine(Channel::usb(), _line);
        }
        _lineLen = 0;
      } else if (_lineLen + 1 < CLI_LINE_MAX) {
        if (ch >= 32 && ch < 127) _line[_lineLen++] = ch;
      } else {
        _lineLen = 0;
      }
    }
  }

  void println(const char *text) {
    if (!text) return;
    notifyRaw(text, strlen(text));
    notifyRaw("\n", 1);
  }

  void print(const char *text) {
    if (!text) return;
    notifyRaw(text, strlen(text));
  }

private:
  class ServerCbs : public BLEServerCallbacks {
  public:
    explicit ServerCbs(BleUartCli *o) : _o(o) {}
    void onConnect(BLEServer *s) override {
      (void)s;
      _o->_connected = true;
      Serial.println(F("[ble] client connected"));
    }
    void onDisconnect(BLEServer *s) override {
      (void)s;
      _o->_connected = false;
      Serial.println(F("[ble] client disconnected — re-advertise"));
      delay(100);
      BLEDevice::startAdvertising();
    }
  private:
    BleUartCli *_o;
  };

  class RxCbs : public BLECharacteristicCallbacks {
  public:
    explicit RxCbs(BleUartCli *o) : _o(o) {}
    void onWrite(BLECharacteristic *c) override {
      // Arduino-esp32 3.x: getValue() returns String or std::string
      String v = c->getValue();
      for (size_t i = 0; i < v.length(); i++) {
        _o->ringPush((uint8_t)v[i]);
      }
    }
  private:
    BleUartCli *_o;
  };

  void ringPush(uint8_t b) {
    size_t next = (_rxHead + 1) % BLE_RX_RING;
    if (next == _rxTail) return;  // drop on overflow
    _rxRing[_rxHead] = b;
    _rxHead = next;
  }

  int ringPop() {
    if (_rxTail == _rxHead) return -1;
    uint8_t b = _rxRing[_rxTail];
    _rxTail = (_rxTail + 1) % BLE_RX_RING;
    return (int)b;
  }

  void notifyRaw(const char *data, size_t len) {
    if (!_ok || !_connected || !_tx || !data || len == 0) return;
    size_t off = 0;
    while (off < len) {
      size_t n = len - off;
      if (n > BLE_TX_CHUNK) n = BLE_TX_CHUNK;
      _tx->setValue((uint8_t *)(data + off), n);
      _tx->notify();
      off += n;
      // small yield so the stack can flush
      delay(2);
    }
  }

  static BleUartCli *s_self;
  static bool s_hasClient() { return s_self && s_self->hasClient(); }
  static void s_println(const char *t) {
    if (s_self) s_self->println(t);
  }
  static void s_print(const char *t) {
    if (s_self) s_self->print(t);
  }

  CliEngine &_cli;
  BLEServer *_server = nullptr;
  BLECharacteristic *_tx = nullptr;
  BLECharacteristic *_rx = nullptr;
  bool _ok = false;
  volatile bool _connected = false;

  uint8_t _rxRing[BLE_RX_RING];
  volatile size_t _rxHead = 0;
  volatile size_t _rxTail = 0;

  char _line[CLI_LINE_MAX];
  size_t _lineLen = 0;
};

// storage for static members — in header with inline for single TU include from main only
// Defined in BleUartCli.cpp

#endif  // BOARD_HAS_BT_BLE_NUS
