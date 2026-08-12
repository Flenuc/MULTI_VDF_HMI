/**
 * @file BtCli.h
 * @brief Bluetooth Classic SPP line collector → same CLI as USB serial.
 *
 * Only compiled when BOARD_HAS_BT_CLASSIC (ESP32 original).
 * Appears to the host as a wireless serial port (SPP / RFCOMM).
 *
 * Pairing strategy (field-friendly):
 *   - Classic-only controller mode (BLE RAM released)
 *   - SSP Just Works (IO_CAP_NONE) + auto-accept confirm callbacks
 *   - Fixed legacy PIN (BT_PIN_CODE) for old stacks
 *   - Periodic re-advertise when no client (Wi-Fi coexist)
 */
#pragma once

#include "Config.h"

#if BOARD_HAS_BT_CLASSIC

#include "CliEngine.h"
#include "ResponseChannel.h"
#include "BtIo.h"

#include <BluetoothSerial.h>
#include <stddef.h>
#include <stdint.h>

#ifndef BT_DEVICE_NAME
#define BT_DEVICE_NAME "SAJ-PDM30-Edge"
#endif

class BtCli {
public:
  explicit BtCli(CliEngine &cli) : _cli(cli) {}

  void begin();
  void poll();

  BluetoothSerial &port() { return _bt; }
  bool ready() const { return _ok; }
  bool hasClient();

  void println(const char *text);
  void print(const char *text);

  void refreshDiscoverable();
  void fillStatus(char *buf, size_t n);
  void clearBonds();

private:
  static BtCli *s_self;
  static bool s_hasClient();
  static void s_println(const char *t);
  static void s_print(const char *t);
  static void s_refresh();
  static void s_fillStatus(char *buf, size_t n);
  static void s_clearBonds();

  CliEngine &_cli;
  BluetoothSerial _bt;
  bool   _ok = false;
  bool   _hadClient = false;
  uint32_t _lastAdvMs = 0;
  char   _line[CLI_LINE_MAX];
  size_t _lineLen = 0;
};

#endif  // BOARD_HAS_BT_CLASSIC
