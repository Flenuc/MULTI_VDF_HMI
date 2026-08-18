#include "DriveProfile.h"
#include "Config.h"

#include <Preferences.h>

DriveProfileStore g_driveProfile;

void DriveProfileStore::begin() {
  load();
}

void DriveProfileStore::load() {
  Preferences prefs;
  if (!prefs.begin(DRIVE_NVS_NAMESPACE, true)) {
    _id = DriveProfileId::SajPdm30;
    return;
  }
  char buf[24] = {};
  prefs.getString(DRIVE_NVS_KEY_ID, buf, sizeof(buf));
  prefs.end();

  DriveProfileId id;
  if (buf[0] && driveProfileFromStr(buf, id)) {
    _id = id;
  } else {
    _id = DriveProfileId::SajPdm30;
  }
}

bool DriveProfileStore::save() const {
  Preferences prefs;
  if (!prefs.begin(DRIVE_NVS_NAMESPACE, false)) return false;
  bool ok = prefs.putString(DRIVE_NVS_KEY_ID, idStr()) > 0;
  prefs.end();
  return ok;
}
