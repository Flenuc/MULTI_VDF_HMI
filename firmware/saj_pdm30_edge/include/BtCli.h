/**
 * @file BtCli.h
 * @brief Bluetooth Classic SPP line collector → same CLI as USB serial.
 *
 * Only compiled when BOARD_HAS_BT_CLASSIC (ESP32 original).
 * Appears to the host as a wireless serial port (SPP / RFCOMM).
 */
#pragma once

#include "Config.h"

#if BOARD_HAS_BT_CLASSIC

#include "CliEngine.h"
#include "ResponseChannel.h"
#include "BtIo.h"

#include <BluetoothSerial.h>

#ifndef BT_DEVICE_NAME
#define BT_DEVICE_NAME "SAJ-PDM30-Edge"
#endif

class BtCli {
public:
  explicit BtCli(CliEngine &cli) : _cli(cli) {}

  void begin() {
    s_self = this;
    g_btIo.hasClient = &BtCli::s_hasClient;
    g_btIo.println = &BtCli::s_println;
    g_btIo.print = &BtCli::s_print;
    // Master=false → we are SPP slave (PC connects to us)
    if (!_bt.begin(BT_DEVICE_NAME)) {
      Serial.println(F("[bt] SerialBT begin FAILED"));
      _ok = false;
      return;
    }
    _ok = true;
    Serial.printf("[bt] SPP ready  name=%s  (pair + RFCOMM)\n", BT_DEVICE_NAME);
  }

  BluetoothSerial &port() { return _bt; }
  bool ready() const { return _ok; }
  // hasClient() is non-const in BluetoothSerial API
  bool hasClient() { return _ok && _bt.hasClient(); }

  void poll() {
    if (!_ok) return;
    while (_bt.available()) {
      char c = (char)_bt.read();
      if (c == '\r') continue;
      if (c == '\n') {
        _line[_lineLen] = '\0';
        if (_lineLen > 0) {
          // Same reply channel as USB so NetworkService mirrors both
          _cli.handleLine(Channel::usb(), _line);
        }
        _lineLen = 0;
      } else if (_lineLen + 1 < CLI_LINE_MAX) {
        if (c >= 32 && c < 127) _line[_lineLen++] = c;
      } else {
        _lineLen = 0;
      }
    }
  }

  void println(const char *text) {
    if (!_ok || !text || !_bt.hasClient()) return;
    _bt.println(text);
  }

  void print(const char *text) {
    if (!_ok || !text || !_bt.hasClient()) return;
    _bt.print(text);
  }

private:
  static BtCli *s_self;
  static bool s_hasClient() { return s_self && s_self->hasClient(); }
  static void s_println(const char *t) {
    if (s_self) s_self->println(t);
  }
  static void s_print(const char *t) {
    if (s_self) s_self->print(t);
  }

  CliEngine &_cli;
  BluetoothSerial _bt;
  bool   _ok = false;
  char   _line[CLI_LINE_MAX];
  size_t _lineLen = 0;
};

#endif  // BOARD_HAS_BT_CLASSIC
