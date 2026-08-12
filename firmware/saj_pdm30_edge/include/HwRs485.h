#pragma once

#include "Config.h"

class HwRs485 {
public:
  void begin() {
#if PIN_RS485_DE >= 0
    pinMode(PIN_RS485_DE, OUTPUT);
    digitalWrite(PIN_RS485_DE, LOW);
#endif
#if PIN_ACT_LED >= 0
    pinMode(PIN_ACT_LED, OUTPUT);
    digitalWrite(PIN_ACT_LED, LOW);
#endif
    RS485_UART.begin(RS485_BAUD, RS485_CONFIG, PIN_RS485_RX, PIN_RS485_TX);
    while (RS485_UART.available()) (void)RS485_UART.read();
  }

  HardwareSerial &uart() { return RS485_UART; }

  void setTransmit(bool enable) {
#if PIN_RS485_DE >= 0 && !RS485_AUTO_DIRECTION
    digitalWrite(PIN_RS485_DE, enable ? HIGH : LOW);
#else
    (void)enable;  // auto-direction transceiver or half-duplex HW
#endif
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
  bool     _ledActive = false;
  uint32_t _ledOffAt  = 0;
};
