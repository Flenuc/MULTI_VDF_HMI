/**
 * Per-board serial derived from chip eFuse MAC (stable across reboot).
 *
 * Examples (last 3 MAC bytes):
 *   id / mDNS / MQTT topic node:  vf-7cf194
 *   BT advertise name:            VF-7CF194
 *   MQTT client id:               vf-7cf194  (same as id)
 *
 * Topics become: saj/pdm30/vf-7cf194/{cmd,rsp,telemetry,status}
 * Optional override via CLI `id set <slug>` (persisted NVS).
 */
#pragma once

#include <stdint.h>
#include <stddef.h>

#ifndef EDGE_ID_MAX
#define EDGE_ID_MAX 24
#endif

class DeviceIdentity {
public:
  /** Load NVS or generate from MAC. Call once early in setup(). */
  void begin();

  const char *id() const { return _id; }           // vf-7cf194
  const char *btName() const { return _btName; }   // VF-7CF194
  const char *mqttClientId() const { return _id; }

  /** Full MAC string aa:bb:cc:dd:ee:ff */
  const char *macStr() const { return _macStr; }

  /**
   * Override id (a-z0-9- only, 3..EDGE_ID_MAX-1). Saves NVS and updates btName.
   * Returns false if invalid.
   */
  bool setId(const char *slug);

  /** Clear override and regenerate from MAC. */
  void resetToMac();

  bool save() const;

private:
  char _id[EDGE_ID_MAX] = {};
  char _btName[EDGE_ID_MAX] = {};
  char _macStr[18] = {};
  uint64_t _mac = 0;

  void deriveFromMac();
  void syncBtNameFromId();
  static bool sanitizeSlug(const char *in, char *out, size_t outSz);
};

extern DeviceIdentity g_deviceId;
