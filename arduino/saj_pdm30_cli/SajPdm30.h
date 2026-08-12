/**
 * @file SajPdm30.h
 * @brief High-level SAJ PDM-30 parameter access (async over ModbusRtuMaster)
 */

#pragma once

#include "ModbusRtuMaster.h"
#include "Config.h"

class SajPdm30 {
public:
  explicit SajPdm30(ModbusRtuMaster &mb) : _mb(mb) {}

  void begin() {}

  uint8_t slaveId() const { return _slave; }
  void setSlaveId(uint8_t id) { _slave = id; }

  bool requestReadParam(uint8_t group, uint8_t index) {
    if (group > 1 || index > PARAM_INDEX_MAX) return false;
    return _mb.readHolding(_slave, paramAddress(group, index), 1);
  }

  bool requestWriteParam(uint8_t group, uint8_t index, uint16_t raw) {
    if (group > 1 || index > PARAM_INDEX_MAX) return false;
    return _mb.writeSingle(_slave, paramAddress(group, index), raw);
  }

  bool requestReadHolding(uint16_t addr, uint8_t qty = 1) {
    return _mb.readHolding(_slave, addr, qty);
  }

  bool requestWriteHolding(uint16_t addr, uint16_t value) {
    return _mb.writeSingle(_slave, addr, value);
  }

  bool requestDumpChunk(uint8_t group, uint8_t startIndex, uint8_t count) {
    if (group > 1 || startIndex > PARAM_INDEX_MAX) return false;
    if (count == 0 || count > 12) return false;
    if ((uint16_t)startIndex + count - 1 > PARAM_INDEX_MAX) return false;
    return _mb.readHolding(_slave, paramAddress(group, startIndex), count);
  }

  static const char *paramName(uint8_t group, uint8_t index);

private:
  ModbusRtuMaster &_mb;
  uint8_t _slave = MB_SLAVE_ID;
};

inline const char *SajPdm30::paramName(uint8_t group, uint8_t index) {
  static const char *const p0[] = {
    "Pressure setting", "Pressure deviation", "Operation direction", "Sensor range",
    "Sensor feedback type", "Pressure calib factor", "Prop gain P", "Integ time I",
    "PID function select", "PID sleep delay", "PID wake delay", "PID sleep freq",
    "PID low-freq hold time", "PID sleep dev press", "Power-on auto start",
    "Power-on auto delay", "Antifreeze fn", "Antifreeze freq", "Antifreeze run time",
    "Antifreeze cycle", "Leakage factor", "High press alarm", "High press alarm delay",
    "Low press alarm", "Low press alarm delay", "Water shortage fn", "WS fault threshold",
    "WS test frequency", "WS current %", "WS detect time", "WS auto restart delay",
    "PID sleep rate", "In water detect press", "In water detect time", "AI min input",
    "AI max input", "Accel time 1", "Decel time 1", "Param init", "Param lock",
    "Broken record", "Radiator temp", "Software version", "Main freq source X",
    "System working mode", "Pressure display mode", "(reserved)", "App macro select"
  };
  static const char *const p1[] = {
    "Multi slave backup", "Multi network mode", "Num aux machines", "Multi op modes",
    "Rotation interval", "Max output freq", "Upper frequency", "Lower limit freq",
    "Below lower action", "Carrier frequency", "PID fb loss value", "PID fb loss time",
    "Motor power select", "Motor rated power", "Motor rated freq", "(P1-15)",
    "(P1-16)", "(P1-17)", "(P1-18)", "(P1-19)", "(P1-20)", "(P1-21)", "(P1-22)",
    "(P1-23)", "(P1-24)", "(P1-25)", "(P1-26)", "(P1-27)", "Stop mode",
    "Keyboard set freq", "PID action dir", "PID low-freq hold", "Sleep detect cycle",
    "PWM mode", "Command source", "Local address", "Baud rate", "Data format",
    "Response delay", "(P1-39)", "(P1-40)", "(P1-41)", "Motor type",
    "SP turns ratio", "SP current corr", "WS protect reset times", "(P1-46)", "(P1-47)"
  };
  if (index > PARAM_INDEX_MAX) return "?";
  if (group == 0) return p0[index];
  if (group == 1) return p1[index];
  return "?";
}
