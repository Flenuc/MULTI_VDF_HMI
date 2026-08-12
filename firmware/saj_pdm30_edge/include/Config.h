/**
 * @file Config.h
 * @brief Hardware, Wi-Fi profiles, MQTT and telemetry configuration
 *
 * Board selection (PlatformIO build_flags):
 *   -DBOARD_ESP32DEV                 (default)
 *   -DBOARD_GUITION_JC_ESP32P4_M3
 */
#pragma once

#include <Arduino.h>
#include <stdint.h>

// ---------------------------------------------------------------------------
// Board variant
// ---------------------------------------------------------------------------
#if defined(BOARD_GUITION_JC_ESP32P4_M3)
  #include "boards/board_guition_jc_esp32p4_m3.h"
#else
  #include "boards/board_esp32dev.h"
#endif

#ifndef BOARD_HAS_BT_CLASSIC
#define BOARD_HAS_BT_CLASSIC 0
#endif
#ifndef BOARD_HAS_BT_BLE_NUS
#define BOARD_HAS_BT_BLE_NUS 0
#endif

// Bluetooth Classic SPP (ESP32-DevKit)
#ifndef BT_DEVICE_NAME
#define BT_DEVICE_NAME "SAJ-PDM30-Edge"
#endif
// Fixed PIN for legacy hosts; SSP Just Works is preferred when supported.
#ifndef BT_PIN_CODE
#define BT_PIN_CODE "1234"
#endif

// ---------------------------------------------------------------------------
// USB debug CLI
// ---------------------------------------------------------------------------
static const uint32_t USB_BAUD = 115200;

// ---------------------------------------------------------------------------
// RS485 (pins from board_*.h)
// ---------------------------------------------------------------------------
static const uint32_t RS485_BAUD   = 9600;
static const uint32_t RS485_CONFIG = SERIAL_8N1;

// ---------------------------------------------------------------------------
// Modbus RTU
// ---------------------------------------------------------------------------
static const uint8_t  MB_SLAVE_ID            = 1;
// 500 ms is tight when SoftAP+MQTT (C6 hosted) share the CPU with RS485 polling.
// 1200 ms still snappy for field use and avoids false Timeouts under Wi‑Fi load.
static const uint32_t MB_RESPONSE_TIMEOUT_MS = 1200;
static const uint32_t MB_INTERFRAME_MS       = 5;
static const uint32_t MB_POST_TX_GUARD_MS    = 2;

static inline uint32_t mbFrameDurationMs(size_t nbytes) {
  return (uint32_t)((nbytes * 11UL * 1000UL + RS485_BAUD - 1) / RS485_BAUD) + 1UL;
}

static const uint8_t PARAM_INDEX_MAX = 47;

static inline uint16_t paramAddress(uint8_t group, uint8_t index) {
  return (uint16_t)(((uint16_t)group << 8) | index);
}

static const uint16_t REG_FREQ_SET_PCT = 0x1000;
static const uint16_t REG_RUN_FREQ     = 0x1001;
// Manual (PDH): 0x1002 bus 0.1V, 0x1003 Vout 1V. Field PDM-30 often has
// DC bus (~310 V) at 0x1003 with 0.1 V scale; 0x1002 may mirror frequency.
static const uint16_t REG_BUS_VOLTAGE  = 0x1002;
static const uint16_t REG_OUT_VOLTAGE  = 0x1003;
static const uint16_t REG_OUT_CURRENT  = 0x1004;
// 0x100F "setting pressure" on this unit does NOT match P0-00 (shows ~642 bar).
// Use P0-00 (0x0000) for consigna; 0x1010 feedback 0.1 bar for transducer.
static const uint16_t REG_SET_PRESS    = 0x100F;
static const uint16_t REG_FB_PRESS     = 0x1010;
static const uint16_t REG_P0_00_SET_P  = 0x0000;
static const uint16_t REG_CTRL_CMD     = 0x2000;
static const uint16_t REG_VFD_STATUS   = 0x3000;

static const uint16_t CMD_FWD_RUN    = 0x0001;
static const uint16_t CMD_DECEL_STOP = 0x0006;
static const uint16_t CMD_FREE_STOP  = 0x0005;
static const uint16_t CMD_FAULT_RST  = 0x0007;

// ---------------------------------------------------------------------------
// Wi-Fi AP (field) + STA profiles (NVS)
// ---------------------------------------------------------------------------
#ifndef WIFI_AP_SSID
#define WIFI_AP_SSID     "SAJ_Diag_Tool"
#endif
#ifndef WIFI_AP_PASS
#define WIFI_AP_PASS     "sajpdm30"
#endif
#ifndef WIFI_AP_CHANNEL
#define WIFI_AP_CHANNEL  1
#endif

#define MDNS_HOSTNAME "saj-pdm30"

static const uint32_t WIFI_STA_CONNECT_TIMEOUT_MS = 35000;
static const uint32_t WIFI_STA_RETRY_MS           = 15000;
static const uint32_t WIFI_MDNS_REFRESH_MS        = 10000;

#define WIFI_NVS_NAMESPACE   "wifi"
#define WIFI_NVS_KEY_ACTIVE  "active"     // profile name in use
#define WIFI_NVS_KEY_COUNT   "nprof"
#define WIFI_MAX_PROFILES    6
#define WIFI_PROFILE_NAME_MAX 20
#define WIFI_SSID_MAX        32
#define WIFI_PASS_MAX        64

// ---------------------------------------------------------------------------
// MQTT (preferred multiplatform link — no WebSocket)
// ---------------------------------------------------------------------------
// Topics (device id = MDNS hostname by default):
//   saj/pdm30/<id>/cmd        app → device  (CLI text)
//   saj/pdm30/<id>/rsp        device → app  (CLI replies)
//   saj/pdm30/<id>/telemetry  device → app  (JSON ~1 Hz)
//   saj/pdm30/<id>/status     device → app  (online/offline LWT)
#define MQTT_NVS_NAMESPACE   "mqtt"
#define MQTT_TOPIC_ROOT      "saj/pdm30"
#define MQTT_DEFAULT_PORT    1883
#define MQTT_HOST_MAX        64
#define MQTT_USER_MAX        32
#define MQTT_PASS_MAX        32
#define MQTT_ID_MAX          24

static const uint32_t MQTT_RECONNECT_MS = 5000;
static const uint16_t MQTT_KEEPALIVE_S  = 30;

// Compile-time default broker (empty = must configure via CLI / NVS)
#ifndef MQTT_HOST_DEFAULT
#define MQTT_HOST_DEFAULT ""
#endif

// ---------------------------------------------------------------------------
// Telemetry
// ---------------------------------------------------------------------------
static const uint32_t TELEMETRY_PERIOD_MS = 1000;

// ---------------------------------------------------------------------------
// CLI / buffers
// ---------------------------------------------------------------------------
static const size_t CLI_LINE_MAX       = 160;
static const size_t CLI_REPLY_MAX      = 320;
static const size_t DUMP_BATCH_MAX     = 900;
static const size_t JSON_TELEMETRY_MAX = 220;
static const uint32_t DUMP_CHUNK_GAP_MS = 60;
