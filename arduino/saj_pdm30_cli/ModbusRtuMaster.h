/**
 * @file ModbusRtuMaster.h
 * @brief Non-blocking Modbus RTU master (FC 0x03 / 0x06) over RS485
 *
 * State machine driven by poll() + millis(). No delay().
 */

#pragma once

#include "HwRs485.h"

enum class MbResult : uint8_t {
  Idle = 0,
  Busy,
  Ok,
  Timeout,
  CrcError,
  Exception,
  BadFrame,
  BusyReject,   // new request while previous still running
};

enum class MbOp : uint8_t {
  None = 0,
  ReadHolding,
  WriteSingle,
};

class ModbusRtuMaster {
public:
  explicit ModbusRtuMaster(HwRs485 &bus) : _bus(bus) {}

  void begin() {
    _state = State::Idle;
    _result = MbResult::Idle;
  }

  bool isBusy() const { return _state != State::Idle; }

  MbResult lastResult() const { return _result; }
  uint8_t  lastException() const { return _exception; }
  uint16_t lastValue() const { return _value; }
  uint8_t  lastQty() const { return _qty; }
  const uint16_t *lastValues() const { return _values; }

  const char *resultStr() const {
    switch (_result) {
      case MbResult::Idle:       return "Idle";
      case MbResult::Busy:       return "Busy";
      case MbResult::Ok:         return "OK";
      case MbResult::Timeout:    return "Timeout";
      case MbResult::CrcError:   return "CRC error";
      case MbResult::Exception:  return "Modbus exception";
      case MbResult::BadFrame:   return "Bad frame";
      case MbResult::BusyReject: return "Busy (request rejected)";
      default:                   return "?";
    }
  }

  /**
   * Queue FC03 read of `qty` holding registers at `addr`.
   * Returns false if busy or invalid args.
   */
  bool readHolding(uint8_t slave, uint16_t addr, uint8_t qty) {
    if (qty == 0 || qty > kMaxQty) return false;
    if (_state != State::Idle) {
      _result = MbResult::BusyReject;
      return false;
    }
    _op = MbOp::ReadHolding;
    _slave = slave;
    _addr = addr;
    _qty = qty;
    _txLen = 0;
    _txBuf[_txLen++] = slave;
    _txBuf[_txLen++] = 0x03;
    _txBuf[_txLen++] = (uint8_t)(addr >> 8);
    _txBuf[_txLen++] = (uint8_t)(addr & 0xFF);
    _txBuf[_txLen++] = 0x00;
    _txBuf[_txLen++] = qty;
    appendCrc(_txBuf, _txLen);
    _txLen += 2;
    startTx();
    return true;
  }

  /** Queue FC06 write single register. */
  bool writeSingle(uint8_t slave, uint16_t addr, uint16_t value) {
    if (_state != State::Idle) {
      _result = MbResult::BusyReject;
      return false;
    }
    _op = MbOp::WriteSingle;
    _slave = slave;
    _addr = addr;
    _qty = 1;
    _value = value;
    _txLen = 0;
    _txBuf[_txLen++] = slave;
    _txBuf[_txLen++] = 0x06;
    _txBuf[_txLen++] = (uint8_t)(addr >> 8);
    _txBuf[_txLen++] = (uint8_t)(addr & 0xFF);
    _txBuf[_txLen++] = (uint8_t)(value >> 8);
    _txBuf[_txLen++] = (uint8_t)(value & 0xFF);
    appendCrc(_txBuf, _txLen);
    _txLen += 2;
    startTx();
    return true;
  }

  /** Advance state machine. Call from loop() as often as possible. */
  void poll() {
    const uint32_t now = millis();

    switch (_state) {
      case State::Idle:
        break;

      case State::TxWaitEnd: {
        // Wait until estimated end of physical TX, then release DE → RX
        if ((int32_t)(now - _txEndAt) >= 0) {
          _bus.setTransmit(false);
          // clear RX buffer after direction switch
          while (_bus.uart().available()) (void)_bus.uart().read();
          _rxLen = 0;
          _tFirstByte = 0;
          _deadline = now + MB_RESPONSE_TIMEOUT_MS;
          _state = State::WaitRx;
        }
        break;
      }

      case State::WaitRx: {
        while (_bus.uart().available() && _rxLen < sizeof(_rxBuf)) {
          _rxBuf[_rxLen++] = (uint8_t)_bus.uart().read();
          _tLastByte = now;
          if (_tFirstByte == 0) _tFirstByte = now;
        }

        if (_rxLen > 0) {
          // Inter-byte idle: if we have a plausible full frame, finish
          if (frameLooksComplete() &&
              (int32_t)(now - _tLastByte) >= (int32_t)MB_INTERFRAME_MS) {
            finishRx();
            break;
          }
        }

        if ((int32_t)(now - _deadline) >= 0) {
          // timeout — maybe partial frame
          if (_rxLen >= 5) {
            finishRx();
          } else {
            complete(MbResult::Timeout);
          }
        }
        break;
      }
    }
  }

  static uint16_t crc16(const uint8_t *data, size_t len) {
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len; i++) {
      crc ^= data[i];
      for (int b = 0; b < 8; b++) {
        if (crc & 1) crc = (crc >> 1) ^ 0xA001;
        else crc >>= 1;
      }
    }
    return crc;
  }

private:
  static const uint8_t kMaxQty = 12;  // SAJ manual: max continuous param read = 12
  static const size_t  kTxMax  = 8;
  static const size_t  kRxMax  = 5 + kMaxQty * 2 + 2;

  enum class State : uint8_t { Idle, TxWaitEnd, WaitRx };

  HwRs485 &_bus;
  State    _state = State::Idle;
  MbResult _result = MbResult::Idle;
  MbOp     _op = MbOp::None;

  uint8_t  _slave = 0;
  uint16_t _addr  = 0;
  uint8_t  _qty   = 0;
  uint16_t _value = 0;
  uint8_t  _exception = 0;
  uint16_t _values[kMaxQty] = {};

  uint8_t  _txBuf[kTxMax];
  size_t   _txLen = 0;
  uint8_t  _rxBuf[kRxMax];
  size_t   _rxLen = 0;

  uint32_t _txEndAt = 0;
  uint32_t _deadline = 0;
  uint32_t _tFirstByte = 0;
  uint32_t _tLastByte = 0;

  void appendCrc(uint8_t *buf, size_t lenWithoutCrc) {
    uint16_t c = crc16(buf, lenWithoutCrc);
    buf[lenWithoutCrc]     = (uint8_t)(c & 0xFF);
    buf[lenWithoutCrc + 1] = (uint8_t)(c >> 8);
  }

  void startTx() {
    _result = MbResult::Busy;
    _exception = 0;
    while (_bus.uart().available()) (void)_bus.uart().read();
    _bus.setTransmit(true);
    _bus.uart().write(_txBuf, _txLen);
    // Non-blocking: do not flush(); estimate wire time instead
    const uint32_t wireMs = mbFrameDurationMs(_txLen) + MB_POST_TX_GUARD_MS;
    _txEndAt = millis() + wireMs;
    _state = State::TxWaitEnd;
  }

  bool frameLooksComplete() {
    if (_rxLen < 5) return false;
    if (_rxBuf[1] & 0x80) {
      return _rxLen >= 5;  // exception: id fc ex crc crc
    }
    if (_op == MbOp::ReadHolding) {
      // id fc bc data... crc crc
      if (_rxLen < 3) return false;
      uint8_t bc = _rxBuf[2];
      return _rxLen >= (size_t)(3 + bc + 2);
    }
    if (_op == MbOp::WriteSingle) {
      return _rxLen >= 8;  // echo of request
    }
    return false;
  }

  void finishRx() {
    if (_rxLen < 5) {
      complete(MbResult::Timeout);
      return;
    }

    const uint16_t rxCrc = (uint16_t)_rxBuf[_rxLen - 2] |
                           ((uint16_t)_rxBuf[_rxLen - 1] << 8);
    const uint16_t calc  = crc16(_rxBuf, _rxLen - 2);
    if (rxCrc != calc) {
      complete(MbResult::CrcError);
      return;
    }

    if (_rxBuf[0] != _slave) {
      complete(MbResult::BadFrame);
      return;
    }

    if (_rxBuf[1] & 0x80) {
      _exception = _rxBuf[2];
      complete(MbResult::Exception);
      return;
    }

    if (_op == MbOp::ReadHolding) {
      if (_rxBuf[1] != 0x03 || _rxBuf[2] != _qty * 2) {
        complete(MbResult::BadFrame);
        return;
      }
      for (uint8_t i = 0; i < _qty; i++) {
        _values[i] = ((uint16_t)_rxBuf[3 + i * 2] << 8) | _rxBuf[4 + i * 2];
      }
      _value = _values[0];
      complete(MbResult::Ok);
      return;
    }

    if (_op == MbOp::WriteSingle) {
      if (_rxBuf[1] != 0x06 || _rxLen < 8) {
        complete(MbResult::BadFrame);
        return;
      }
      // echo check
      for (int i = 0; i < 6; i++) {
        if (_rxBuf[i] != _txBuf[i]) {
          complete(MbResult::BadFrame);
          return;
        }
      }
      _value = ((uint16_t)_rxBuf[4] << 8) | _rxBuf[5];
      complete(MbResult::Ok);
      return;
    }

    complete(MbResult::BadFrame);
  }

  void complete(MbResult r) {
    _result = r;
    _state = State::Idle;
    _op = MbOp::None;
    // LED pulse on every completed transaction (success or fail)
    _bus.blink(r == MbResult::Ok ? 30 : 80);
  }
};
