/**
 * @file ScaleTable.h
 * @brief Engineering unit scale: display = raw / scale, raw = round(display * scale)
 *
 * Scales derived from PDM-30 manual unit columns + field discovery
 * (e.g. P1-05 6000 = 60.00 Hz → scale 100).
 * Unknown indices default to scale 1 (identity).
 */
#pragma once

#include <stdint.h>
#include <math.h>

namespace ScaleTable {

/** Multiplier: raw = eng * scale (scale is integer 1,10,100,1000) */
uint16_t scaleOf(uint8_t group, uint8_t index);

inline float rawToEng(uint8_t group, uint8_t index, uint16_t raw) {
  const uint16_t s = scaleOf(group, index);
  if (s <= 1) return (float)(int16_t)raw;  // allow signed interpretation for scale 1
  return (float)(int16_t)raw / (float)s;
}

inline uint16_t engToRaw(uint8_t group, uint8_t index, float eng) {
  const uint16_t s = scaleOf(group, index);
  float v = eng * (float)s;
  if (v >= 0.0f) v += 0.5f;
  else v -= 0.5f;
  if (v > 65535.0f) v = 65535.0f;
  if (v < -32768.0f) v = -32768.0f;
  // Most params are unsigned; clamp to uint16 for wire
  int32_t r = (int32_t)v;
  if (r < 0) r = 0;
  if (r > 65535) r = 65535;
  return (uint16_t)r;
}

const char *unitOf(uint8_t group, uint8_t index);

}  // namespace ScaleTable
