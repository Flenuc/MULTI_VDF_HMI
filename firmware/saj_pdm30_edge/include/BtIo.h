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
