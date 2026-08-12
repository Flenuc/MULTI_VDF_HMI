/**
 * @file HwRs485.h
 * @brief RS485 transceiver control (DE/RE) + activity LED — non-blocking
 */

#pragma once

#include "Config.h"

class HwRs485 {
public:
  void begin() {
    pinMode(PIN_RS485_DE, OUTPUT);
    digitalWrite(PIN_RS485_DE, LOW);  // receive by default
    pinMode(PIN_ACT_LED, OUTPUT);
    digitalWrite(PIN_ACT_LED, LOW);

    RS485_SERIAL.begin(RS485_BAUD, RS485_CONFIG, PIN_RS485_RX, PIN_RS485_TX);
    // Drain any garbage without delay()
    while (RS485_SERIAL.available()) {
      (void)RS485_SERIAL.read();
    }
  }

  HardwareSerial &uart() { return RS485_SERIAL; }

  void setTransmit(bool enable) {
    digitalWrite(PIN_RS485_DE, enable ? HIGH : LOW);
  }

  bool isTransmit() const {
    return digitalRead(PIN_RS485_DE) == HIGH;
  }

  /** Pulse LED for `ms` milliseconds from now (non-blocking). */
  void blink(uint32_t ms = 40) {
    digitalWrite(PIN_ACT_LED, HIGH);
    _ledOffAt = millis() + ms;
    _ledActive = true;
  }

  /** Call every loop() — turns LED off when timer expires. */
  void poll() {
    if (_ledActive && (int32_t)(millis() - _ledOffAt) >= 0) {
      digitalWrite(PIN_ACT_LED, LOW);
      _ledActive = false;
    }
  }

private:
  // Alias: use Serial2 bound to our pins
  HardwareSerial &RS485_SERIAL = Serial2;
  bool     _ledActive = false;
  uint32_t _ledOffAt  = 0;
};
