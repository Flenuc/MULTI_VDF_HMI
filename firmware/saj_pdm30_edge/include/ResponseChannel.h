/**
 * @file ResponseChannel.h
 * @brief Routes CLI replies to USB Serial and/or MQTT.
 */
#pragma once

#include <stdint.h>

enum class ChannelKind : uint8_t {
  UsbSerial = 0,
  Mqtt      = 1,  // response published on .../rsp
  Broadcast = 2,  // telemetry + system → MQTT telemetry/status + Serial mirror
};

struct Channel {
  ChannelKind kind;
  uint32_t    reserved;  // unused (was WS client id)

  static Channel usb() {
    Channel c{ChannelKind::UsbSerial, 0};
    return c;
  }

  static Channel mqtt() {
    Channel c{ChannelKind::Mqtt, 0};
    return c;
  }

  static Channel broadcast() {
    Channel c{ChannelKind::Broadcast, 0};
    return c;
  }

  bool isMqtt() const { return kind == ChannelKind::Mqtt; }
  bool isUsb() const { return kind == ChannelKind::UsbSerial; }
};

class IReplySink {
public:
  virtual ~IReplySink() = default;
  virtual void reply(const Channel &ch, const char *text) = 0;
  /** True if MQTT (or generic remote) channel can accept replies. */
  virtual bool isRemoteAlive() const = 0;
};
