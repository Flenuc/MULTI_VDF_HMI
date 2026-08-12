#include "TelemetryService.h"

#include <stdio.h>
#include <string.h>
#include <stdlib.h>

const char *TelemetryService::statusName(uint16_t s) {
  if (s == 1) return "run";
  if (s == 2) return "rev";
  if (s == 3) return "stop";
  return "unknown";
}

void TelemetryService::emitJson() {
  // Fixed buffer only — no Arduino String
  // pset = consigna (P0-00), pfb = presión real (0x1010)
  snprintf(
      _json, sizeof(_json),
      "{\"freq\":%.2f,\"amp\":%.2f,\"vdc\":%.1f,\"vout\":%.0f,"
      "\"pset\":%.1f,\"pfb\":%.1f,\"status\":\"%s\"}",
      (double)_freq, (double)_amp, (double)_vdc, (double)_vout,
      (double)_pset, (double)_pfb, statusName(_status));
  _sink.reply(Channel::broadcast(), _json);
}

static bool looksLikeBusRaw(uint16_t r) {
  // 0.1 V units: 150 V .. 900 V DC bus typical
  return r >= 1500 && r <= 9000;
}

static bool nearFreqRaw(uint16_t r, uint16_t freqRaw) {
  if (freqRaw == 0) return false;
  int d = (int)r - (int)freqRaw;
  if (d < 0) d = -d;
  return d <= 200;  // within 2.00 Hz
}

void TelemetryService::poll(bool cliIdle) {
  if (!_enabled) return;

  const uint32_t now = millis();

  if (_phase == Phase::Idle) {
    if (!cliIdle) return;
    if ((int32_t)(now - _nextAt) < 0) return;
    if (_mb.isBusy()) return;

    // 0x1001..0x1004: freq, (suspect), (bus-like), current
    if (!_vfd.requestReadHolding(REG_RUN_FREQ, 4)) return;
    _phase = Phase::WaitBlockA;
    _awaiting = true;
    return;
  }

  if (_mb.isBusy()) return;
  if (!_awaiting) return;

  _awaiting = false;

  if (_phase == Phase::WaitBlockA) {
    if (_mb.lastResult() == MbResult::Ok) {
      const uint16_t *v = _mb.lastValues();
      const uint16_t rFreq = v[0];
      const uint16_t r1002 = v[1];
      const uint16_t r1003 = v[2];
      const uint16_t rCurr = v[3];

      _freq = rFreq / 100.0f;
      _amp = rCurr / 100.0f;

      // Field PDM-30 (Guition tests):
      //  - 0x1003 raw ~3100..3200 always ≈ DC bus at 0.1 V (stop and run)
      //  - 0x1002 is 0 at stop, or ≈ frequency raw when running (NOT volts)
      // Manual text claims 0x1002=bus / 0x1003=Vout@1V — that yields Vout=3162 V
      // and Vbus=600 V while running, which is wrong on this unit.
      const bool busAt1003 = looksLikeBusRaw(r1003);
      const bool busAt1002 = looksLikeBusRaw(r1002) && !nearFreqRaw(r1002, rFreq);

      if (busAt1003 && !busAt1002) {
        _vdc = r1003 / 10.0f;
        // Do not report r1003 as Vout; avoid r1002 when it mirrors frequency
        if (!nearFreqRaw(r1002, rFreq) && r1002 > 0 && r1002 < 500)
          _vout = (float)r1002;  // rare: small 1 V-scale out reading
        else
          _vout = 0.0f;
      } else if (busAt1002) {
        _vdc = r1002 / 10.0f;
        if (busAt1003)
          _vout = 0.0f;
        else if (r1003 < 500)
          _vout = (float)r1003;
        else
          _vout = r1003 / 10.0f;
      } else {
        // Fallback to manual scales
        _vdc = r1002 / 10.0f;
        _vout = (r1003 >= 500) ? (r1003 / 10.0f) : (float)r1003;
      }
    }

    if (!_vfd.requestReadHolding(REG_VFD_STATUS, 1)) {
      _phase = Phase::Idle;
      _nextAt = now + TELEMETRY_PERIOD_MS;
      return;
    }
    _phase = Phase::WaitStatus;
    _awaiting = true;
    return;
  }

  if (_phase == Phase::WaitStatus) {
    if (_mb.lastResult() == MbResult::Ok) {
      _status = _mb.lastValue();
    }
    // Feedback pressure only (0x1010, 0.1 bar) — real transducer value
    if (!_vfd.requestReadHolding(REG_FB_PRESS, 1)) {
      emitJson();
      _phase = Phase::Idle;
      _nextAt = now + TELEMETRY_PERIOD_MS;
      return;
    }
    _phase = Phase::WaitPressFb;
    _awaiting = true;
    return;
  }

  if (_phase == Phase::WaitPressFb) {
    if (_mb.lastResult() == MbResult::Ok) {
      // Manual: 0.1 bar. Sanity: reject absurd values (>200 bar) as bad frames
      uint16_t raw = _mb.lastValue();
      float p = raw / 10.0f;
      _pfb = (p >= 0.0f && p <= 200.0f) ? p : 0.0f;
    }
    // Set pressure from P0-00, eng scale 0.1 bar — matches r0 0 (not 0x100F)
    if (!_vfd.requestReadHolding(REG_P0_00_SET_P, 1)) {
      emitJson();
      _phase = Phase::Idle;
      _nextAt = now + TELEMETRY_PERIOD_MS;
      return;
    }
    _phase = Phase::WaitPressSet;
    _awaiting = true;
    return;
  }

  if (_phase == Phase::WaitPressSet) {
    if (_mb.lastResult() == MbResult::Ok) {
      uint16_t raw = _mb.lastValue();
      float p = raw / 10.0f;
      _pset = (p >= 0.0f && p <= 200.0f) ? p : _pset;
    }
    emitJson();
    _phase = Phase::Idle;
    _nextAt = now + TELEMETRY_PERIOD_MS;
  }
}
