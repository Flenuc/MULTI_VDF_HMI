/**
 * Active VFD drive profile (multi-VDF).
 * saj.pdm30 — field-proven P0/P1 group_direct
 * saj.pdh30 — F0–F9 / FD / FE / D0 / E0 F-style (+ special regs)
 */
#pragma once

#include <stdint.h>
#include <stddef.h>
#include <string.h>

enum class DriveProfileId : uint8_t {
  SajPdm30 = 0,
  SajPdh30 = 1,
};

inline const char *driveProfileIdStr(DriveProfileId id) {
  switch (id) {
    case DriveProfileId::SajPdh30: return "saj.pdh30";
    case DriveProfileId::SajPdm30:
    default: return "saj.pdm30";
  }
}

inline bool driveProfileFromStr(const char *s, DriveProfileId &out) {
  if (!s || !*s) return false;
  if (strcmp(s, "saj.pdh30") == 0 || strcmp(s, "pdh30") == 0 || strcmp(s, "pdh") == 0) {
    out = DriveProfileId::SajPdh30;
    return true;
  }
  if (strcmp(s, "saj.pdm30") == 0 || strcmp(s, "pdm30") == 0 || strcmp(s, "pdm") == 0) {
    out = DriveProfileId::SajPdm30;
    return true;
  }
  return false;
}

/** PDM: (group<<8)|index. PDH F n.mm: ((0xF0|n)<<8)|mm */
inline uint16_t pdmParamAddress(uint8_t group, uint8_t index) {
  return (uint16_t)(((uint16_t)group << 8) | index);
}

inline uint16_t pdhFAddress(uint8_t fGroup /*0-9*/, uint8_t index) {
  return (uint16_t)(((uint16_t)(0xF0 | (fGroup & 0x0F)) << 8) | index);
}

class DriveProfileStore {
public:
  DriveProfileId id() const { return _id; }
  const char *idStr() const { return driveProfileIdStr(_id); }

  void set(DriveProfileId id) { _id = id; }
  bool setFromStr(const char *s) {
    DriveProfileId id;
    if (!driveProfileFromStr(s, id)) return false;
    _id = id;
    return true;
  }

  bool isPdh() const { return _id == DriveProfileId::SajPdh30; }
  bool isPdm() const { return _id == DriveProfileId::SajPdm30; }

private:
  DriveProfileId _id = DriveProfileId::SajPdm30;
};

// Global store (defined in DriveProfile.cpp)
extern DriveProfileStore g_driveProfile;
