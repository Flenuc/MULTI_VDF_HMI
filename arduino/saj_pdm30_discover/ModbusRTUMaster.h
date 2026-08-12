/**
 * Minimal Modbus RTU master for ESP32 HardwareSerial + RS485 DE pin.
 * Supports FC 0x03 (read holding) and FC 0x06 (write single register).
 */

#pragma once

#include <Arduino.h>
#include "config.h"

class ModbusRTUMaster {
public:
  ModbusRTUMaster(HardwareSerial &serial = RS485_SERIAL)
    : _serial(serial), _lastError(0) {}

  void begin(uint32_t baud = VFD_BAUD, uint32_t config = VFD_CONFIG) {
#if !RS485_AUTO_DIRECTION
    pinMode(RS485_DE_PIN, OUTPUT);
    setTx(false);
#endif
#ifdef ACTIVITY_LED_PIN
    pinMode(ACTIVITY_LED_PIN, OUTPUT);
    digitalWrite(ACTIVITY_LED_PIN, LOW);
#endif
    _serial.begin(baud, config, RS485_RX_PIN, RS485_TX_PIN);
    delay(50);
    while (_serial.available()) _serial.read();
  }

  /** Read holding registers. Returns true on success; values in out[]. */
  bool readHolding(uint8_t slave, uint16_t addr, uint16_t qty, uint16_t *out) {
    if (qty == 0 || qty > 125 || out == nullptr) {
      _lastError = 0xFF;
      return false;
    }
    uint8_t req[8];
    req[0] = slave;
    req[1] = 0x03;
    req[2] = (uint8_t)(addr >> 8);
    req[3] = (uint8_t)(addr & 0xFF);
    req[4] = (uint8_t)(qty >> 8);
    req[5] = (uint8_t)(qty & 0xFF);
    uint16_t crc = crc16(req, 6);
    req[6] = (uint8_t)(crc & 0xFF);        // CRC lo
    req[7] = (uint8_t)(crc >> 8);          // CRC hi

    if (!transact(req, 8, 5 + qty * 2)) return false;

    // response: [id][fc][byteCount][data...][crc lo][crc hi]
    if (_rx[1] & 0x80) {
      _lastError = _rx[2];
      return false;
    }
    if (_rx[1] != 0x03 || _rx[2] != qty * 2) {
      _lastError = 0xFE;
      return false;
    }
    for (uint16_t i = 0; i < qty; i++) {
      out[i] = ((uint16_t)_rx[3 + i * 2] << 8) | _rx[4 + i * 2];
    }
    _lastError = 0;
    return true;
  }

  /** Write single holding register (FC 06). */
  bool writeSingle(uint8_t slave, uint16_t addr, uint16_t value) {
    uint8_t req[8];
    req[0] = slave;
    req[1] = 0x06;
    req[2] = (uint8_t)(addr >> 8);
    req[3] = (uint8_t)(addr & 0xFF);
    req[4] = (uint8_t)(value >> 8);
    req[5] = (uint8_t)(value & 0xFF);
    uint16_t crc = crc16(req, 6);
    req[6] = (uint8_t)(crc & 0xFF);
    req[7] = (uint8_t)(crc >> 8);

    if (!transact(req, 8, 8)) return false;

    if (_rx[1] & 0x80) {
      _lastError = _rx[2];
      return false;
    }
    // echo check
    for (int i = 0; i < 6; i++) {
      if (_rx[i] != req[i]) {
        _lastError = 0xFD;
        return false;
      }
    }
    _lastError = 0;
    return true;
  }

  uint8_t lastError() const { return _lastError; }

  const char *lastErrorStr() const {
    switch (_lastError) {
      case 0:    return "OK";
      case 0x01: return "Illegal function";
      case 0x02: return "Illegal data address";
      case 0x03: return "Illegal data value";
      case 0x04: return "Slave device failure";
      case 0x06: return "Parameter modification invalid";
      case 0x07: return "System locked (password)";
      case 0x08: return "EEPROM busy";
      case 0xFE: return "Bad response format";
      case 0xFD: return "Write echo mismatch";
      case 0xFC: return "Timeout / no response";
      case 0xFB: return "CRC error";
      default:   return "Unknown error";
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
  HardwareSerial &_serial;
  uint8_t _rx[256];
  uint8_t _lastError;

  void setTx(bool enable) {
#if !RS485_AUTO_DIRECTION
    digitalWrite(RS485_DE_PIN, enable ? HIGH : LOW);
#endif
  }

  bool transact(const uint8_t *req, size_t reqLen, size_t expectedMin) {
    while (_serial.available()) _serial.read();

#ifdef ACTIVITY_LED_PIN
    digitalWrite(ACTIVITY_LED_PIN, HIGH);
#endif
    setTx(true);
    _serial.write(req, reqLen);
    _serial.flush();
    delayMicroseconds(MB_POST_TX_US);
    setTx(false);

    size_t got = 0;
    uint32_t t0 = millis();
    while (millis() - t0 < MB_RESPONSE_TIMEOUT_MS) {
      while (_serial.available() && got < sizeof(_rx)) {
        _rx[got++] = _serial.read();
        t0 = millis();  // sliding window after first byte
      }
      if (got >= 5) {
        // exception frame is 5 bytes
        if (_rx[1] & 0x80) {
          if (got >= 5) break;
        } else if (got >= expectedMin) {
          break;
        }
      }
      delay(1);
    }
#ifdef ACTIVITY_LED_PIN
    digitalWrite(ACTIVITY_LED_PIN, LOW);
#endif

    if (got < 5) {
      _lastError = 0xFC;
      return false;
    }

    uint16_t rxCrc = (uint16_t)_rx[got - 2] | ((uint16_t)_rx[got - 1] << 8);
    uint16_t calc = crc16(_rx, got - 2);
    if (rxCrc != calc) {
      _lastError = 0xFB;
      return false;
    }
    return true;
  }
};
