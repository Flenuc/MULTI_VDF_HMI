/**
 * Non-blocking USB serial line collector → CliEngine.
 */
#pragma once

#include "Config.h"
#include "CliEngine.h"
#include "ResponseChannel.h"

class UsbCli {
public:
  explicit UsbCli(CliEngine &cli) : _cli(cli) {}

  void begin() {
    Serial.begin(USB_BAUD);
    _lineLen = 0;
  }

  void poll() {
    while (Serial.available()) {
      char c = (char)Serial.read();
      if (c == '\r') continue;
      if (c == '\n') {
        _line[_lineLen] = '\0';
        if (_lineLen > 0) {
          _cli.handleLine(Channel::usb(), _line);
        }
        _lineLen = 0;
      } else if (_lineLen + 1 < CLI_LINE_MAX) {
        if (c >= 32 && c < 127) _line[_lineLen++] = c;
      } else {
        _lineLen = 0;  // overflow discard
      }
    }
  }

private:
  CliEngine &_cli;
  char   _line[CLI_LINE_MAX];
  size_t _lineLen = 0;
};
