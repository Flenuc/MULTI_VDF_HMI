/**
 * Classic ESP32 Dev Module + external SN75176B (original hardware).
 */
#pragma once

#define BOARD_NAME              "ESP32-DevKit"
#define BOARD_HAS_WIFI          1
#define BOARD_HAS_ETHERNET      0
#define BOARD_HAS_ONBOARD_RS485 0
// Classic Bluetooth SPP (BluetoothSerial) — not available on C3/C6/S3/P4
#define BOARD_HAS_BT_CLASSIC    1
#define BOARD_HAS_BT_BLE_NUS    0

// External SN75176B wiring (project default)
#ifndef PIN_RS485_TX
#define PIN_RS485_TX   14
#endif
#ifndef PIN_RS485_RX
#define PIN_RS485_RX   25
#endif
#ifndef PIN_RS485_DE
#define PIN_RS485_DE   27
#endif
#ifndef PIN_ACT_LED
#define PIN_ACT_LED    2
#endif

#define RS485_AUTO_DIRECTION  0
#define RS485_UART            Serial2
