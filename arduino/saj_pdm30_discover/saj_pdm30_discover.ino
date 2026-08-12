/**
 * SAJ PDM-30 — Parameter address discovery
 *
 * Goal: find which Modbus register maps to each parameter
 *       P0-00..P0-47 and P1-00..P1-47.
 *
 * The PDM-30 user manual does NOT publish the register map for Pn.mm.
 * The PDH30 family uses F-group encoding: F3.15 → 0xF30F.
 * This sketch tries common schemes and fingerprints known defaults.
 *
 * Modes (USB Serial 115200, type and Enter):
 *   h           help
 *   ping        check link (read 0x3000 / 0x1001)
 *   schemes     test MAP schemes against known factory defaults
 *   dump        dump all candidate Pn addresses for best scheme
 *   fullscan    brute-force scan a register range (slow, READ ONLY)
 *   watch       snapshot then wait for you to change a param on keypad
 *   csv         print CSV of P0/P1 map for best scheme
 *   setmap N    force scheme 0/1/2
 *   raw A       read single address 0xA (hex or decimal)
 *
 * SAFETY:
 *   - All discovery operations are READ-ONLY by default.
 *   - Do NOT write randomly — you can corrupt settings or lock the drive.
 *   - Prefer fingerprinting with factory defaults OR the "watch" method:
 *       1) run "watch"
 *       2) change ONE parameter on the VFD keypad (e.g. P0-00)
 *       3) sketch finds which register value changed
 *
 * Recommended first run:
 *   1. Confirm P1-35=1, P1-36=1 (9600), P1-37=0 (8N1)
 *   2. ping
 *   3. schemes
 *   4. dump / csv
 *   5. if schemes fail → watch (change P0-00 on panel)
 */

#include "config.h"
#include "saj_pdm30_protocol.h"
#include "ModbusRTUMaster.h"

// Copy ModbusRTUMaster into this sketch folder (same file as control sketch)
// If missing, symlink or copy from ../saj_pdm30_modbus/ModbusRTUMaster.h

ModbusRTUMaster mb;

static ParamMapScheme g_bestScheme = MAP_F_STYLE;
static bool g_schemeKnown = false;

// Snapshot for watch mode
static const uint16_t WATCH_MAX = 256;
static uint16_t g_snapAddr[WATCH_MAX];
static uint16_t g_snapVal[WATCH_MAX];
static uint16_t g_snapCount = 0;

// ---------------------------------------------------------------------------
static void printHelp() {
  Serial.println(F("\n=== PDM-30 address discovery ==="));
  Serial.println(F("h          help"));
  Serial.println(F("ping       link check"));
  Serial.println(F("schemes    score MAP schemes vs known defaults"));
  Serial.println(F("dump       read all P0/P1 via best scheme"));
  Serial.println(F("csv        CSV map P0/P1 for best scheme"));
  Serial.println(F("fullscan   brute READ 0x0000-0x02FF + 0xF000-0xF1FF"));
  Serial.println(F("watch      snapshot; change param on keypad; re-scan"));
  Serial.println(F("setmap N   force scheme 0=direct 1=F-style 2=g*100"));
  Serial.println(F("raw ADDR   read one reg (e.g. raw 0xF000)"));
  Serial.println(F("OUTPUT lines starting with CSV: or MAP: are parseable"));
}

static bool rd(uint16_t addr, uint16_t &val) {
  delay(MB_INTER_FRAME_MS);
  return mb.readHolding(VFD_SLAVE_ID, addr, 1, &val);
}

static void cmdPing() {
  Serial.println(F("PING..."));
  uint16_t v;
  bool ok = false;
  if (rd(REG_VFD_STATUS, v)) {
    Serial.printf("  0x3000 status = %u OK\n", v);
    ok = true;
  } else {
    Serial.printf("  0x3000 FAIL: %s\n", mb.lastErrorStr());
  }
  if (rd(REG_RUN_FREQ, v)) {
    Serial.printf("  0x1001 run freq raw = %u (%.2f Hz)\n", v, v / 100.0f);
    ok = true;
  } else {
    Serial.printf("  0x1001 FAIL: %s\n", mb.lastErrorStr());
  }
  if (rd(REG_FB_PRESSURE, v)) {
    Serial.printf("  0x1010 pressure fb = %.1f bar\n", v / 10.0f);
    ok = true;
  } else {
    Serial.printf("  0x1010 FAIL: %s\n", mb.lastErrorStr());
  }
  if (!ok) {
    Serial.println(F("No response. Check: wiring A/B, GND, baud, slave ID, DE pin."));
  } else {
    Serial.println(F("Link appears alive."));
  }
}

/** Score a scheme: how many known defaults match when read. */
static int scoreScheme(ParamMapScheme scheme, bool verbose) {
  int hits = 0;
  int tries = 0;
  if (verbose) {
    Serial.printf("\n--- Scheme %u ---\n", (unsigned)scheme);
  }
  for (size_t k = 0; k < KNOWN_DEFAULTS_COUNT; k++) {
    const KnownDefault &d = KNOWN_DEFAULTS[k];
    uint16_t addr = paramToAddress(d.group, d.index, scheme);
    uint16_t val = 0;
    tries++;
    if (!rd(addr, val)) {
      if (verbose) {
        Serial.printf("  P%u-%02u @0x%04X  NO RESP (%s)\n",
                      d.group, d.index, addr, mb.lastErrorStr());
      }
      continue;
    }
    // Allow small tolerance: exact match preferred; also accept abs diff <= 1
    // and alternate scale for frequency-like values (x10 /x100)
    bool match = (int16_t)val == d.rawValue;
    bool soft  = abs((int)val - (int)d.rawValue) <= 1;
    bool alt   = (val == (uint16_t)(d.rawValue * 10)) ||
                 (val == (uint16_t)(d.rawValue * 100)) ||
                 (d.rawValue != 0 && val == (uint16_t)(d.rawValue / 10));
    if (match) hits += 2;
    else if (soft || alt) hits += 1;

    if (verbose) {
      const char *tag = match ? "HIT" : (soft || alt ? "NEAR" : "miss");
      Serial.printf("  P%u-%02u @0x%04X  got=%6u  expect=%d  %s  (%s)\n",
                    d.group, d.index, addr, val, d.rawValue, tag, d.name);
    }
  }
  if (verbose) {
    Serial.printf("Score: %d (higher is better, max ~%u)\n", hits, (unsigned)(KNOWN_DEFAULTS_COUNT * 2));
  }
  (void)tries;
  return hits;
}

static void cmdSchemes() {
  Serial.println(F("Scoring address map schemes against known defaults..."));
  Serial.println(F("(Best results if VFD still has factory / known settings)"));

  int bestScore = -1;
  ParamMapScheme best = MAP_GROUP_DIRECT;
  for (uint8_t s = 0; s < MAP_COUNT; s++) {
    int sc = scoreScheme((ParamMapScheme)s, true);
    if (sc > bestScore) {
      bestScore = sc;
      best = (ParamMapScheme)s;
    }
  }

  g_bestScheme = best;
  g_schemeKnown = (bestScore >= 4);  // at least a couple of hits
  Serial.printf("\nBEST scheme = %u  score=%d  %s\n",
                (unsigned)best, bestScore,
                g_schemeKnown ? "(confident)" : "(low confidence — try watch mode)");
  Serial.println(F("  0 = MAP_GROUP_DIRECT  P0-12→0x000C  P1-35→0x0123"));
  Serial.println(F("  1 = MAP_F_STYLE       P0-12→0xF00C  P1-35→0xF123  (PDH30-like)"));
  Serial.println(F("  2 = MAP_GROUP_100     P0-12→12      P1-35→135"));
}

static void dumpGroup(uint8_t group, ParamMapScheme scheme) {
  Serial.printf("\n=== P%u-xx  scheme=%u ===\n", group, (unsigned)scheme);
  for (uint8_t i = 0; i <= 47; i++) {
    uint16_t addr = paramToAddress(group, i, scheme);
    uint16_t val = 0;
    bool ok = rd(addr, val);
    if (ok) {
      Serial.printf("MAP: P%u-%02u,0x%04X,%u,%s\n",
                    group, i, addr, val, paramName(group, i));
    } else {
      Serial.printf("MAP: P%u-%02u,0x%04X,ERR_%s,%s\n",
                    group, i, addr, mb.lastErrorStr(), paramName(group, i));
    }
  }
}

static void cmdDump() {
  ParamMapScheme s = g_schemeKnown ? g_bestScheme : g_bestScheme;
  Serial.printf("Dumping with scheme %u\n", (unsigned)s);
  dumpGroup(0, s);
  dumpGroup(1, s);
  Serial.println(F("DONE dump"));
}

static void cmdCsv() {
  ParamMapScheme s = g_bestScheme;
  Serial.println(F("CSV:param,address_hex,address_dec,raw_value,name"));
  for (uint8_t g = 0; g <= 1; g++) {
    for (uint8_t i = 0; i <= 47; i++) {
      uint16_t addr = paramToAddress(g, i, s);
      uint16_t val = 0;
      bool ok = rd(addr, val);
      if (ok) {
        Serial.printf("CSV:P%u-%02u,0x%04X,%u,%u,\"%s\"\n",
                      g, i, addr, addr, val, paramName(g, i));
      } else {
        Serial.printf("CSV:P%u-%02u,0x%04X,%u,ERROR,\"%s\"\n",
                      g, i, addr, addr, paramName(g, i));
      }
    }
  }
  Serial.println(F("CSV:END"));
}

/** Brute-force readable register scan (read-only). */
static void scanRange(uint16_t start, uint16_t endInclusive) {
  Serial.printf("SCAN 0x%04X..0x%04X\n", start, endInclusive);
  for (uint32_t a = start; a <= endInclusive; a++) {
    uint16_t val;
    if (rd((uint16_t)a, val)) {
      Serial.printf("REG: 0x%04X,%u\n", (uint16_t)a, val);
    }
    // progress every 32 addresses
    if ((a & 0x1F) == 0) {
      Serial.printf("# progress 0x%04X\n", (uint16_t)a);
    }
  }
}

static void cmdFullScan() {
  Serial.println(F("FULLSCAN read-only (may take several minutes)..."));
  scanRange(0x0000, 0x02FF);
  scanRange(0x1000, 0x1010);
  scanRange(0x2000, 0x2000);
  scanRange(0x3000, 0x3000);
  scanRange(0xF000, 0xF12F);
  Serial.println(F("DONE fullscan"));
}

/** Build snapshot of candidate addresses for all schemes. */
static void buildSnapshot() {
  g_snapCount = 0;
  auto push = [&](uint16_t addr) {
    if (g_snapCount >= WATCH_MAX) return;
    uint16_t val;
    if (!rd(addr, val)) return;
    // de-dup
    for (uint16_t i = 0; i < g_snapCount; i++) {
      if (g_snapAddr[i] == addr) return;
    }
    g_snapAddr[g_snapCount] = addr;
    g_snapVal[g_snapCount] = val;
    g_snapCount++;
  };

  for (uint8_t s = 0; s < MAP_COUNT; s++) {
    for (uint8_t g = 0; g <= 1; g++) {
      for (uint8_t i = 0; i <= 47; i++) {
        push(paramToAddress(g, i, (ParamMapScheme)s));
      }
    }
  }
  // also specials
  for (uint16_t a = 0x1000; a <= 0x1010; a++) push(a);
  push(0x3000);
  Serial.printf("Snapshot: %u readable registers stored\n", g_snapCount);
}

static void cmdWatch() {
  Serial.println(F("WATCH mode:"));
  Serial.println(F("  1) Taking baseline snapshot of candidate addresses..."));
  buildSnapshot();
  if (g_snapCount == 0) {
    Serial.println(F("No registers readable. Fix link first (ping)."));
    return;
  }
  Serial.println(F("  2) NOW change ONE parameter on the VFD keypad."));
  Serial.println(F("     Recommended: P0-00 pressure setting (easy to see)."));
  Serial.println(F("  3) Waiting 15 seconds, then re-reading..."));
  for (int s = 15; s > 0; s--) {
    Serial.printf("     %d...\n", s);
    delay(1000);
  }

  Serial.println(F("  4) Diff:"));
  int changes = 0;
  for (uint16_t i = 0; i < g_snapCount; i++) {
    uint16_t val;
    if (!rd(g_snapAddr[i], val)) continue;
    if (val != g_snapVal[i]) {
      changes++;
      uint16_t addr = g_snapAddr[i];
      Serial.printf("CHANGE: addr=0x%04X  old=%u  new=%u\n", addr, g_snapVal[i], val);
      // decode under each scheme
      for (uint8_t s = 0; s < MAP_COUNT; s++) {
        uint8_t g, idx;
        if (addressToParam(addr, (ParamMapScheme)s, g, idx)) {
          Serial.printf("  -> scheme %u : P%u-%02u \"%s\"\n",
                        s, g, idx, paramName(g, idx));
          g_bestScheme = (ParamMapScheme)s;
          g_schemeKnown = true;
        }
      }
    }
  }
  if (changes == 0) {
    Serial.println(F("No changes detected. Did you modify a parameter? Try again."));
    Serial.println(F("Tip: change a value with a large delta (e.g. P0-00 3.0 -> 4.0)."));
  } else {
    Serial.printf("Detected %d change(s). Best scheme now %u\n", changes, (unsigned)g_bestScheme);
  }
}

static void cmdRaw(const char *arg) {
  uint16_t addr = (uint16_t)strtoul(arg, nullptr, 0);  // accepts 0x.. or decimal
  uint16_t val;
  if (rd(addr, val)) {
    Serial.printf("0x%04X = %u (0x%04X) signed=%d\n", addr, val, val, (int16_t)val);
  } else {
    Serial.printf("0x%04X FAIL: %s\n", addr, mb.lastErrorStr());
  }
}

static void processLine(String line) {
  line.trim();
  if (line.length() == 0) return;

  char buf[80];
  line.toCharArray(buf, sizeof(buf));
  char *tok = strtok(buf, " \t");
  if (!tok) return;

  if (strcmp(tok, "h") == 0 || strcmp(tok, "help") == 0) printHelp();
  else if (strcmp(tok, "ping") == 0) cmdPing();
  else if (strcmp(tok, "schemes") == 0) cmdSchemes();
  else if (strcmp(tok, "dump") == 0) cmdDump();
  else if (strcmp(tok, "csv") == 0) cmdCsv();
  else if (strcmp(tok, "fullscan") == 0) cmdFullScan();
  else if (strcmp(tok, "watch") == 0) cmdWatch();
  else if (strcmp(tok, "setmap") == 0) {
    char *n = strtok(nullptr, " \t");
    if (!n) { Serial.printf("scheme=%u known=%d\n", (unsigned)g_bestScheme, g_schemeKnown); return; }
    int v = atoi(n);
    if (v < 0 || v >= MAP_COUNT) { Serial.println(F("setmap 0|1|2")); return; }
    g_bestScheme = (ParamMapScheme)v;
    g_schemeKnown = true;
    Serial.printf("forced scheme=%u\n", (unsigned)g_bestScheme);
  } else if (strcmp(tok, "raw") == 0) {
    char *a = strtok(nullptr, " \t");
    if (!a) { Serial.println(F("usage: raw 0xF000")); return; }
    cmdRaw(a);
  } else {
    Serial.println(F("unknown — type h"));
  }
}

void setup() {
  Serial.begin(DEBUG_BAUD);
  delay(500);
  Serial.println(F("\nSAJ PDM-30 Parameter Address Discovery"));
  Serial.printf("RS485 RX=%d TX=%d DE=%d  slave=%d @ %d\n",
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
    } else if (line.length() < 70) {
      line += c;
    }
  }
}
