#include "CliEngine.h"
#include "ScaleTable.h"
#include "TelemetryService.h"
#include "NetworkService.h"
#include "BtIo.h"
#include "DriveProfile.h"
#include "generated/Pdh30ParamTable.h"

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>

void CliEngine::replyf(const Channel &ch, const char *fmt, ...) {
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(_reply, sizeof(_reply), fmt, ap);
  va_end(ap);
  _sink.reply(ch, _reply);
}

void CliEngine::printHelp(const Channel &ch) {
  replyf(ch, "help | ping | dump | stream on|off");
  replyf(ch, "profile | profile get | profile set saj.pdm30|saj.pdh30");
  replyf(ch, "pget <id> | pset <id> <eng>   e.g. pget F0.00 / pset F0.00 2.6");
  replyf(ch, "r0|r1 <ii>   w0|w1 <ii> <float>   (PDM map)");
  replyf(ch, "raw <addr> | wraw <addr> <uint>   e.g. raw 0xF000");
  replyf(ch, "start | stop | estop | reset | set <pct>");
  replyf(ch, "slave <id>   values ENGINEERING floats");
  replyf(ch, "wifi status | wifi set <ssid> <pass> | wifi reconnect");
  replyf(ch, "wifi profile list|save <name> <ssid> <pass>|use <name>|delete <name>");
  replyf(ch, "mqtt status | mqtt set <host> [port] | mqtt user <u> <p>");
  replyf(ch, "mqtt enable | mqtt disable");
  replyf(ch, "bt status | bt advertise | bt clearbonds");
  replyf(ch, "profile now=%s", g_driveProfile.idStr());
}

// Normalize param id to uppercase canonical form (F0.00 / P0-00 / D0.00)
static bool normalizeParamId(const char *in, char *out, size_t outSz) {
  if (!in || !out || outSz < 5) return false;
  char tmp[16];
  size_t n = 0;
  for (const char *p = in; *p && n + 1 < sizeof(tmp); ++p) {
    if (*p == ' ' || *p == '\t') continue;
    tmp[n++] = (char)toupper((unsigned char)*p);
  }
  tmp[n] = '\0';
  // P0-0 / P0-00 / P0.00
  if (tmp[0] == 'P' && (tmp[1] == '0' || tmp[1] == '1') &&
      (tmp[2] == '-' || tmp[2] == '.')) {
    int idx = atoi(tmp + 3);
    if (idx < 0 || idx > 47) return false;
    snprintf(out, outSz, "P%c-%02d", tmp[1], idx);
    return true;
  }
  // F0.00 .. F9.00, FD.00, FE.00, D0.00, E0.00
  if ((tmp[0] == 'F' || tmp[0] == 'D' || tmp[0] == 'E') && strchr(tmp, '.')) {
    strncpy(out, tmp, outSz - 1);
    out[outSz - 1] = '\0';
    // pad index to 2 digits if F0.0 style
    char g[4] = {};
    int idx = -1;
    if (sscanf(tmp, "%3[^.].%d", g, &idx) == 2 && idx >= 0 && idx < 256) {
      snprintf(out, outSz, "%s.%02d", g, idx);
    }
    return true;
  }
  return false;
}

static uint16_t engToRawScaled(float eng, uint16_t scale) {
  if (scale < 1) scale = 1;
  float v = eng * (float)scale;
  if (v >= 0.0f) v += 0.5f;
  else v -= 0.5f;
  if (v < 0) v = 0;
  if (v > 65535.0f) v = 65535.0f;
  return (uint16_t)v;
}

static float rawToEngScaled(uint16_t raw, uint16_t scale) {
  if (scale <= 1) {
    int16_t s = (int16_t)raw;
    return (float)s;
  }
  int16_t s = (int16_t)raw;
  return (float)s / (float)scale;
}

// Commands that never touch Modbus — must work even while telemetry owns the bus
// (otherwise USB/MQTT feel "dead" when stream is on).
static bool isControlOnlyCmd(int argc, char **argv) {
  if (argc < 1 || !argv[0]) return false;
  const char *cmd = argv[0];
  if (strcmp(cmd, "help") == 0 || strcmp(cmd, "h") == 0) return true;
  if (strcmp(cmd, "stream") == 0) return true;
  if (strcmp(cmd, "wifi") == 0) return true;   // status/set/profile/reconnect
  if (strcmp(cmd, "mqtt") == 0) return true;   // status/set/user/enable/disable
  if (strcmp(cmd, "bt") == 0) return true;     // status/advertise/clearbonds
  if (strcmp(cmd, "profile") == 0) return true; // drive profile get/set (no Modbus)
  if (strcmp(cmd, "profile") == 0) return true;
  if (strcmp(cmd, "slave") == 0 && argc < 2) return true;  // query only
  return false;
}

void CliEngine::handleLine(const Channel &ch, const char *line) {
  if (!line || !*line) return;

  // Mutable copy for strtok-style parse
  char buf[CLI_LINE_MAX];
  strncpy(buf, line, sizeof(buf) - 1);
  buf[sizeof(buf) - 1] = '\0';

  char *argv[8];
  int argc = 0;
  char *p = buf;
  while (*p && argc < 8) {
    while (*p == ' ' || *p == '\t') p++;
    if (!*p) break;
    argv[argc++] = p;
    while (*p && *p != ' ' && *p != '\t') p++;
    if (*p) *p++ = '\0';
  }
  if (argc == 0) return;

  // Control path always available (stream off / help / wifi / mqtt…)
  if (isControlOnlyCmd(argc, argv)) {
    dispatch(ch, argc, argv);
    return;
  }

  // Modbus path: pause telemetry so it does not keep the bus forever
  if (_tel && _tel->enabled()) {
    _tel->setEnabled(false);
    _streamPausedForCmd = _streamOn;
  }

  if (_job != Job::None || _mb.isBusy()) {
    // Queue one command until the in-flight Modbus frame finishes
    // (telemetry cycle or previous job). Avoids permanent "USB dead" feel.
    if (!_hasPending) {
      strncpy(_pendingLine, line, sizeof(_pendingLine) - 1);
      _pendingLine[sizeof(_pendingLine) - 1] = '\0';
      _pendingCh = ch;
      _hasPending = true;
      replyf(ch, "OK queued");
    } else {
      replyf(ch, "ERR: busy");
    }
    return;
  }

  dispatch(ch, argc, argv);
}

void CliEngine::dispatch(const Channel &ch, int argc, char **argv) {
  const char *cmd = argv[0];

  if (strcmp(cmd, "help") == 0 || strcmp(cmd, "h") == 0) {
    printHelp(ch);
    return;
  }

  if (strcmp(cmd, "stream") == 0) {
    if (argc < 2) {
      replyf(ch, "usage: stream on|off  (now=%s)", _streamOn ? "on" : "off");
      return;
    }
    if (strcmp(argv[1], "on") == 0) {
      _streamOn = true;
      if (_tel) _tel->setEnabled(true);
      replyf(ch, "stream ON (~1 Hz JSON on WebSocket)");
    } else if (strcmp(argv[1], "off") == 0) {
      _streamOn = false;
      if (_tel) _tel->setEnabled(false);
      replyf(ch, "stream OFF");
    } else {
      replyf(ch, "usage: stream on|off");
    }
    return;
  }

  if (strcmp(cmd, "slave") == 0) {
    if (argc < 2) {
      replyf(ch, "slave=%u", (unsigned)_vfd.slaveId());
      return;
    }
    int id = atoi(argv[1]);
    if (id < 1 || id > 247) {
      replyf(ch, "ERR: slave 1..247");
      return;
    }
    _vfd.setSlaveId((uint8_t)id);
    replyf(ch, "slave=%d", id);
    return;
  }

  // ----- Wi-Fi profiles -----
  if (strcmp(cmd, "wifi") == 0) {
    if (!_net) {
      replyf(ch, "ERR: network not ready");
      return;
    }
    if (argc < 2 || strcmp(argv[1], "status") == 0) {
      _net->wifiStatus(ch);
      return;
    }
    if (strcmp(argv[1], "set") == 0) {
      if (argc < 4) {
        replyf(ch, "usage: wifi set <ssid> <password>");
        return;
      }
      const char *pass = argv[3];
      if (strcmp(pass, "\"\"") == 0 || strcmp(pass, "''") == 0) pass = "";
      _net->wifiSetQuick(argv[2], pass, ch);
      return;
    }
    if (strcmp(argv[1], "reconnect") == 0) {
      _net->wifiReconnect(ch);
      return;
    }
    if (strcmp(argv[1], "profile") == 0) {
      if (argc < 3) {
        replyf(ch, "usage: wifi profile list|save|use|delete …");
        return;
      }
      if (strcmp(argv[2], "list") == 0) {
        _net->wifiProfileList(ch);
        return;
      }
      if (strcmp(argv[2], "save") == 0) {
        if (argc < 6) {
          replyf(ch, "usage: wifi profile save <name> <ssid> <pass>");
          return;
        }
        const char *pass = argv[5];
        if (strcmp(pass, "\"\"") == 0) pass = "";
        _net->wifiProfileSave(argv[3], argv[4], pass, ch);
        return;
      }
      if (strcmp(argv[2], "use") == 0) {
        if (argc < 4) {
          replyf(ch, "usage: wifi profile use <name>");
          return;
        }
        _net->wifiProfileUse(argv[3], ch);
        return;
      }
      if (strcmp(argv[2], "delete") == 0) {
        if (argc < 4) {
          replyf(ch, "usage: wifi profile delete <name>");
          return;
        }
        _net->wifiProfileDelete(argv[3], ch);
        return;
      }
      replyf(ch, "usage: wifi profile list|save|use|delete");
      return;
    }
    replyf(ch, "usage: wifi status|set|reconnect|profile …");
    return;
  }

  // ----- MQTT -----
  if (strcmp(cmd, "mqtt") == 0) {
    if (!_net) {
      replyf(ch, "ERR: network not ready");
      return;
    }
    if (argc < 2 || strcmp(argv[1], "status") == 0) {
      _net->mqttStatus(ch);
      return;
    }
    if (strcmp(argv[1], "set") == 0) {
      if (argc < 3) {
        replyf(ch, "usage: mqtt set <host> [port]");
        return;
      }
      uint16_t port = MQTT_DEFAULT_PORT;
      if (argc >= 4) port = (uint16_t)atoi(argv[3]);
      _net->mqttSetHost(argv[2], port, ch);
      return;
    }
    if (strcmp(argv[1], "user") == 0) {
      if (argc < 3) {
        replyf(ch, "usage: mqtt user <username> [password]");
        return;
      }
      const char *pw = (argc >= 4) ? argv[3] : "";
      if (strcmp(pw, "\"\"") == 0) pw = "";
      _net->mqttSetAuth(argv[2], pw, ch);
      return;
    }
    if (strcmp(argv[1], "enable") == 0) {
      _net->mqttSetEnabled(true, ch);
      return;
    }
    if (strcmp(argv[1], "disable") == 0) {
      _net->mqttSetEnabled(false, ch);
      return;
    }
    replyf(ch, "usage: mqtt status|set|user|enable|disable");
    return;
  }

  // ----- Bluetooth (Classic SPP / BLE NUS bridge status) -----
  if (strcmp(cmd, "bt") == 0) {
    if (argc < 2 || strcmp(argv[1], "status") == 0) {
      char st[160];
      st[0] = '\0';
      if (g_btIo.fillStatus) {
        g_btIo.fillStatus(st, sizeof(st));
      }
      if (st[0]) {
        replyf(ch, "%s", st);
      } else {
        replyf(ch, "bt ready=0 (not enabled on this board build)");
      }
      return;
    }
    if (strcmp(argv[1], "advertise") == 0 || strcmp(argv[1], "adv") == 0) {
      if (g_btIo.refreshDiscoverable) {
        g_btIo.refreshDiscoverable();
        replyf(ch, "OK bt advertise refreshed");
      } else {
        replyf(ch, "ERR: bt not available");
      }
      return;
    }
    if (strcmp(argv[1], "clearbonds") == 0 || strcmp(argv[1], "unpair") == 0) {
      if (g_btIo.clearBonds) {
        g_btIo.clearBonds();
        replyf(ch, "OK bt bonds cleared — re-pair host");
      } else {
        replyf(ch, "ERR: bt not available");
      }
      return;
    }
    replyf(ch, "usage: bt status|advertise|clearbonds");
    return;
  }

  if (strcmp(cmd, "profile") == 0) {
    if (argc < 2 || strcmp(argv[1], "get") == 0) {
      replyf(ch, "profile=%s", g_driveProfile.idStr());
      return;
    }
    if (strcmp(argv[1], "set") == 0 && argc >= 3) {
      if (!g_driveProfile.setFromStr(argv[2])) {
        replyf(ch, "ERR: profile set saj.pdm30|saj.pdh30");
        return;
      }
      replyf(ch, "OK profile=%s", g_driveProfile.idStr());
      return;
    }
    if (strcmp(argv[1], "list") == 0) {
      replyf(ch, "profiles: saj.pdm30 saj.pdh30");
      return;
    }
    replyf(ch, "usage: profile get|list|set <id>");
    return;
  }

  if (strcmp(cmd, "ping") == 0 || strcmp(cmd, "status") == 0) {
    _jobCh = ch;
    _pingStep = 0;
    _dumpAwaiting = false;
    _job = Job::Ping;
    return;
  }

  if (strcmp(cmd, "dump") == 0) {
    _jobCh = ch;
    _dumpGroup = 0;
    _dumpIndex = 0;
    _dumpChunk = 0;
    _dumpPdhIdx = 0;
    _dumpIsPdh = g_driveProfile.isPdh();
    _dumpAwaiting = false;
    _dumpNextChunkAt = 0;
    // Pause telemetry stream so it does not fight dump for Modbus / WS bandwidth
    _streamPausedForDump = _streamOn;
    if (_streamPausedForDump && _tel) {
      _tel->setEnabled(false);
    }
    _job = Job::Dump;
    replyf(ch, "DUMP begin profile=%s", g_driveProfile.idStr());
    replyf(ch, "CSV:param,addr,eng,raw,unit");
    return;
  }

  // pget <id>   pset <id> <eng>
  if ((strcmp(cmd, "pget") == 0 || strcmp(cmd, "pset") == 0) && argc >= 2) {
    char id[12];
    if (!normalizeParamId(argv[1], id, sizeof(id))) {
      replyf(ch, "ERR: bad id (use F0.00 or P0-00)");
      return;
    }
    _jobCh = ch;
    _ctxIsPdhId = false;
    _ctxScaled = true;
    _ctxIsParam = true;
    strncpy(_ctxId, id, sizeof(_ctxId) - 1);
    _ctxId[sizeof(_ctxId) - 1] = '\0';

    // PDM classic P0/P1
    if (id[0] == 'P' && (id[1] == '0' || id[1] == '1')) {
      uint8_t g = (uint8_t)(id[1] - '0');
      int ii = atoi(id + 3);
      _ctxGroup = g;
      _ctxIndex = (uint8_t)ii;
      _ctxAddr = paramAddress(g, (uint8_t)ii);
      _ctxScale = ScaleTable::scaleOf(g, (uint8_t)ii);
      if (strcmp(cmd, "pget") == 0) {
        if (!_vfd.requestReadParam(g, (uint8_t)ii)) {
          replyf(ch, "ERR: queue read");
          return;
        }
        _job = Job::WaitRead;
        return;
      }
      if (argc < 3) {
        replyf(ch, "usage: pset P0-00 <eng>");
        return;
      }
      float eng = strtof(argv[2], nullptr);
      uint16_t raw = ScaleTable::engToRaw(g, (uint8_t)ii, eng);
      _ctxEng = eng;
      if (!_vfd.requestWriteParam(g, (uint8_t)ii, raw)) {
        replyf(ch, "ERR: queue write");
        return;
      }
      _job = Job::WaitWrite;
      return;
    }

    // PDH catalog id (F0.00, FD.01, D0.00, …)
    const Pdh30ParamEntry *pe = pdh30FindId(id);
    if (!pe) {
      replyf(ch, "ERR: unknown id %s (set profile saj.pdh30 catalog)", id);
      return;
    }
    _ctxIsPdhId = true;
    _ctxAddr = pe->reg;
    _ctxScale = pe->scale ? pe->scale : 1;
    if (strcmp(cmd, "pget") == 0) {
      if (!_vfd.requestReadHolding(pe->reg, 1)) {
        replyf(ch, "ERR: queue read");
        return;
      }
      _job = Job::WaitRead;
      return;
    }
    if (pe->ro) {
      replyf(ch, "ERR: %s is read-only", id);
      return;
    }
    if (argc < 3) {
      replyf(ch, "usage: pset F0.00 <eng>");
      return;
    }
    float eng = strtof(argv[2], nullptr);
    uint16_t raw = engToRawScaled(eng, _ctxScale);
    _ctxEng = eng;
    if (!_vfd.requestWriteHolding(pe->reg, raw)) {
      replyf(ch, "ERR: queue write");
      return;
    }
    _job = Job::WaitWrite;
    return;
  }

  if (strcmp(cmd, "start") == 0) {
    _jobCh = ch;
    if (!_vfd.requestStart()) {
      replyf(ch, "ERR: queue start");
      return;
    }
    _job = Job::WaitOp;
    return;
  }
  if (strcmp(cmd, "stop") == 0) {
    _jobCh = ch;
    if (!_vfd.requestStop()) {
      replyf(ch, "ERR: queue stop");
      return;
    }
    _job = Job::WaitOp;
    return;
  }
  if (strcmp(cmd, "estop") == 0) {
    _jobCh = ch;
    if (!_vfd.requestEstop()) {
      replyf(ch, "ERR: queue estop");
      return;
    }
    _job = Job::WaitOp;
    return;
  }
  if (strcmp(cmd, "reset") == 0) {
    _jobCh = ch;
    if (!_vfd.requestFaultReset()) {
      replyf(ch, "ERR: queue reset");
      return;
    }
    _job = Job::WaitOp;
    return;
  }
  if (strcmp(cmd, "set") == 0) {
    if (argc < 2) {
      replyf(ch, "usage: set <percent>  e.g. set 50.0");
      return;
    }
    float pct = strtof(argv[1], nullptr);
    _jobCh = ch;
    if (!_vfd.requestSetFreqPercent(pct)) {
      replyf(ch, "ERR: queue set");
      return;
    }
    _ctxEng = pct;
    _job = Job::WaitOp;
    return;
  }

  // r0 / r1
  if ((strcmp(cmd, "r0") == 0 || strcmp(cmd, "r1") == 0) && argc >= 2) {
    uint8_t g = (cmd[1] == '1') ? 1 : 0;
    int ii = atoi(argv[1]);
    if (ii < 0 || ii > PARAM_INDEX_MAX) {
      replyf(ch, "ERR: index 0..47");
      return;
    }
    _jobCh = ch;
    _ctxGroup = g;
    _ctxIndex = (uint8_t)ii;
    _ctxAddr = paramAddress(g, (uint8_t)ii);
    _ctxIsParam = true;
    _ctxScaled = true;
    if (!_vfd.requestReadParam(g, (uint8_t)ii)) {
      replyf(ch, "ERR: queue read");
      return;
    }
    _job = Job::WaitRead;
    return;
  }

  // w0 / w1  <ii> <float>
  if ((strcmp(cmd, "w0") == 0 || strcmp(cmd, "w1") == 0) && argc >= 3) {
    uint8_t g = (cmd[1] == '1') ? 1 : 0;
    int ii = atoi(argv[1]);
    if (ii < 0 || ii > PARAM_INDEX_MAX) {
      replyf(ch, "ERR: index 0..47");
      return;
    }
    float eng = strtof(argv[2], nullptr);
    uint16_t raw = ScaleTable::engToRaw(g, (uint8_t)ii, eng);
    _jobCh = ch;
    _ctxGroup = g;
    _ctxIndex = (uint8_t)ii;
    _ctxAddr = paramAddress(g, (uint8_t)ii);
    _ctxIsParam = true;
    _ctxScaled = true;
    _ctxEng = eng;
    if (!_vfd.requestWriteParam(g, (uint8_t)ii, raw)) {
      replyf(ch, "ERR: queue write");
      return;
    }
    _job = Job::WaitWrite;
    return;
  }

  if (strcmp(cmd, "raw") == 0 && argc >= 2) {
    char *end = nullptr;
    unsigned long addr = strtoul(argv[1], &end, 0);
    if (end == argv[1] || addr > 0xFFFFUL) {
      replyf(ch, "ERR: bad addr");
      return;
    }
    _jobCh = ch;
    _ctxAddr = (uint16_t)addr;
    _ctxIsParam = false;
    _ctxScaled = false;
    _ctxIsPdhId = false;
    if (!_vfd.requestReadHolding((uint16_t)addr, 1)) {
      replyf(ch, "ERR: queue raw");
      return;
    }
    _job = Job::WaitRead;
    return;
  }

  // wraw <addr> <uint>
  if (strcmp(cmd, "wraw") == 0 && argc >= 3) {
    char *end = nullptr;
    unsigned long addr = strtoul(argv[1], &end, 0);
    if (end == argv[1] || addr > 0xFFFFUL) {
      replyf(ch, "ERR: bad addr");
      return;
    }
    unsigned long val = strtoul(argv[2], nullptr, 0);
    if (val > 0xFFFFUL) {
      replyf(ch, "ERR: bad value");
      return;
    }
    _jobCh = ch;
    _ctxAddr = (uint16_t)addr;
    _ctxIsParam = false;
    _ctxScaled = false;
    _ctxIsPdhId = false;
    _ctxEng = (float)val;
    if (!_vfd.requestWriteHolding((uint16_t)addr, (uint16_t)val)) {
      replyf(ch, "ERR: queue wraw");
      return;
    }
    _job = Job::WaitWrite;
    return;
  }

  replyf(ch, "ERR: unknown — type help");
}

bool CliEngine::clientStillValid() const {
  // USB always valid; MQTT jobs valid while broker link is up (or still finish dump on USB)
  if (_jobCh.isUsb()) return true;
  if (_jobCh.isMqtt()) return _sink.isRemoteAlive();
  return true;
}

void CliEngine::cancelJob(const char *reason) {
  if (_job == Job::Dump) {
    finishDump(reason ? reason : "cancelled");
    return;
  }
  _job = Job::None;
  _dumpAwaiting = false;
  if (clientStillValid()) {
    replyf(_jobCh, "ERR: cancelled (%s)", reason ? reason : "?");
  }
}

void CliEngine::finishDump(const char *errMsg) {
  _job = Job::None;
  _streamPausedForCmd = false;  // dump owns stream restore below
  _dumpAwaiting = false;
  _dumpNextChunkAt = 0;
  if (clientStillValid()) {
    if (errMsg && errMsg[0]) {
      replyf(_jobCh, "ERR: dump %s", errMsg);
    }
    replyf(_jobCh, "CSV:END");
    replyf(_jobCh, "DUMP done");
  }
  // Restore telemetry if it was on before dump
  if (_streamPausedForDump) {
    _streamPausedForDump = false;
    if (_streamOn && _tel) _tel->setEnabled(true);
  }
}

void CliEngine::appendDumpCsvLine(size_t &pos, uint8_t group, uint8_t idx,
                                  bool ok, uint16_t raw) {
  if (pos + 48 >= sizeof(_dumpBatch)) return;
  int n;
  if (!ok) {
    n = snprintf(_dumpBatch + pos, sizeof(_dumpBatch) - pos,
                 "CSV:P%u-%02u,0x%04X,ERROR,ERROR,\n",
                 group, idx, paramAddress(group, idx));
  } else {
    float eng = ScaleTable::rawToEng(group, idx, raw);
    const char *u = ScaleTable::unitOf(group, idx);
    n = snprintf(_dumpBatch + pos, sizeof(_dumpBatch) - pos,
                 "CSV:P%u-%02u,0x%04X,%.4g,%u,%s\n",
                 group, idx, paramAddress(group, idx),
                 (double)eng, (unsigned)raw, u ? u : "");
  }
  if (n > 0) pos += (size_t)n;
}

void CliEngine::appendDumpPdhCsvLine(size_t &pos, const char *id, uint16_t reg,
                                     uint16_t scale, bool ok, uint16_t raw) {
  if (pos + 64 >= sizeof(_dumpBatch)) return;
  int n;
  if (!ok || !id) {
    n = snprintf(_dumpBatch + pos, sizeof(_dumpBatch) - pos,
                 "CSV:%s,0x%04X,ERROR,ERROR,\n",
                 id ? id : "?", (unsigned)reg);
  } else {
    float eng = rawToEngScaled(raw, scale ? scale : 1);
    n = snprintf(_dumpBatch + pos, sizeof(_dumpBatch) - pos,
                 "CSV:%s,0x%04X,%.4g,%u,\n",
                 id, (unsigned)reg, (double)eng, (unsigned)raw);
  }
  if (n > 0) pos += (size_t)n;
}

void CliEngine::restoreStreamIfNeeded() {
  if (_streamPausedForCmd) {
    _streamPausedForCmd = false;
    if (_streamOn && _tel && !_streamPausedForDump) {
      _tel->setEnabled(true);
    }
  }
}

void CliEngine::poll() {
  pollJob();
  // Run one queued Modbus CLI command when the bus is free
  if (_hasPending && _job == Job::None && !_mb.isBusy()) {
    _hasPending = false;
    char line[CLI_LINE_MAX];
    strncpy(line, _pendingLine, sizeof(line) - 1);
    line[sizeof(line) - 1] = '\0';
    Channel ch = _pendingCh;
    // Re-enter via handleLine (control cmds already filtered at queue time)
    handleLine(ch, line);
  }
}

void CliEngine::pollJob() {
  if (_job == Job::None) return;

  // Drop long jobs if WS client gone (e.g. mid-dump) — always emit END so host unblocks
  if (_job == Job::Dump && !clientStillValid()) {
    // Cannot reply to dead WS; just clear job and restore stream
    _job = Job::None;
    _dumpAwaiting = false;
    if (_streamPausedForDump) {
      _streamPausedForDump = false;
      if (_streamOn && _tel) _tel->setEnabled(true);
    }
    _streamPausedForCmd = false;
    return;
  }

  if (_mb.isBusy()) return;

  if (_job == Job::WaitRead) {
    MbResult r = _mb.lastResult();
    if (r != MbResult::Ok) {
      replyf(_jobCh, "ERR: %s", _mb.resultStr());
    } else if (_ctxIsPdhId) {
      uint16_t raw = _mb.lastValue();
      float eng = rawToEngScaled(raw, _ctxScale);
      replyf(_jobCh, "%s @0x%04X = %.4g  (raw=%u scale=%u)",
             _ctxId, _ctxAddr, (double)eng, (unsigned)raw, (unsigned)_ctxScale);
    } else if (_ctxIsParam && _ctxScaled) {
      uint16_t raw = _mb.lastValue();
      float eng = ScaleTable::rawToEng(_ctxGroup, _ctxIndex, raw);
      const char *u = ScaleTable::unitOf(_ctxGroup, _ctxIndex);
      replyf(_jobCh, "P%u-%02u @0x%04X = %.4g %s  (raw=%u)",
             _ctxGroup, _ctxIndex, _ctxAddr, (double)eng, u, (unsigned)raw);
    } else {
      uint16_t v = _mb.lastValue();
      replyf(_jobCh, "0x%04X = %u (0x%04X)", _ctxAddr, (unsigned)v, (unsigned)v);
    }
    _job = Job::None;
    restoreStreamIfNeeded();
    return;
  }

  if (_job == Job::WaitWrite) {
    MbResult r = _mb.lastResult();
    if (r != MbResult::Ok) {
      replyf(_jobCh, "ERR: %s", _mb.resultStr());
    } else if (_ctxIsPdhId) {
      uint16_t raw = engToRawScaled(_ctxEng, _ctxScale);
      replyf(_jobCh, "OK write %s @0x%04X eng=%.4g raw=%u",
             _ctxId, _ctxAddr, (double)_ctxEng, (unsigned)raw);
    } else if (_ctxIsParam) {
      uint16_t raw = _mb.lastValue();
      replyf(_jobCh, "OK write P%u-%02u @0x%04X eng=%.4g raw=%u",
             _ctxGroup, _ctxIndex, _ctxAddr, (double)_ctxEng, (unsigned)raw);
    } else {
      replyf(_jobCh, "OK wraw 0x%04X = %u", _ctxAddr, (unsigned)_mb.lastValue());
    }
    _job = Job::None;
    restoreStreamIfNeeded();
    return;
  }

  if (_job == Job::WaitOp) {
    MbResult r = _mb.lastResult();
    if (r != MbResult::Ok) {
      replyf(_jobCh, "ERR: %s", _mb.resultStr());
    } else {
      replyf(_jobCh, "OK op raw=%u", (unsigned)_mb.lastValue());
    }
    _job = Job::None;
    restoreStreamIfNeeded();
    return;
  }

  if (_job == Job::Ping) {
    if (!_dumpAwaiting) {
      bool ok = false;
      if (_pingStep == 0) ok = _vfd.requestReadHolding(REG_VFD_STATUS, 1);
      else if (_pingStep == 1) ok = _vfd.requestReadHolding(REG_RUN_FREQ, 1);
      else if (_pingStep == 2) ok = _vfd.requestReadHolding(REG_OUT_CURRENT, 1);
      // Field: bus voltage lives at 0x1003 (0.1 V), not 0x1002
      else if (_pingStep == 3) ok = _vfd.requestReadHolding(REG_OUT_VOLTAGE, 1);
      if (!ok) {
        replyf(_jobCh, "ERR: ping queue");
        _job = Job::None;
        restoreStreamIfNeeded();
        return;
      }
      _dumpAwaiting = true;
      return;
    }
    _dumpAwaiting = false;
    if (_mb.lastResult() != MbResult::Ok) {
      replyf(_jobCh, "PING FAIL step %u: %s", _pingStep, _mb.resultStr());
      _job = Job::None;
      restoreStreamIfNeeded();
      return;
    }
    uint16_t v = _mb.lastValue();
    if (_pingStep == 0) {
      const char *n = (v == 1) ? "run" : (v == 2) ? "rev" : (v == 3) ? "stop" : "?";
      replyf(_jobCh, "status=%u (%s)", (unsigned)v, n);
    } else if (_pingStep == 1) {
      replyf(_jobCh, "freq=%.2f Hz", v / 100.0);
    } else if (_pingStep == 2) {
      replyf(_jobCh, "amp=%.2f A", v / 100.0);
    } else if (_pingStep == 3) {
      replyf(_jobCh, "vdc=%.1f V", v / 10.0);
      replyf(_jobCh, "Link OK");
      _job = Job::None;
      restoreStreamIfNeeded();
      return;
    }
    _pingStep++;
    return;
  }

  if (_job == Job::Dump) {
    // ----- PDH: one register per catalog entry (non-contiguous F/D/E map) -----
    if (_dumpIsPdh) {
      if (_dumpAwaiting) {
        _dumpAwaiting = false;
        if (!clientStillValid()) {
          finishDump("client gone");
          return;
        }
        if (_dumpPdhIdx >= kPdh30ParamsCount) {
          finishDump(nullptr);
          return;
        }
        const Pdh30ParamEntry &pe = kPdh30Params[_dumpPdhIdx];
        size_t pos = 0;
        _dumpBatch[0] = '\0';
        if (_mb.lastResult() != MbResult::Ok) {
          appendDumpPdhCsvLine(pos, pe.id, pe.reg, pe.scale, false, 0);
        } else {
          appendDumpPdhCsvLine(pos, pe.id, pe.reg, pe.scale, true, _mb.lastValue());
        }
        if (pos > 0) {
          if (_dumpBatch[pos - 1] == '\n') _dumpBatch[pos - 1] = '\0';
          _sink.reply(_jobCh, _dumpBatch);
        }
        _dumpPdhIdx++;
        if (_dumpPdhIdx >= kPdh30ParamsCount) {
          finishDump(nullptr);
          return;
        }
        _dumpNextChunkAt = millis() + DUMP_CHUNK_GAP_MS;
        return;
      }

      if ((int32_t)(millis() - _dumpNextChunkAt) < 0) return;
      if (!clientStillValid()) {
        finishDump("client gone");
        return;
      }
      if (_dumpPdhIdx >= kPdh30ParamsCount) {
        finishDump(nullptr);
        return;
      }
      const Pdh30ParamEntry &pe = kPdh30Params[_dumpPdhIdx];
      if (!_vfd.requestReadHolding(pe.reg, 1)) {
        finishDump("queue failed");
        return;
      }
      _dumpChunk = 1;
      _dumpAwaiting = true;
      return;
    }

    // ----- PDM: contiguous P0/P1 chunks -----
    if (_dumpAwaiting) {
      _dumpAwaiting = false;
      if (!clientStillValid()) {
        finishDump("client gone");
        return;
      }
      uint8_t qty = _dumpChunk;
      uint8_t start = _dumpIndex;

      // One multi-line WebSocket frame per chunk (avoids TX queue overflow)
      size_t pos = 0;
      _dumpBatch[0] = '\0';
      if (_mb.lastResult() != MbResult::Ok) {
        for (uint8_t i = 0; i < qty; i++) {
          appendDumpCsvLine(pos, _dumpGroup, (uint8_t)(start + i), false, 0);
        }
      } else {
        const uint16_t *vals = _mb.lastValues();
        for (uint8_t i = 0; i < qty; i++) {
          appendDumpCsvLine(pos, _dumpGroup, (uint8_t)(start + i), true, vals[i]);
        }
      }
      if (pos > 0) {
        if (_dumpBatch[pos - 1] == '\n') {
          _dumpBatch[pos - 1] = '\0';
        }
        _sink.reply(_jobCh, _dumpBatch);
      }

      _dumpIndex = (uint8_t)(start + qty);
      if (_dumpIndex > PARAM_INDEX_MAX) {
        if (_dumpGroup == 0) {
          _dumpGroup = 1;
          _dumpIndex = 0;
        } else {
          finishDump(nullptr);  // success: emits CSV:END + DUMP done
          return;
        }
      }
      // Pace next Modbus/WS chunk
      _dumpNextChunkAt = millis() + DUMP_CHUNK_GAP_MS;
      return;
    }

    // Waiting between chunks (non-blocking)
    if ((int32_t)(millis() - _dumpNextChunkAt) < 0) return;

    if (!clientStillValid()) {
      finishDump("client gone");
      return;
    }
    uint8_t remain = (uint8_t)(PARAM_INDEX_MAX - _dumpIndex + 1);
    uint8_t qty = remain > 12 ? 12 : remain;
    if (!_vfd.requestDumpChunk(_dumpGroup, _dumpIndex, qty)) {
      finishDump("queue failed");
      return;
    }
    _dumpChunk = qty;
    _dumpAwaiting = true;
  }
}
