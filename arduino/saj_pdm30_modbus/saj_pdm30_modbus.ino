/**
 * SAJ PDM-30 — ESP32 Modbus RTU master
 *
 * Control and monitor a SAJ PDM-30 pump VFD over RS485.
 * Protocol from SAJ PDH30 family manual (Mod-Bus RTU).
 *
 * USB Serial (115200) interactive commands:
 *   h          help
 *   s          read status + run parameters
 *   p          read pressures (set + feedback)
 *   r G I      read parameter  Pn-ii  e.g.  r 0 0  → P0-00
 *   w G I V    write parameter Pn-ii = V (raw integer)
 *   f PCT      set frequency % of max  (-10000..10000)
 *   go         forward run (needs P1-34 = 2 serial command)
 *   stop       deceleration stop
 *   estop      free / emergency stop
 *   reset      fault reset
 *   scan       probe special registers 0x1000-0x1010, 0x2000, 0x3000
 *
 * Before writing control commands set on the VFD panel:
 *   P1-34 = 2  (command source = serial)
 *   P1-35 = 1  (slave address, match config.h)
 *   P1-36 = 1  (9600 baud)
 *   P1-37 = 0  (8N1)
 *
 * Wiring (typical MAX485):
 *   ESP32 TX → DI
 *   ESP32 RX → RO
 *   ESP32 DE → DE+RE
 *   A+ / B-  → VFD A+ / B-
 *   GND common recommended
 */

#include "config.h"
#include "saj_pdm30_protocol.h"
#include "ModbusRTUMaster.h"

ModbusRTUMaster mb;

// Active mapping scheme (change after discovery)
static ParamMapScheme g_scheme = (ParamMapScheme)PARAM_MAP_SCHEME;

// ---------------------------------------------------------------------------
static void printHelp() {
  Serial.println(F("\n=== SAJ PDM-30 Modbus RTU ==="));
  Serial.println(F("h          help"));
  Serial.println(F("s          status + telemetry"));
  Serial.println(F("p          pressures"));
  Serial.println(F("r G I      read  P{G}-{I}"));
  Serial.println(F("w G I V    write P{G}-{I}=V (raw)"));
  Serial.println(F("f PCT      set freq percent *100 (5000=50.00%)"));
  Serial.println(F("go / stop / estop / reset"));
  Serial.println(F("scan       probe special regs"));
  Serial.println(F("map N      set map scheme 0=direct 1=F-style 2=group*100"));
  Serial.printf("slave=%u baud=%u scheme=%u\n", VFD_SLAVE_ID, VFD_BAUD, (unsigned)g_scheme);
}

static bool readReg(uint16_t addr, uint16_t &val) {
  uint16_t tmp;
  if (!mb.readHolding(VFD_SLAVE_ID, addr, 1, &tmp)) {
    Serial.printf("RD 0x%04X FAIL: %s (err=%u)\n", addr, mb.lastErrorStr(), mb.lastError());
    return false;
  }
  val = tmp;
  return true;
}

static bool writeReg(uint16_t addr, uint16_t val) {
  if (!mb.writeSingle(VFD_SLAVE_ID, addr, val)) {
    Serial.printf("WR 0x%04X=%u FAIL: %s (err=%u)\n", addr, val, mb.lastErrorStr(), mb.lastError());
    return false;
  }
  Serial.printf("WR 0x%04X = %u (0x%04X) OK\n", addr, val, val);
  return true;
}

static void cmdStatus() {
  uint16_t st = 0;
  if (readReg(REG_VFD_STATUS, st)) {
    const char *name = "?";
    if (st == STATUS_FWD) name = "FWD run";
    else if (st == STATUS_REV) name = "REV run";
    else if (st == STATUS_STOP) name = "STOP";
    Serial.printf("Status 0x3000 = %u (%s)\n", st, name);
  }

  // Manual: read up to 12 contiguous from 0x1000 block
  uint16_t buf[17];
  if (mb.readHolding(VFD_SLAVE_ID, REG_FREQ_SET_PCT, 12, buf)) {
    Serial.printf("Freq set %%   0x1000 = %d (%.2f%%)\n", (int16_t)buf[0], (int16_t)buf[0] / 100.0f);
    Serial.printf("Run freq      0x1001 = %.2f Hz\n", buf[1] / 100.0f);
    Serial.printf("Bus voltage   0x1002 = %.1f V\n",  buf[2] / 10.0f);
    Serial.printf("Out voltage   0x1003 = %u V\n",    buf[3]);
    Serial.printf("Out current   0x1004 = %.2f A\n",  buf[4] / 100.0f);
    Serial.printf("Out power     0x1005 = %.1f kW\n", buf[5] / 10.0f);
    Serial.printf("Out torque    0x1006 = %.1f %%\n", buf[6] / 10.0f);
    Serial.printf("Run speed     0x1007 = %u RPM\n",  buf[7]);
    Serial.printf("DI status     0x1008 = 0x%04X\n",  buf[8]);
    Serial.printf("DO status     0x1009 = 0x%04X\n",  buf[9]);
    Serial.printf("AI1           0x100A = %.2f V\n",  buf[10] / 100.0f);
    Serial.printf("AI2           0x100B = %.2f V\n",  buf[11] / 100.0f);
  } else {
    Serial.printf("telemetry read FAIL: %s\n", mb.lastErrorStr());
  }

  // pressures are at 0x100F / 0x1010 — second read (max 12 contiguous)
  uint16_t p[2];
  if (mb.readHolding(VFD_SLAVE_ID, REG_SET_PRESSURE, 2, p)) {
    Serial.printf("Set pressure  0x100F = %.1f bar\n", p[0] / 10.0f);
    Serial.printf("Fb  pressure  0x1010 = %.1f bar\n", p[1] / 10.0f);
  }
}

static void cmdPressures() {
  uint16_t p[2];
  if (!mb.readHolding(VFD_SLAVE_ID, REG_SET_PRESSURE, 2, p)) {
    Serial.printf("FAIL: %s\n", mb.lastErrorStr());
    return;
  }
  Serial.printf("Set=%.1f bar  Feedback=%.1f bar\n", p[0] / 10.0f, p[1] / 10.0f);
}

static void cmdReadParam(uint8_t g, uint8_t i) {
  uint16_t addr = paramToAddress(g, i, g_scheme);
  uint16_t val;
  Serial.printf("P%u-%02u \"%s\"  addr=0x%04X\n", g, i, paramName(g, i), addr);
  if (readReg(addr, val)) {
    Serial.printf("  raw=%u  (0x%04X)  signed=%d\n", val, val, (int16_t)val);
  }
}

static void cmdWriteParam(uint8_t g, uint8_t i, uint16_t v) {
  uint16_t addr = paramToAddress(g, i, g_scheme);
  Serial.printf("P%u-%02u \"%s\"  addr=0x%04X <- %u\n", g, i, paramName(g, i), addr, v);
  writeReg(addr, v);
}

static void cmdScanSpecial() {
  Serial.println(F("Probing special registers..."));
  const uint16_t addrs[] = {
    0x1000, 0x1001, 0x1002, 0x1003, 0x1004, 0x1005, 0x1006, 0x1007,
    0x1008, 0x1009, 0x100A, 0x100B, 0x100C, 0x100D, 0x100E, 0x100F, 0x1010,
    0x2000, 0x3000
  };
  for (uint16_t a : addrs) {
    uint16_t v;
    delay(MB_INTER_FRAME_MS);
    if (mb.readHolding(VFD_SLAVE_ID, a, 1, &v)) {
      Serial.printf("  0x%04X = %6u  (0x%04X)\n", a, v, v);
    } else {
      Serial.printf("  0x%04X  -- %s\n", a, mb.lastErrorStr());
    }
  }
}

static void processLine(String line) {
  line.trim();
  if (line.length() == 0) return;

  // tokenize
  char buf[64];
  line.toCharArray(buf, sizeof(buf));
  char *tok = strtok(buf, " \t");
  if (!tok) return;

  if (strcmp(tok, "h") == 0 || strcmp(tok, "help") == 0) {
    printHelp();
  } else if (strcmp(tok, "s") == 0) {
    cmdStatus();
  } else if (strcmp(tok, "p") == 0) {
    cmdPressures();
  } else if (strcmp(tok, "scan") == 0) {
    cmdScanSpecial();
  } else if (strcmp(tok, "map") == 0) {
    char *n = strtok(nullptr, " \t");
    if (!n) {
      Serial.printf("scheme=%u\n", (unsigned)g_scheme);
      return;
    }
    int v = atoi(n);
    if (v < 0 || v >= MAP_COUNT) {
      Serial.println(F("map 0|1|2"));
      return;
    }
    g_scheme = (ParamMapScheme)v;
    Serial.printf("scheme set to %u\n", (unsigned)g_scheme);
  } else if (strcmp(tok, "r") == 0) {
    char *g = strtok(nullptr, " \t");
    char *i = strtok(nullptr, " \t");
    if (!g || !i) { Serial.println(F("usage: r G I")); return; }
    cmdReadParam((uint8_t)atoi(g), (uint8_t)atoi(i));
  } else if (strcmp(tok, "w") == 0) {
    char *g = strtok(nullptr, " \t");
    char *i = strtok(nullptr, " \t");
    char *v = strtok(nullptr, " \t");
    if (!g || !i || !v) { Serial.println(F("usage: w G I V")); return; }
    cmdWriteParam((uint8_t)atoi(g), (uint8_t)atoi(i), (uint16_t)atoi(v));
  } else if (strcmp(tok, "f") == 0) {
    char *v = strtok(nullptr, " \t");
    if (!v) { Serial.println(F("usage: f PCT  (5000 = 50.00%)")); return; }
    writeReg(REG_FREQ_SET_PCT, (uint16_t)atoi(v));
  } else if (strcmp(tok, "go") == 0) {
    writeReg(REG_CTRL_CMD, CMD_FWD_RUN);
  } else if (strcmp(tok, "stop") == 0) {
    writeReg(REG_CTRL_CMD, CMD_DECEL_STOP);
  } else if (strcmp(tok, "estop") == 0) {
    writeReg(REG_CTRL_CMD, CMD_FREE_STOP);
  } else if (strcmp(tok, "reset") == 0) {
    writeReg(REG_CTRL_CMD, CMD_FAULT_RESET);
  } else {
    Serial.println(F("unknown cmd — type h"));
  }
}

void setup() {
  Serial.begin(DEBUG_BAUD);
  delay(500);
  Serial.println(F("\nSAJ PDM-30 ESP32 Modbus RTU master"));
  Serial.printf("RS485 RX=%d TX=%d DE=%d  slave=%d @ %d 8N1\n",
                RS485_RX_PIN, RS485_TX_PIN, RS485_DE_PIN, VFD_SLAVE_ID, VFD_BAUD);

  mb.begin(VFD_BAUD, VFD_CONFIG);
  printHelp();
  Serial.print(F("> "));
}

void loop() {
  static String line;
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      processLine(line);
      line = "";
      Serial.print(F("> "));
    } else if (line.length() < 60) {
      line += c;
    }
  }
}
