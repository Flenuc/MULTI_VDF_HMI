#pragma once

#include "ModbusRtuMaster.h"
#include "Config.h"

class SajPdm30 {
public:
  explicit SajPdm30(ModbusRtuMaster &mb) : _mb(mb) {}

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

  bool requestStart() { return requestWriteHolding(REG_CTRL_CMD, CMD_FWD_RUN); }
  bool requestStop() { return requestWriteHolding(REG_CTRL_CMD, CMD_DECEL_STOP); }
  bool requestEstop() { return requestWriteHolding(REG_CTRL_CMD, CMD_FREE_STOP); }
  bool requestFaultReset() { return requestWriteHolding(REG_CTRL_CMD, CMD_FAULT_RST); }

  /** set_pct is engineering % of max freq, e.g. 50.0 → raw 5000 */
  bool requestSetFreqPercent(float set_pct) {
    if (set_pct < -100.0f) set_pct = -100.0f;
    if (set_pct > 100.0f) set_pct = 100.0f;
    int32_t raw = (int32_t)(set_pct * 100.0f + (set_pct >= 0 ? 0.5f : -0.5f));
    if (raw < -10000) raw = -10000;
    if (raw > 10000) raw = 10000;
    return requestWriteHolding(REG_FREQ_SET_PCT, (uint16_t)(int16_t)raw);
  }

private:
  ModbusRtuMaster &_mb;
  uint8_t _slave = MB_SLAVE_ID;
};
