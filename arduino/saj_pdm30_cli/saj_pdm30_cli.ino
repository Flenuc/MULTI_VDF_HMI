/**
 * @file saj_pdm30_cli.ino
 * @brief ESP32 master — SAJ PDM-30 VFD over RS485 (SN75176B) + USB CLI
 *
 * Architecture (modular headers in this sketch folder):
 *   Config.h          pins, baud, address map
 *   HwRs485.h         DE/RE + LED + UART2
 *   ModbusRtuMaster.h non-blocking RTU master (FC03/FC06)
 *   SajPdm30.h        parameter helpers / names
 *   Cli.h             USB command interpreter
 *
 * Loop is fully cooperative: no delay().
 *
 * Flash: Arduino IDE / arduino-cli, board "ESP32 Dev Module"
 * USB Serial: 115200
 */

#include "Config.h"
#include "HwRs485.h"
#include "ModbusRtuMaster.h"
#include "SajPdm30.h"
#include "Cli.h"

static HwRs485         g_bus;
static ModbusRtuMaster g_mb(g_bus);
static SajPdm30        g_vfd(g_mb);
static Cli             g_cli(g_vfd, g_mb);

void setup() {
  g_bus.begin();
  g_mb.begin();
  g_vfd.begin();
  g_cli.begin();
}

void loop() {
  g_bus.poll();   // LED timer
  g_mb.poll();    // Modbus state machine
  g_cli.poll();   // USB CLI + async jobs
}
