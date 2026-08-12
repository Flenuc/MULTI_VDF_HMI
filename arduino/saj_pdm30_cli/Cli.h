/**
 * @file Cli.h
 * @brief Non-blocking USB serial CLI for SAJ PDM-30 master
 *
 * Commands:
 *   help | h
 *   ping | status
 *   dump                 — read all P0-00..47 and P1-00..47 (chunked, async)
 *   r0 <ii>              — read  P0-ii
 *   w0 <ii> <raw>        — write P0-ii = raw
 *   r1 <ii>              — read  P1-ii
 *   w1 <ii> <raw>        — write P1-ii = raw
 *   raw <addr>           — read holding (hex 0x.. or dec)
 *   slave <id>           — set Modbus slave id (runtime)
 */

#pragma once

#include "SajPdm30.h"

class Cli {
public:
  Cli(SajPdm30 &vfd, ModbusRtuMaster &mb) : _vfd(vfd), _mb(mb) {}

  void begin() {
    Serial.begin(USB_BAUD);
    // Non-blocking wait for USB: just print when first poll runs
    _bootPrinted = false;
    _lineLen = 0;
    _job = Job::None;
  }

  void poll() {
    if (!_bootPrinted) {
      // Print banner once USB is up (millis > 0 is enough; no delay)
      if (millis() > 200) {
        printBanner();
        _bootPrinted = true;
      }
    }

    // Progress async jobs first
    pollJob();

    // Accept new input only when no job pending and modbus idle
    while (Serial.available()) {
      char c = (char)Serial.read();
      if (c == '\r') continue;
      if (c == '\n') {
        _line[_lineLen] = '\0';
        if (_lineLen > 0) {
          if (_job != Job::None || _mb.isBusy()) {
            Serial.println(F("ERR: busy — wait for current operation"));
          } else {
            handleLine(_line);
          }
        }
        _lineLen = 0;
        if (_job == Job::None && !_mb.isBusy()) {
          Serial.print(F("> "));
        }
      } else if (_lineLen + 1 < CLI_LINE_MAX) {
        // basic filter: printable + tab
        if (c >= 32 && c < 127) {
          _line[_lineLen++] = c;
        }
      } else {
        // overflow — discard line
        _lineLen = 0;
        Serial.println(F("ERR: line too long"));
      }
    }
  }

private:
  enum class Job : uint8_t {
    None = 0,
    WaitSingleRead,
    WaitSingleWrite,
    Dump,
    Ping,
  };

  SajPdm30 &_vfd;
  ModbusRtuMaster &_mb;

  char _line[CLI_LINE_MAX];
  size_t _lineLen = 0;
  bool _bootPrinted = false;

  Job _job = Job::None;
  // dump state
  uint8_t _dumpGroup = 0;
  uint8_t _dumpIndex = 0;
  uint8_t _dumpChunk = 0;
  bool    _dumpAwaiting = false;
  // context for single r/w print
  uint8_t  _ctxGroup = 0;
  uint8_t  _ctxIndex = 0;
  uint16_t _ctxAddr  = 0;
  bool     _ctxIsParam = false;

  void printBanner() {
    Serial.println();
    Serial.println(F("=== SAJ PDM-30 ESP32 Master (CLI) ==="));
    Serial.printf("RS485 TX=%d RX=%d DE=%d LED=%d | slave=%u @ %lu 8N1\n",
                  PIN_RS485_TX, PIN_RS485_RX, PIN_RS485_DE, PIN_ACT_LED,
                  (unsigned)_vfd.slaveId(), (unsigned long)RS485_BAUD);
    Serial.println(F("Map: P0-ii→0x00ii  P1-ii→0x01ii  (discovered)"));
    Serial.println(F("Type 'help' for commands."));
    Serial.print(F("> "));
  }

  void printHelp() {
    Serial.println(F("help              this help"));
    Serial.println(F("ping | status     link + status regs"));
    Serial.println(F("dump              read all P0/P1 EEPROM params"));
    Serial.println(F("r0 <ii>           read  P0-ii   (ii=0..47)"));
    Serial.println(F("w0 <ii> <raw>     write P0-ii"));
    Serial.println(F("r1 <ii>           read  P1-ii"));
    Serial.println(F("w1 <ii> <raw>     write P1-ii"));
    Serial.println(F("raw <addr>        read holding (0xHEX or decimal)"));
    Serial.println(F("slave <id>        set Modbus slave id 1..247"));
    Serial.println(F("Values are RAW register integers (see manual units)."));
  }

  static bool parseU16(const char *s, uint16_t &out) {
    if (!s || !*s) return false;
    char *end = nullptr;
    unsigned long v = strtoul(s, &end, 0);  // accepts 0x / decimal
    if (end == s || *end != '\0') return false;
    if (v > 0xFFFFUL) return false;
    out = (uint16_t)v;
    return true;
  }

  static bool parseU8(const char *s, uint8_t &out) {
    uint16_t v;
    if (!parseU16(s, v) || v > 255) return false;
    out = (uint8_t)v;
    return true;
  }

  void handleLine(char *line) {
    // tokenize in-place
    char *argv[6];
    int argc = 0;
    char *p = line;
    while (*p && argc < 6) {
      while (*p == ' ' || *p == '\t') p++;
      if (!*p) break;
      argv[argc++] = p;
      while (*p && *p != ' ' && *p != '\t') p++;
      if (*p) *p++ = '\0';
    }
    if (argc == 0) return;

    if (strcmp(argv[0], "help") == 0 || strcmp(argv[0], "h") == 0) {
      printHelp();
      return;
    }
    if (strcmp(argv[0], "ping") == 0 || strcmp(argv[0], "status") == 0) {
      startPing();
      return;
    }
    if (strcmp(argv[0], "dump") == 0) {
      startDump();
      return;
    }
    if (strcmp(argv[0], "slave") == 0) {
      if (argc < 2) { Serial.println(F("usage: slave <id>")); return; }
      uint8_t id;
      if (!parseU8(argv[1], id) || id < 1 || id > 247) {
        Serial.println(F("ERR: slave id 1..247"));
        return;
      }
      _vfd.setSlaveId(id);
      Serial.printf("slave id = %u\n", id);
      return;
    }
    if (strcmp(argv[0], "r0") == 0 || strcmp(argv[0], "r1") == 0) {
      if (argc < 2) { Serial.println(F("usage: r0|r1 <ii>")); return; }
      uint8_t ii;
      if (!parseU8(argv[1], ii) || ii > PARAM_INDEX_MAX) {
        Serial.println(F("ERR: index 0..47"));
        return;
      }
      uint8_t g = (argv[0][1] == '1') ? 1 : 0;
      startParamRead(g, ii);
      return;
    }
    if (strcmp(argv[0], "w0") == 0 || strcmp(argv[0], "w1") == 0) {
      if (argc < 3) { Serial.println(F("usage: w0|w1 <ii> <raw>")); return; }
      uint8_t ii;
      uint16_t raw;
      if (!parseU8(argv[1], ii) || ii > PARAM_INDEX_MAX) {
        Serial.println(F("ERR: index 0..47"));
        return;
      }
      if (!parseU16(argv[2], raw)) {
        Serial.println(F("ERR: invalid raw value"));
        return;
      }
      uint8_t g = (argv[0][1] == '1') ? 1 : 0;
      startParamWrite(g, ii, raw);
      return;
    }
    if (strcmp(argv[0], "raw") == 0) {
      if (argc < 2) { Serial.println(F("usage: raw <addr>")); return; }
      uint16_t addr;
      if (!parseU16(argv[1], addr)) {
        Serial.println(F("ERR: invalid address"));
        return;
      }
      startRawRead(addr);
      return;
    }

    Serial.println(F("ERR: unknown command — type help"));
  }

  void startParamRead(uint8_t g, uint8_t i) {
    _ctxGroup = g;
    _ctxIndex = i;
    _ctxAddr = paramAddress(g, i);
    _ctxIsParam = true;
    if (!_vfd.requestReadParam(g, i)) {
      Serial.println(F("ERR: cannot queue read"));
      return;
    }
    _job = Job::WaitSingleRead;
  }

  void startParamWrite(uint8_t g, uint8_t i, uint16_t raw) {
    _ctxGroup = g;
    _ctxIndex = i;
    _ctxAddr = paramAddress(g, i);
    _ctxIsParam = true;
    if (!_vfd.requestWriteParam(g, i, raw)) {
      Serial.println(F("ERR: cannot queue write"));
      return;
    }
    _job = Job::WaitSingleWrite;
  }

  void startRawRead(uint16_t addr) {
    _ctxAddr = addr;
    _ctxIsParam = false;
    if (!_vfd.requestReadHolding(addr, 1)) {
      Serial.println(F("ERR: cannot queue read"));
      return;
    }
    _job = Job::WaitSingleRead;
  }

  void startPing() {
    _dumpIndex = 0;  // reuse as step: 0=status,1=freq,2=press
    _dumpAwaiting = false;
    _job = Job::Ping;
  }

  void startDump() {
    Serial.println(F("DUMP begin P0-00..P0-47, P1-00..P1-47"));
    Serial.println(F("CSV:param,addr,raw,name"));
    _dumpGroup = 0;
    _dumpIndex = 0;
    _dumpChunk = 0;
    _dumpAwaiting = false;
    _job = Job::Dump;
  }

  void pollJob() {
    if (_job == Job::None) return;

    // Wait for in-flight Modbus to complete
    if (_mb.isBusy()) return;

    if (_job == Job::WaitSingleRead) {
      // Result of last request
      printMbOutcomeRead();
      _job = Job::None;
      Serial.print(F("> "));
      return;
    }

    if (_job == Job::WaitSingleWrite) {
      printMbOutcomeWrite();
      _job = Job::None;
      Serial.print(F("> "));
      return;
    }

    if (_job == Job::Ping) {
      pollPing();
      return;
    }

    if (_job == Job::Dump) {
      pollDump();
      return;
    }
  }

  void printMbOutcomeRead() {
    MbResult r = _mb.lastResult();
    if (r != MbResult::Ok) {
      Serial.printf("ERR: %s", _mb.resultStr());
      if (r == MbResult::Exception)
        Serial.printf(" code=0x%02X", _mb.lastException());
      Serial.println();
      return;
    }
    uint16_t v = _mb.lastValue();
    if (_ctxIsParam) {
      Serial.printf("P%u-%02u @0x%04X = %u (0x%04X)  \"%s\"\n",
                    _ctxGroup, _ctxIndex, _ctxAddr, v, v,
                    SajPdm30::paramName(_ctxGroup, _ctxIndex));
    } else {
      Serial.printf("0x%04X = %u (0x%04X) signed=%d\n",
                    _ctxAddr, v, v, (int16_t)v);
    }
  }

  void printMbOutcomeWrite() {
    MbResult r = _mb.lastResult();
    if (r != MbResult::Ok) {
      Serial.printf("ERR: %s", _mb.resultStr());
      if (r == MbResult::Exception)
        Serial.printf(" code=0x%02X", _mb.lastException());
      Serial.println();
      return;
    }
    Serial.printf("OK write P%u-%02u @0x%04X = %u\n",
                  _ctxGroup, _ctxIndex, _ctxAddr, _mb.lastValue());
  }

  void pollPing() {
    if (!_dumpAwaiting) {
      bool ok = false;
      if (_dumpIndex == 0) ok = _vfd.requestReadHolding(REG_STATUS, 1);
      else if (_dumpIndex == 1) ok = _vfd.requestReadHolding(REG_RUN_FREQ, 1);
      else if (_dumpIndex == 2) ok = _vfd.requestReadHolding(REG_SET_PRESS, 2);
      if (!ok) {
        Serial.println(F("ERR: cannot queue ping"));
        _job = Job::None;
        Serial.print(F("> "));
        return;
      }
      _dumpAwaiting = true;
      return;
    }

    // completed
    _dumpAwaiting = false;
    MbResult r = _mb.lastResult();
    if (r != MbResult::Ok) {
      Serial.printf("PING step %u FAIL: %s\n", _dumpIndex, _mb.resultStr());
      _job = Job::None;
      Serial.print(F("> "));
      return;
    }

    if (_dumpIndex == 0) {
      uint16_t st = _mb.lastValue();
      const char *n = (st == 1) ? "FWD" : (st == 2) ? "REV" : (st == 3) ? "STOP" : "?";
      Serial.printf("Status 0x3000 = %u (%s)\n", st, n);
    } else if (_dumpIndex == 1) {
      Serial.printf("Run freq 0x1001 = %.2f Hz\n", _mb.lastValue() / 100.0f);
    } else if (_dumpIndex == 2) {
      const uint16_t *v = _mb.lastValues();
      Serial.printf("Set press 0x100F = %.1f bar\n", v[0] / 10.0f);
      Serial.printf("Fb  press 0x1010 = %.1f bar\n", v[1] / 10.0f);
      Serial.println(F("Link OK"));
      _job = Job::None;
      Serial.print(F("> "));
      return;
    }
    _dumpIndex++;
  }

  void pollDump() {
    if (_dumpAwaiting) {
      // process completed chunk
      _dumpAwaiting = false;
      MbResult r = _mb.lastResult();
      uint8_t qty = _dumpChunk;
      uint8_t start = _dumpIndex;

      if (r != MbResult::Ok) {
        // print ERRORs for this chunk range, then advance
        for (uint8_t i = 0; i < qty; i++) {
          uint8_t idx = start + i;
          Serial.printf("CSV:P%u-%02u,0x%04X,ERROR,\"%s\"\n",
                        _dumpGroup, idx, paramAddress(_dumpGroup, idx),
                        SajPdm30::paramName(_dumpGroup, idx));
        }
      } else {
        const uint16_t *vals = _mb.lastValues();
        for (uint8_t i = 0; i < qty; i++) {
          uint8_t idx = start + i;
          Serial.printf("CSV:P%u-%02u,0x%04X,%u,\"%s\"\n",
                        _dumpGroup, idx, paramAddress(_dumpGroup, idx),
                        vals[i], SajPdm30::paramName(_dumpGroup, idx));
        }
      }

      _dumpIndex = start + qty;
      if (_dumpIndex > PARAM_INDEX_MAX) {
        if (_dumpGroup == 0) {
          _dumpGroup = 1;
          _dumpIndex = 0;
        } else {
          Serial.println(F("CSV:END"));
          Serial.println(F("DUMP done"));
          _job = Job::None;
          Serial.print(F("> "));
          return;
        }
      }
    }

    // queue next chunk
    uint8_t remain = (uint8_t)(PARAM_INDEX_MAX - _dumpIndex + 1);
    uint8_t qty = remain > 12 ? 12 : remain;
    if (!_vfd.requestDumpChunk(_dumpGroup, _dumpIndex, qty)) {
      Serial.println(F("ERR: dump queue failed"));
      _job = Job::None;
      Serial.print(F("> "));
      return;
    }
    _dumpChunk = qty;
    _dumpAwaiting = true;
  }
};
