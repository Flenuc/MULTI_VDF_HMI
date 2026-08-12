/**
 * @file CliEngine.h
 * @brief Multi-channel CLI (USB + WebSocket) over non-blocking Modbus jobs.
 *
 * Commands (engineering floats for r/w unless "raw" used):
 *   help | ping | dump
 *   r0 <ii> | w0 <ii> <float> | r1 <ii> | w1 <ii> <float>
 *   raw <addr> | slave <id>
 *   start | stop | estop | reset
 *   set <pct>          — freq setpoint % of fmax → 0x1000
 *   stream on|off      — JSON telemetry ~1 Hz to all WS clients
 *   wifi status | wifi set | wifi profile list|save|use|delete | wifi reconnect
 *   mqtt status | mqtt set <host> [port] | mqtt user <u> <p> | mqtt enable|disable
 */
#pragma once

#include "Config.h"
#include "ResponseChannel.h"
#include "SajPdm30.h"
#include "ModbusRtuMaster.h"

class TelemetryService;  // fwd
class NetworkService;    // fwd

class CliEngine {
public:
  CliEngine(SajPdm30 &vfd, ModbusRtuMaster &mb, IReplySink &sink)
      : _vfd(vfd), _mb(mb), _sink(sink) {}

  void setTelemetry(TelemetryService *tel) { _tel = tel; }
  void setNetwork(NetworkService *net) { _net = net; }

  /** Feed one complete line (no CR/LF) from a channel. */
  void handleLine(const Channel &ch, const char *line);

  /** Advance async jobs; call every loop. */
  void poll();

  bool streamEnabled() const { return _streamOn; }
  void setStreamEnabled(bool on) { _streamOn = on; }

  bool isBusy() const { return _job != Job::None || _mb.isBusy(); }

private:
  enum class Job : uint8_t {
    None = 0,
    WaitRead,
    WaitWrite,
    Dump,
    Ping,
    WaitOp,  // start/stop/set
  };

  SajPdm30 &_vfd;
  ModbusRtuMaster &_mb;
  IReplySink &_sink;
  TelemetryService *_tel = nullptr;
  NetworkService   *_net = nullptr;

  Channel _jobCh = Channel::usb();
  Job     _job = Job::None;
  bool    _streamOn = false;

  // dump / ping state
  uint8_t  _dumpGroup = 0;
  uint8_t  _dumpIndex = 0;
  uint8_t  _dumpChunk = 0;
  bool     _dumpAwaiting = false;
  uint32_t _dumpNextChunkAt = 0;  // millis gate between chunks (WS pacing)
  bool     _streamPausedForDump = false;
  bool     _streamPausedForCmd = false;  // pause tel for r0/ping/etc., restore after job
  bool     _hasPending = false;          // one queued Modbus CLI line while bus busy
  Channel  _pendingCh = Channel::usb();
  char     _pendingLine[CLI_LINE_MAX] = {};
  uint8_t  _pingStep = 0;

  // context for single r/w print
  uint8_t  _ctxGroup = 0;
  uint8_t  _ctxIndex = 0;
  uint16_t _ctxAddr = 0;
  bool     _ctxIsParam = false;
  bool     _ctxScaled = true;
  float    _ctxEng = 0.0f;

  char _reply[CLI_REPLY_MAX];
  char _dumpBatch[DUMP_BATCH_MAX];

  void replyf(const Channel &ch, const char *fmt, ...);
  void printHelp(const Channel &ch);
  void dispatch(const Channel &ch, int argc, char **argv);
  void pollJob();
  void restoreStreamIfNeeded();
  bool clientStillValid() const;
  void cancelJob(const char *reason);
  void finishDump(const char *errMsg);
  void appendDumpCsvLine(size_t &pos, uint8_t group, uint8_t idx, bool ok,
                         uint16_t raw);
};
