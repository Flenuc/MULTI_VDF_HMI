#include "DeviceIdentity.h"
#include "Config.h"

#include <Arduino.h>
#include <Preferences.h>
#include <stdio.h>
#include <string.h>
#include <ctype.h>

#ifndef EDGE_NVS_NAMESPACE
#define EDGE_NVS_NAMESPACE "edge"
#endif
#ifndef EDGE_NVS_KEY_ID
#define EDGE_NVS_KEY_ID "id"
#endif

DeviceIdentity g_deviceId;

bool DeviceIdentity::sanitizeSlug(const char *in, char *out, size_t outSz) {
  if (!in || !out || outSz < 4) return false;
  size_t j = 0;
  for (size_t i = 0; in[i] && j + 1 < outSz; i++) {
    char c = in[i];
    if (c >= 'A' && c <= 'Z') c = (char)(c - 'A' + 'a');
    if ((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '-') {
      out[j++] = c;
    } else if (c == '_' || c == ' ') {
      out[j++] = '-';
    }
  }
  out[j] = '\0';
  // trim leading/trailing dashes
  while (out[0] == '-') memmove(out, out + 1, strlen(out));
  size_t n = strlen(out);
  while (n > 0 && out[n - 1] == '-') out[--n] = '\0';
  return n >= 3 && n < outSz;
}

void DeviceIdentity::syncBtNameFromId() {
  // VF-7CF194 from vf-7cf194
  snprintf(_btName, sizeof(_btName), "VF");
  size_t j = 2;
  for (size_t i = 0; _id[i] && j + 1 < sizeof(_btName); i++) {
    char c = _id[i];
    if (c == '-') {
      if (j + 1 < sizeof(_btName)) _btName[j++] = '-';
      continue;
    }
    if (c >= 'a' && c <= 'z') c = (char)(c - 'a' + 'A');
    _btName[j++] = c;
  }
  _btName[j] = '\0';
  if (j < 4) {
    strncpy(_btName, "VF-EDGE", sizeof(_btName) - 1);
    _btName[sizeof(_btName) - 1] = '\0';
  }
}

void DeviceIdentity::deriveFromMac() {
  _mac = ESP.getEfuseMac();
  // ESP MAC print order: commonly shown as bytes of efuse
  uint8_t b[6];
  b[0] = (uint8_t)(_mac >> 0);
  b[1] = (uint8_t)(_mac >> 8);
  b[2] = (uint8_t)(_mac >> 16);
  b[3] = (uint8_t)(_mac >> 24);
  b[4] = (uint8_t)(_mac >> 32);
  b[5] = (uint8_t)(_mac >> 40);
  snprintf(_macStr, sizeof(_macStr), "%02x:%02x:%02x:%02x:%02x:%02x",
           b[0], b[1], b[2], b[3], b[4], b[5]);
  // Human serial = last 3 bytes
  snprintf(_id, sizeof(_id), "vf-%02x%02x%02x", b[3], b[4], b[5]);
  syncBtNameFromId();
}

void DeviceIdentity::begin() {
  deriveFromMac();
  Preferences prefs;
  if (prefs.begin(EDGE_NVS_NAMESPACE, true)) {
    char saved[EDGE_ID_MAX] = {};
    prefs.getString(EDGE_NVS_KEY_ID, saved, sizeof(saved));
    prefs.end();
    char clean[EDGE_ID_MAX] = {};
    if (saved[0] && sanitizeSlug(saved, clean, sizeof(clean))) {
      strncpy(_id, clean, sizeof(_id) - 1);
      _id[sizeof(_id) - 1] = '\0';
      syncBtNameFromId();
      return;
    }
  }
  // Persist first-boot generated id so it stays even if we change format later
  save();
}

bool DeviceIdentity::save() const {
  Preferences prefs;
  if (!prefs.begin(EDGE_NVS_NAMESPACE, false)) return false;
  bool ok = prefs.putString(EDGE_NVS_KEY_ID, _id) > 0;
  prefs.end();
  return ok;
}

bool DeviceIdentity::setId(const char *slug) {
  char clean[EDGE_ID_MAX] = {};
  if (!sanitizeSlug(slug, clean, sizeof(clean))) return false;
  strncpy(_id, clean, sizeof(_id) - 1);
  _id[sizeof(_id) - 1] = '\0';
  syncBtNameFromId();
  return save();
}

void DeviceIdentity::resetToMac() {
  deriveFromMac();
  save();
}
