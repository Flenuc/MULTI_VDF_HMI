#include "WifiProfiles.h"
#include <Preferences.h>
#include <string.h>
#include <stdio.h>

void WifiProfiles::clearMem() {
  memset(_prof, 0, sizeof(_prof));
  _active[0] = '\0';
  _count = 0;
  for (int i = 0; i < WIFI_MAX_PROFILES; i++) _prof[i].used = false;
}

void WifiProfiles::begin() {
  clearMem();
  load();
}

void WifiProfiles::load() {
  clearMem();
  Preferences prefs;
  if (!prefs.begin(WIFI_NVS_NAMESPACE, true)) return;

  _count = prefs.getInt(WIFI_NVS_KEY_COUNT, 0);
  if (_count < 0) _count = 0;
  if (_count > WIFI_MAX_PROFILES) _count = WIFI_MAX_PROFILES;

  prefs.getString(WIFI_NVS_KEY_ACTIVE, _active, sizeof(_active));

  for (int i = 0; i < WIFI_MAX_PROFILES; i++) {
    char kn[12], ks[12], kp[12];
    snprintf(kn, sizeof(kn), "n%d", i);
    snprintf(ks, sizeof(ks), "s%d", i);
    snprintf(kp, sizeof(kp), "p%d", i);
    if (!prefs.isKey(kn)) continue;
    prefs.getString(kn, _prof[i].name, sizeof(_prof[i].name));
    prefs.getString(ks, _prof[i].ssid, sizeof(_prof[i].ssid));
    prefs.getString(kp, _prof[i].pass, sizeof(_prof[i].pass));
    if (_prof[i].name[0] && _prof[i].ssid[0]) {
      _prof[i].used = true;
    }
  }
  // recompute count
  _count = 0;
  for (int i = 0; i < WIFI_MAX_PROFILES; i++) {
    if (_prof[i].used) _count++;
  }

  // Migrate legacy single-key STA if no profiles
  if (_count == 0 && prefs.isKey("sta_ssid")) {
    char ssid[WIFI_SSID_MAX + 1] = {};
    char pass[WIFI_PASS_MAX + 1] = {};
    prefs.getString("sta_ssid", ssid, sizeof(ssid));
    prefs.getString("sta_pass", pass, sizeof(pass));
    prefs.end();
    if (ssid[0]) {
      upsert("default", ssid, pass);
      setActive("default");
      save();
    }
    return;
  }
  prefs.end();
}

void WifiProfiles::save() const {
  Preferences prefs;
  if (!prefs.begin(WIFI_NVS_NAMESPACE, false)) return;
  prefs.clear();
  int n = 0;
  for (int i = 0; i < WIFI_MAX_PROFILES; i++) {
    if (!_prof[i].used) continue;
    char kn[12], ks[12], kp[12];
    snprintf(kn, sizeof(kn), "n%d", n);
    snprintf(ks, sizeof(ks), "s%d", n);
    snprintf(kp, sizeof(kp), "p%d", n);
    prefs.putString(kn, _prof[i].name);
    prefs.putString(ks, _prof[i].ssid);
    prefs.putString(kp, _prof[i].pass);
    n++;
  }
  prefs.putInt(WIFI_NVS_KEY_COUNT, n);
  prefs.putString(WIFI_NVS_KEY_ACTIVE, _active);
  prefs.end();
}

int WifiProfiles::count() const {
  int n = 0;
  for (int i = 0; i < WIFI_MAX_PROFILES; i++) {
    if (_prof[i].used) n++;
  }
  return n;
}

bool WifiProfiles::get(int index, WifiProfile &out) const {
  int n = 0;
  for (int i = 0; i < WIFI_MAX_PROFILES; i++) {
    if (!_prof[i].used) continue;
    if (n == index) {
      out = _prof[i];
      return true;
    }
    n++;
  }
  return false;
}

bool WifiProfiles::findByName(const char *name, WifiProfile &out, int *indexOut) const {
  if (!name || !name[0]) return false;
  for (int i = 0; i < WIFI_MAX_PROFILES; i++) {
    if (_prof[i].used && strcmp(_prof[i].name, name) == 0) {
      out = _prof[i];
      if (indexOut) *indexOut = i;
      return true;
    }
  }
  return false;
}

bool WifiProfiles::upsert(const char *name, const char *ssid, const char *pass) {
  if (!name || !name[0] || !ssid || !ssid[0]) return false;
  if (strlen(name) > WIFI_PROFILE_NAME_MAX) return false;
  if (strlen(ssid) > WIFI_SSID_MAX) return false;
  if (pass && strlen(pass) > WIFI_PASS_MAX) return false;

  WifiProfile dummy;
  int idx = -1;
  if (findByName(name, dummy, &idx)) {
    strncpy(_prof[idx].ssid, ssid, WIFI_SSID_MAX);
    _prof[idx].ssid[WIFI_SSID_MAX] = '\0';
    if (pass) {
      strncpy(_prof[idx].pass, pass, WIFI_PASS_MAX);
      _prof[idx].pass[WIFI_PASS_MAX] = '\0';
    }
    _prof[idx].used = true;
    return true;
  }
  for (int i = 0; i < WIFI_MAX_PROFILES; i++) {
    if (!_prof[i].used) {
      memset(&_prof[i], 0, sizeof(_prof[i]));
      strncpy(_prof[i].name, name, WIFI_PROFILE_NAME_MAX);
      strncpy(_prof[i].ssid, ssid, WIFI_SSID_MAX);
      if (pass) strncpy(_prof[i].pass, pass, WIFI_PASS_MAX);
      _prof[i].used = true;
      return true;
    }
  }
  return false;
}

bool WifiProfiles::remove(const char *name) {
  WifiProfile dummy;
  int idx = -1;
  if (!findByName(name, dummy, &idx)) return false;
  if (strcmp(_active, name) == 0) _active[0] = '\0';
  memset(&_prof[idx], 0, sizeof(_prof[idx]));
  _prof[idx].used = false;
  return true;
}

bool WifiProfiles::setActive(const char *name) {
  WifiProfile p;
  if (!findByName(name, p)) return false;
  strncpy(_active, name, WIFI_PROFILE_NAME_MAX);
  _active[WIFI_PROFILE_NAME_MAX] = '\0';
  return true;
}

bool WifiProfiles::getActive(WifiProfile &out) const {
  if (_active[0] == '\0') {
    // first profile as fallback
    return get(0, out);
  }
  return findByName(_active, out);
}
