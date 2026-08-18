#pragma once

#include "Config.h"

/**
 * RS485 half-duplex helper.
 *
 * DevKit (SN75176B): software DE on PIN_RS485_DE, active-high by default.
 * Guition (MAX485 auto): PIN_RS485_DE < 0 or RS485_AUTO_DIRECTION=1.
 *
 * Runtime knobs (field diagnosis):
 *   setDeActiveHigh(false)  — invert DE if module expects active-low TX
 *   rebegin(tx,rx)          — remap UART pins (test TX/RX swap)
 */
class HwRs485 {
public:
  void begin() {
    _txPin = PIN_RS485_TX;
    _rxPin = PIN_RS485_RX;
    _dePin = PIN_RS485_DE;
    _deActiveHigh = true;
    _autoDir = (RS485_AUTO_DIRECTION != 0) || (_dePin < 0);
#if PIN_RS485_DE >= 0
    pinMode(_dePin, OUTPUT);
    digitalWrite(_dePin, _rxLevel());
#endif
#if PIN_ACT_LED >= 0
    pinMode(PIN_ACT_LED, OUTPUT);
    digitalWrite(PIN_ACT_LED, LOW);
#endif
    RS485_UART.begin(RS485_BAUD, RS485_CONFIG, _rxPin, _txPin);
    while (RS485_UART.available()) (void)RS485_UART.read();
  }

  HardwareSerial &uart() { return RS485_UART; }

  void setTransmit(bool enable) {
    if (_autoDir || _dePin < 0) {
      (void)enable;
      return;
    }
    digitalWrite(_dePin, enable ? _txLevel() : _rxLevel());
  }

  void setDeActiveHigh(bool activeHigh) {
    _deActiveHigh = activeHigh;
    if (!_autoDir && _dePin >= 0) {
      digitalWrite(_dePin, _rxLevel());  // idle = receive
    }
  }

  bool deActiveHigh() const { return _deActiveHigh; }
  bool autoDirection() const { return _autoDir; }
  int txPin() const { return _txPin; }
  int rxPin() const { return _rxPin; }
  int dePin() const { return _dePin; }

  /** Remap UART pins and restart (e.g. swap TX/RX for wiring diagnosis). */
  void rebegin(int txPin, int rxPin) {
    _txPin = txPin;
    _rxPin = rxPin;
    RS485_UART.end();
    delay(2);
    RS485_UART.begin(RS485_BAUD, RS485_CONFIG, _rxPin, _txPin);
    while (RS485_UART.available()) (void)RS485_UART.read();
    if (!_autoDir && _dePin >= 0) {
      digitalWrite(_dePin, _rxLevel());
    }
  }

  void blink(uint32_t ms = 40) {
#if PIN_ACT_LED >= 0
    digitalWrite(PIN_ACT_LED, HIGH);
    _ledOffAt = millis() + ms;
    _ledActive = true;
#else
    (void)ms;
#endif
  }

  void poll() {
#if PIN_ACT_LED >= 0
    if (_ledActive && (int32_t)(millis() - _ledOffAt) >= 0) {
      digitalWrite(PIN_ACT_LED, LOW);
      _ledActive = false;
    }
#endif
  }

private:
  int  _txPin = PIN_RS485_TX;
  int  _rxPin = PIN_RS485_RX;
  int  _dePin = PIN_RS485_DE;
  bool _deActiveHigh = true;
  bool _autoDir = false;
  bool     _ledActive = false;
  uint32_t _ledOffAt  = 0;

  int _txLevel() const { return _deActiveHigh ? HIGH : LOW; }
  int _rxLevel() const { return _deActiveHigh ? LOW : HIGH; }
};
