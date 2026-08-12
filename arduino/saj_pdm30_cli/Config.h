/**
 * @file Config.h
 * @brief Hardware and link configuration — SAJ PDM-30 master (ESP32 + SN75176B)
 *
 * Verified on-site (discovery):
 *   - Slave ID = 1, baud 9600 8N1
 *   - P0-ii → holding 0x00ii, P1-ii → holding 0x01ii  (MAP_GROUP_DIRECT)
 */

#pragma once

#include <Arduino.h>

// ---------------------------------------------------------------------------
// USB debug console
// ---------------------------------------------------------------------------
static const uint32_t USB_BAUD = 115200;

// ---------------------------------------------------------------------------
// RS485 (SN75176B) on UART2
// ---------------------------------------------------------------------------
static const int PIN_RS485_TX  = 14;   // DI
static const int PIN_RS485_RX  = 25;   // RO
static const int PIN_RS485_DE  = 27;   // DE+RE: HIGH=TX, LOW=RX
static const int PIN_ACT_LED   = 2;    // activity LED

static const uint32_t RS485_BAUD   = 9600;
static const uint32_t RS485_CONFIG = SERIAL_8N1;

// ---------------------------------------------------------------------------
// Modbus RTU
// ---------------------------------------------------------------------------
static const uint8_t  MB_SLAVE_ID          = 1;
static const uint32_t MB_RESPONSE_TIMEOUT_MS = 500;
static const uint32_t MB_INTERFRAME_MS     = 5;    // silence between frames (≈3.5 char times @9600)
static const uint32_t MB_POST_TX_GUARD_MS  = 2;    // extra settle after calculated TX end before DE→RX

// 11 bit-times per byte (start + 8 data + stop, no parity) at 9600
static inline uint32_t mbFrameDurationMs(size_t nbytes) {
  // ceil( nbytes * 11 * 1000 / 9600 ) + 1
  return (uint32_t)((nbytes * 11UL * 1000UL + RS485_BAUD - 1) / RS485_BAUD) + 1UL;
}

// ---------------------------------------------------------------------------
// Parameter map (discovered)
// ---------------------------------------------------------------------------
static const uint8_t PARAM_INDEX_MAX = 47;

/** Pn.ii → Modbus holding register address */
static inline uint16_t paramAddress(uint8_t group, uint8_t index) {
  return (uint16_t)(((uint16_t)group << 8) | index);
}

// Special telemetry (PDH30 family — confirmed alive on this unit)
static const uint16_t REG_STATUS     = 0x3000;
static const uint16_t REG_RUN_FREQ   = 0x1001;  // 0.01 Hz
static const uint16_t REG_SET_PRESS  = 0x100F;  // 0.1 bar
static const uint16_t REG_FB_PRESS   = 0x1010;  // 0.1 bar

// CLI
static const size_t CLI_LINE_MAX = 80;
