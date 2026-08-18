/**
 * SAJ PDM-30 Edge IIoT — main cooperative loop
 *
 *   USB Serial CLI  ↔  CliEngine  ↔  Modbus RTU (RS485)
 *   Bluetooth SPP   ↔  wireless serial (ESP32 classic)
 *   Bluetooth LE NUS↔  wireless serial (Guition C6 hosted)
 *   MQTT  cmd/rsp/telemetry  ↕
 */

#include <Arduino.h>
#include <WiFi.h>

#include "Config.h"
#include "DriveProfile.h"
#include "HwRs485.h"
#include "ModbusRtuMaster.h"
#include "SajPdm30.h"
#include "CliEngine.h"
#include "NetworkService.h"
#include "TelemetryService.h"
#include "UsbCli.h"
#if BOARD_HAS_BT_CLASSIC
#include "BtCli.h"
#endif
#if BOARD_HAS_BT_BLE_NUS
#include "BleUartCli.h"
#endif

static HwRs485           g_bus;
static ModbusRtuMaster   g_mb(g_bus);
static SajPdm30          g_vfd(g_mb);
static NetworkService    g_net;
static CliEngine         g_cli(g_vfd, g_mb, g_net);
static TelemetryService  g_tel(g_vfd, g_mb, g_net);
static UsbCli            g_usb(g_cli);
#if BOARD_HAS_BT_CLASSIC
static BtCli             g_bt(g_cli);
#endif
#if BOARD_HAS_BT_BLE_NUS
static BleUartCli        g_ble(g_cli);
#endif

void setup() {
  g_bus.begin();
  g_mb.begin();
  g_driveProfile.begin();  // NVS: last profile set (default saj.pdm30)
  g_usb.begin();

  g_cli.setTelemetry(&g_tel);
  g_cli.setNetwork(&g_net);
  g_tel.begin();
  // Wi-Fi / hosted stack first (helps C6 BLE + SoftAP coexist)
  g_net.begin(g_cli);

#if BOARD_HAS_BT_CLASSIC
  g_bt.begin();
#endif
#if BOARD_HAS_BT_BLE_NUS
  // After hosted Wi-Fi is up so VHCI/controller is available on P4+C6
  g_ble.begin();
#endif

  Serial.println();
  Serial.println(F("=== SAJ PDM-30 Edge (MQTT) ==="));
  Serial.printf("board=%s\n", BOARD_NAME);
  Serial.printf("drive_profile=%s\n", g_driveProfile.idStr());
  Serial.printf("RS485 TX=%d RX=%d DE=%d auto=%d | slave=%u @ %lu\n",
                PIN_RS485_TX, PIN_RS485_RX, PIN_RS485_DE, (int)RS485_AUTO_DIRECTION,
                (unsigned)MB_SLAVE_ID, (unsigned long)RS485_BAUD);
#if BOARD_HAS_WIFI
  Serial.printf("AP SSID=%s pass=%s  IP=%s\n",
                WIFI_AP_SSID, WIFI_AP_PASS,
                WiFi.softAPIP().toString().c_str());
#endif
#if BOARD_HAS_ETHERNET
  Serial.println(F("Ethernet IP101 enabled (wait for link/DHCP)"));
#endif
#if BOARD_HAS_BT_CLASSIC
  Serial.println(F("Bluetooth SPP: SAJ-PDM30-Edge (Classic; Just Works / PIN 1234)"));
  Serial.println(F("  CLI: bt status | bt advertise | bt clearbonds"));
#endif
#if BOARD_HAS_BT_BLE_NUS
  Serial.println(F("Bluetooth LE NUS: SAJ-PDM30-Edge (Nordic UART)"));
#endif
#if !BOARD_HAS_BT_CLASSIC && !BOARD_HAS_BT_BLE_NUS
  Serial.println(F("Bluetooth: not enabled on this board build"));
#endif
  Serial.printf("mDNS: %s.local\n", MDNS_HOSTNAME);
  Serial.println(F("wifi profile list|save|use   mqtt set <broker> [port]"));
  Serial.println(F("MQTT: saj/pdm30/saj-pdm30/{cmd,rsp,telemetry,status}"));
  Serial.print(F("> "));
}

void loop() {
  g_bus.poll();
  g_mb.poll();
  g_usb.poll();
#if BOARD_HAS_BT_CLASSIC
  g_bt.poll();
#endif
#if BOARD_HAS_BT_BLE_NUS
  g_ble.poll();
#endif
  g_cli.poll();
  g_mb.poll();
  if (!g_mb.isBusy()) {
    g_net.poll();
  }
  g_mb.poll();
  g_tel.poll(!g_cli.isBusy() && !g_mb.isBusy());
}
