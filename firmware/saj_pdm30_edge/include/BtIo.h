/**
 * @file BtIo.h
 * @brief Shared mirror hooks for Classic SPP and BLE NUS serial bridges.
 */
#pragma once

#include <stddef.h>

struct BtIoFns {
  bool (*hasClient)();
  void (*println)(const char *text);
  void (*print)(const char *text);
  /** Re-assert connectable + general discoverable (Classic / host stacks). */
  void (*refreshDiscoverable)();
  /** Fill one-line human status into buf (NUL-terminated). */
  void (*fillStatus)(char *buf, size_t n);
  /** Delete all bonded peers (field re-pair). */
  void (*clearBonds)();
};

// Zero-initialized → no-ops until BtCli / BleUartCli::begin()
extern BtIoFns g_btIo;

inline void btMirrorLine(const char *text) {
  if (text && g_btIo.hasClient && g_btIo.hasClient() && g_btIo.println) {
    g_btIo.println(text);
  }
}

inline void btMirrorPrompt() {
  if (g_btIo.hasClient && g_btIo.hasClient() && g_btIo.print) {
    g_btIo.print("> ");
  }
}

inline void btRefreshDiscoverable() {
  if (g_btIo.refreshDiscoverable) {
    g_btIo.refreshDiscoverable();
  }
}
