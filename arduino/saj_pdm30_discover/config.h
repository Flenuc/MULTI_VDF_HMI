/**
 * Hardware / link configuration for ESP32 ↔ RS485 ↔ SAJ PDM-30
 *
 * Adjust pins to match your RS485 transceiver (MAX485 / SP3485 / etc.).
 * Default PDM-30 link settings from manual:
 *   Slave ID  = P1-35 = 1
 *   Baud      = P1-36 = 1 → 9600
 *   Format    = P1-37 = 0 → 8N1
 */

#pragma once

// ----- Serial to RS485 transceiver (ESP32 + SN75176B) -----
//   TX GPIO14 → DI
//   RX GPIO25 → RO
//   DE/RE unidos → GPIO27
//   LED actividad → GPIO2
#define RS485_RX_PIN        25
#define RS485_TX_PIN        14
#define RS485_DE_PIN        27    // DE+RE tied; HIGH=TX, LOW=RX
#define RS485_SERIAL        Serial2
#define ACTIVITY_LED_PIN    2

// Set true if your module has no DE pin (auto-direction)
#define RS485_AUTO_DIRECTION  false

// ----- Link parameters (must match VFD) -----
#define VFD_SLAVE_ID        1
#define VFD_BAUD            9600
#define VFD_CONFIG          SERIAL_8N1

// ----- Timing -----
#define MB_RESPONSE_TIMEOUT_MS  500
#define MB_INTER_FRAME_MS       30
#define MB_POST_TX_US           100  // settle after last TX bit before releasing DE (SN75176B)

// ----- USB debug console -----
#define DEBUG_BAUD          115200

// ----- After discovery: set the scheme that matched your VFD -----
// 0 = MAP_GROUP_DIRECT, 1 = MAP_F_STYLE (PDH30-like), 2 = MAP_GROUP_100
#define PARAM_MAP_SCHEME    0
