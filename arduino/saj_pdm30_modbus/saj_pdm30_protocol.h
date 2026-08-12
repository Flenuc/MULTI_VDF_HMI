/**
 * SAJ PDM-30 / PDH30 family — Modbus RTU protocol definitions
 *
 * Based on SAJ PDH30 User Manual Chapter 6 (same product family / Mod-Bus RTU).
 * Parameter groups on PDM-30 are named P0-xx / P1-xx (not F0.xx).
 * Exact Pn.mm → register mapping is NOT published for PDM-30; use the
 * discovery sketch/script to confirm. Two common schemes are defined below.
 *
 * Defaults (from PDM30 manual):
 *   P1-35 Local address = 1
 *   P1-36 Baud rate     = 1 → 9600 bps
 *   P1-37 Data format   = 0 → 8N1
 */

#ifndef SAJ_PDM30_PROTOCOL_H
#define SAJ_PDM30_PROTOCOL_H

#include <stdint.h>
#include <stddef.h>

// ---------------------------------------------------------------------------
// Modbus
// ---------------------------------------------------------------------------
static const uint8_t  MB_FC_READ_HOLDING  = 0x03;
static const uint8_t  MB_FC_WRITE_SINGLE  = 0x06;
static const uint8_t  MB_FC_WRITE_MULTI   = 0x10;

// ---------------------------------------------------------------------------
// Special function registers (PDH30 Ch.6 — expected same family on PDM-30)
// ---------------------------------------------------------------------------
static const uint16_t REG_FREQ_SET_PCT    = 0x1000;  // R/W  -10000..10000 (= -100.00%..100.00% of max freq)
static const uint16_t REG_RUN_FREQ        = 0x1001;  // R    0.01 Hz
static const uint16_t REG_BUS_VOLTAGE     = 0x1002;  // R    0.1 V
static const uint16_t REG_OUT_VOLTAGE     = 0x1003;  // R    1 V
static const uint16_t REG_OUT_CURRENT     = 0x1004;  // R    0.01 A
static const uint16_t REG_OUT_POWER       = 0x1005;  // R    0.1 kW
static const uint16_t REG_OUT_TORQUE      = 0x1006;  // R    0.1 %
static const uint16_t REG_RUN_SPEED       = 0x1007;  // R    1 RPM
static const uint16_t REG_DI_STATUS       = 0x1008;  // R
static const uint16_t REG_DO_STATUS       = 0x1009;  // R
static const uint16_t REG_AI1             = 0x100A;  // R    0.01 V
static const uint16_t REG_AI2             = 0x100B;  // R    0.01 V
static const uint16_t REG_POWERON_HOURS   = 0x100C;  // R    1 h
static const uint16_t REG_RUN_HOURS       = 0x100D;  // R    1 h
static const uint16_t REG_ENERGY_KWH      = 0x100E;  // R    1 kWh
static const uint16_t REG_SET_PRESSURE    = 0x100F;  // R    0.1 bar
static const uint16_t REG_FB_PRESSURE     = 0x1010;  // R    0.1 bar

// Communication control command (write only)
static const uint16_t REG_CTRL_CMD        = 0x2000;
static const uint16_t CMD_FWD_RUN         = 0x0001;
static const uint16_t CMD_REV_RUN         = 0x0002;
static const uint16_t CMD_JOG_FWD         = 0x0003;
static const uint16_t CMD_JOG_REV         = 0x0004;
static const uint16_t CMD_FREE_STOP       = 0x0005;  // emergency / free stop
static const uint16_t CMD_DECEL_STOP      = 0x0006;
static const uint16_t CMD_FAULT_RESET     = 0x0007;

// VFD status (read only)
static const uint16_t REG_VFD_STATUS      = 0x3000;
static const uint16_t STATUS_FWD          = 0x0001;
static const uint16_t STATUS_REV          = 0x0002;
static const uint16_t STATUS_STOP         = 0x0003;

// Manual note: max continuous read length for params is 12 registers.
static const uint16_t MB_MAX_CONTIGUOUS   = 12;

// ---------------------------------------------------------------------------
// Candidate address maps for function codes Pn.mm
// PDH30 example: F3.15 → 0xF30F  (high = 0xF0|group, low = index)
// PDM30 may use either F-style or plain group bytes.
// ---------------------------------------------------------------------------
enum ParamMapScheme : uint8_t {
  MAP_GROUP_DIRECT = 0,  // P0-12 → 0x000C, P1-35 → 0x0123
  MAP_F_STYLE      = 1,  // P0-12 → 0xF00C, P1-35 → 0xF123  (like PDH30 F groups)
  MAP_GROUP_100    = 2,  // P0-12 → 0x000C, P1-35 → 0x0063  (group*100 + idx) wait: 100+35=135=0x0087
  MAP_COUNT
};

/** Encode Pn.mm → Modbus register address for a given scheme. */
inline uint16_t paramToAddress(uint8_t group, uint8_t index, ParamMapScheme scheme) {
  switch (scheme) {
    case MAP_GROUP_DIRECT:
      return (uint16_t)((group << 8) | index);
    case MAP_F_STYLE:
      return (uint16_t)((0xF0 | group) << 8) | index;
    case MAP_GROUP_100:
      return (uint16_t)(group * 100 + index);
    default:
      return (uint16_t)((group << 8) | index);
  }
}

/** Decode address → group/index if it matches a scheme (returns false if not). */
inline bool addressToParam(uint16_t addr, ParamMapScheme scheme, uint8_t &group, uint8_t &index) {
  switch (scheme) {
    case MAP_GROUP_DIRECT:
      group = (uint8_t)(addr >> 8);
      index = (uint8_t)(addr & 0xFF);
      return group <= 1 && index <= 47;
    case MAP_F_STYLE:
      if ((addr >> 12) != 0xF) return false;
      group = (uint8_t)((addr >> 8) & 0x0F);
      index = (uint8_t)(addr & 0xFF);
      return group <= 1 && index <= 47;
    case MAP_GROUP_100: {
      uint16_t g = addr / 100;
      uint16_t i = addr % 100;
      if (g > 1 || i > 47) return false;
      group = (uint8_t)g;
      index = (uint8_t)i;
      return true;
    }
    default:
      return false;
  }
}

// ---------------------------------------------------------------------------
// Known factory defaults (raw register integers as typically stored)
// Used by discovery to fingerprint which map scheme is correct.
// Scale follows manual unit column (value = display / unit).
// ---------------------------------------------------------------------------
struct KnownDefault {
  uint8_t  group;
  uint8_t  index;
  int16_t  rawValue;   // expected default in register units
  const char *name;
};

// Conservative list of distinctive defaults from PDM30 manual
static const KnownDefault KNOWN_DEFAULTS[] = {
  {0,  0,   30, "P0-00 Pressure setting (3.0 bar, unit 0.1)"},
  {0,  1,    3, "P0-01 Pressure deviation (0.3 bar)"},
  {0,  3,  100, "P0-03 Sensor range (10.0 bar)"},
  {0,  8,    1, "P0-08 PID function selection"},
  {0, 14,    0, "P0-14 Power-on auto start"},
  {0, 25,    2, "P0-25 Water shortage protection"},
  {0, 36,   20, "P0-36 Accel time 1 (2.0 s, unit 0.1s)"},
  {0, 37,   20, "P0-37 Decel time 1 (2.0 s, unit 0.1s)"},
  {0, 43,    8, "P0-43 Main frequency source (PID)"},
  {0, 44,    0, "P0-44 System working mode"},
  {1,  5,  500, "P1-05 Max output freq (50.00 Hz, unit 0.1Hz?)"},
  {1,  6,  500, "P1-06 Upper frequency"},
  {1,  9,   80, "P1-09 Carrier freq (8.0 kHz, unit 0.1kHz)"},
  {1, 34,    0, "P1-34 Command source"},
  {1, 35,    1, "P1-35 Local address"},
  {1, 36,    1, "P1-36 Baud rate (9600)"},
  {1, 37,    0, "P1-37 Data format (8N1)"},
  {1, 38,    2, "P1-38 Response delay (2 ms)"},
};
static const size_t KNOWN_DEFAULTS_COUNT = sizeof(KNOWN_DEFAULTS) / sizeof(KNOWN_DEFAULTS[0]);

// PDM-30 parameter names for reporting (P0-00 .. P0-47, P1-00 .. P1-47)
// Empty string = not documented / reserved in manual extract
static const char *const P0_NAMES[48] = {
  /*00*/ "Pressure setting",
  /*01*/ "Pressure deviation (wake)",
  /*02*/ "Operation direction",
  /*03*/ "Sensor range",
  /*04*/ "Sensor feedback type",
  /*05*/ "Pressure calibration factor",
  /*06*/ "Proportional gain P1",
  /*07*/ "Integration time I1",
  /*08*/ "PID function selection",
  /*09*/ "PID sleep delay",
  /*10*/ "PID wake-up delay",
  /*11*/ "PID sleep frequency",
  /*12*/ "PID low-freq hold run time",
  /*13*/ "PID sleep deviation pressure",
  /*14*/ "Power-on automatic start",
  /*15*/ "Power-on auto start delay",
  /*16*/ "Antifreeze function",
  /*17*/ "Antifreeze operating frequency",
  /*18*/ "Antifreeze running time",
  /*19*/ "Antifreeze operation cycle",
  /*20*/ "Leakage size factor",
  /*21*/ "High pressure alarm value",
  /*22*/ "High pressure alarm delay",
  /*23*/ "Low pressure alarm value",
  /*24*/ "Low pressure alarm delay",
  /*25*/ "Water shortage protection fn",
  /*26*/ "Water shortage fault threshold",
  /*27*/ "Water shortage test frequency",
  /*28*/ "Water shortage current %",
  /*29*/ "Water shortage detect time",
  /*30*/ "Water shortage auto restart delay",
  /*31*/ "PID sleep rate",
  /*32*/ "Incoming water detection pressure",
  /*33*/ "Incoming water detection time",
  /*34*/ "AI minimum input",
  /*35*/ "AI maximum input",
  /*36*/ "Acceleration time 1",
  /*37*/ "Deceleration time 1",
  /*38*/ "Parameter initialization",
  /*39*/ "Parameter function lock",
  /*40*/ "Broken record",
  /*41*/ "Radiator temperature",
  /*42*/ "Software version",
  /*43*/ "Main frequency source X",
  /*44*/ "System working mode",
  /*45*/ "Pressure display mode",
  /*46*/ "(reserved / unknown)",
  /*47*/ "Application macro selection",
};

static const char *const P1_NAMES[48] = {
  /*00*/ "Multi online slave backup host action",
  /*01*/ "Multi online network mode",
  /*02*/ "Number of multi-line aux machines",
  /*03*/ "Multi online operating modes",
  /*04*/ "Multi-line rotation interval",
  /*05*/ "Maximum output frequency",
  /*06*/ "Upper frequency",
  /*07*/ "Lower limit frequency",
  /*08*/ "Below lower limit frequency action",
  /*09*/ "Carrier frequency",
  /*10*/ "PID feedback loss detection value",
  /*11*/ "PID feedback loss detection time",
  /*12*/ "Motor power selection",
  /*13*/ "Motor rated power / related",
  /*14*/ "Motor rated frequency",
  /*15*/ "(see manual)",
  /*16*/ "(see manual)",
  /*17*/ "(see manual)",
  /*18*/ "(see manual)",
  /*19*/ "(see manual)",
  /*20*/ "(see manual)",
  /*21*/ "(see manual)",
  /*22*/ "(see manual)",
  /*23*/ "(see manual)",
  /*24*/ "(see manual)",
  /*25*/ "(see manual)",
  /*26*/ "(see manual)",
  /*27*/ "(see manual)",
  /*28*/ "Stop mode",
  /*29*/ "Keyboard setting frequency",
  /*30*/ "PID action direction",
  /*31*/ "PID low frequency hold frequency",
  /*32*/ "Sleep detection cycle",
  /*33*/ "PWM mode",
  /*34*/ "Command source selection",
  /*35*/ "Local address (Modbus slave)",
  /*36*/ "Baud rate",
  /*37*/ "Data format",
  /*38*/ "Response delay",
  /*39*/ "(reserved / unknown)",
  /*40*/ "(reserved / unknown)",
  /*41*/ "(reserved / unknown)",
  /*42*/ "Motor type selection",
  /*43*/ "Single-phase turns ratio",
  /*44*/ "Single-phase current correction",
  /*45*/ "Water shortage protection reset times",
  /*46*/ "(reserved / unknown)",
  /*47*/ "(reserved / unknown)",
};

inline const char *paramName(uint8_t group, uint8_t index) {
  if (index > 47) return "?";
  return (group == 0) ? P0_NAMES[index] : P1_NAMES[index];
}

#endif // SAJ_PDM30_PROTOCOL_H
