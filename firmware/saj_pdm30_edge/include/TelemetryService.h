/**
 * @file TelemetryService.h
 * @brief Non-blocking ~1 Hz register poll → static JSON to WebSocket clients.
 */
#pragma once

#include "Config.h"
#include "ModbusRtuMaster.h"
#include "SajPdm30.h"
#include "ResponseChannel.h"

class TelemetryService {
public:
  TelemetryService(SajPdm30 &vfd, ModbusRtuMaster &mb, IReplySink &sink)
      : _vfd(vfd), _mb(mb), _sink(sink) {}

  void begin() {}
  void setEnabled(bool on) {
    _enabled = on;
    if (!on) {
      _phase = Phase::Idle;
    }
  }
  bool enabled() const { return _enabled; }

  /**
   * Call every loop. Yields if Modbus busy with higher-priority CLI work
   * (caller should only call when CLI idle, or we skip if mb busy unless we own it).
   */
  void poll(bool cliIdle);

private:
  enum class Phase : uint8_t {
    Idle = 0,
    WaitBlockA,     // 0x1001..0x1004 freq + volts + current
    WaitStatus,     // 0x3000
    WaitPressFb,    // 0x1010 feedback pressure (transducer)
    WaitPressSet,   // 0x0000 P0-00 set pressure (consigna)
  };

  SajPdm30 &_vfd;
  ModbusRtuMaster &_mb;
  IReplySink &_sink;

  bool     _enabled = false;
  bool     _awaiting = false;
  Phase    _phase = Phase::Idle;
  uint32_t _nextAt = 0;

  float    _freq = 0;
  float    _amp = 0;
  float    _vdc = 0;
  float    _vout = 0;
  float    _pset = 0;
  float    _pfb = 0;
  uint16_t _status = 3;

  char _json[JSON_TELEMETRY_MAX];

  void emitJson();
  static const char *statusName(uint16_t s);
};
