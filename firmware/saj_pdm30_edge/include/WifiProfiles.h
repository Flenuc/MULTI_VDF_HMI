/**
 * @file WifiProfiles.h
 * @brief Multiple named Wi-Fi STA profiles in NVS.
 */
#pragma once

#include "Config.h"
#include <stdint.h>

struct WifiProfile {
  char name[WIFI_PROFILE_NAME_MAX + 1];
  char ssid[WIFI_SSID_MAX + 1];
  char pass[WIFI_PASS_MAX + 1];
  bool used;
};

class WifiProfiles {
public:
  void begin();
  void load();
  void save() const;

  int  count() const;
  bool get(int index, WifiProfile &out) const;
  bool findByName(const char *name, WifiProfile &out, int *indexOut = nullptr) const;

  /** Add or replace by name. Returns false if full / invalid. */
  bool upsert(const char *name, const char *ssid, const char *pass);
  bool remove(const char *name);

  const char *activeName() const { return _active; }
  bool setActive(const char *name);
  bool getActive(WifiProfile &out) const;

private:
  WifiProfile _prof[WIFI_MAX_PROFILES];
  char _active[WIFI_PROFILE_NAME_MAX + 1];
  int  _count;

  void clearMem();
};
