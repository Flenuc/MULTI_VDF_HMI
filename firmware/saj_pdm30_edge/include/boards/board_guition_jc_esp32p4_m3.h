/**
 * Guition JC-ESP32P4-M3-DEV
 *
 * SoC: ESP32-P4 (+ ESP32-C6 Wi-Fi/BT coprocessor via SDIO hosted)
 * Flash 16MB, PSRAM OPI
 * Onboard MAX485 (TX1=GPIO26, RX1=GPIO27) — DE/RE typically auto / EN net
 * 100M Ethernet IP101: MDC=31 MDIO=52 PWR=51 CLK=50
 * C6 hosted SDIO: RST=54 CMD=19 CLK=18 D0-3=14..17
 *
 * Pin sources:
 *  - Board IDF RS485 demo sdkconfig: TXD=26 RXD=27
 *  - Module schematic: GPIO26=TX1, GPIO27=RX1
 *  - ESPHome / cnx-software: Ethernet + C6 hosted pins
 */
#pragma once

#define BOARD_NAME              "Guition-JC-ESP32P4-M3-DEV"
#define BOARD_HAS_WIFI          1   /* via ESP32-C6 hosted (when stack available) */
#define BOARD_HAS_ETHERNET      1
#define BOARD_HAS_ONBOARD_RS485 1
// C6 radio is BLE-only (via hosted); Classic SPP not available
#define BOARD_HAS_BT_CLASSIC    0
// Nordic UART Service over BLE (wireless serial for Guition)
#define BOARD_HAS_BT_BLE_NUS    1

// Onboard MAX485 (UART1 / TX1-RX1)
#ifndef PIN_RS485_TX
#define PIN_RS485_TX   26
#endif
#ifndef PIN_RS485_RX
#define PIN_RS485_RX   27
#endif
// DE not exposed as discrete GPIO in public RS485 demos (half-duplex HW / auto).
// Set to a free GPIO if your revision wires EN to a pad; -1 = no DE toggle.
#ifndef PIN_RS485_DE
#define PIN_RS485_DE   (-1)
#endif
// No dedicated user LED mapped publicly; disable activity LED by default.
#ifndef PIN_ACT_LED
#define PIN_ACT_LED    (-1)
#endif

#define RS485_AUTO_DIRECTION  1
// Prefer Serial1 on P4 (UART1); Serial2 also OK if mapped
#define RS485_UART            Serial1

// Ethernet IP101GRI (matches Arduino esp32p4 pins_arduino.h defaults)
#define PIN_ETH_MDC    31
#define PIN_ETH_MDIO   52
#define PIN_ETH_POWER  51
#define PIN_ETH_CLK    50
// Do NOT redefine ETH_PHY_* here — pins_arduino.h already sets
// ETH_PHY_TYPE/ADDR/MDC/MDIO/POWER and ETH_CLK_MODE=EMAC_CLK_EXT_IN

// ESP32-C6 hosted (SDIO) — for future WiFi-through-hosted builds
#define PIN_C6_RESET   54
#define PIN_C6_SD_CMD  19
#define PIN_C6_SD_CLK  18
#define PIN_C6_SD_D0   14
#define PIN_C6_SD_D1   15
#define PIN_C6_SD_D2   16
#define PIN_C6_SD_D3   17
