# Protocolo Edge — contrato compartido (firmware / app / clientes)

Fuente única para no divergir entre Electron/RN, desktop legacy y firmware.  
Versión alineada a Edge **≥ 0.3.7**. Seguridad de transporte: `docs/SECURITY.md`.

## Transportes

| Canal | Dirección | Notas |
|-------|-----------|--------|
| **MQTT** | App ↔ broker ↔ Edge | Preferido en planta (LAN). Topics abajo. |
| **USB Serial** | App ↔ Edge | 115200 8N1. CLI línea a línea. DevKit CDC a veces mudo → usar MQTT/BT. |
| **BT SPP** | App ↔ Edge | Solo `esp32dev` (Classic). Nombre `SAJ-PDM30-Edge`, PIN `1234`. |
| **BLE NUS** | App ↔ Edge | Solo Guition (Nordic UART). |

**Quién usa qué (producto):**

- VarioField (RN/Electron): **MQTT + BT** preferidos; USB para debug/Flasher.  
- Flasher / PlatformIO: USB download.  
- SoftAP `SAJ_Diag_Tool`: acceso de campo sin STA (ver SECURITY).

Todos los canales alimentan el mismo `CliEngine` (mismas líneas de comando/respuesta).

## MQTT topics

Root por defecto: `saj/pdm30/<edge_id>` con `edge_id` ≈ mDNS hostname (`saj-pdm30`).

| Topic | Quién publica | Payload |
|-------|---------------|---------|
| `…/cmd` | App | Línea CLI UTF-8 (una orden) |
| `…/rsp` | Edge | Línea(s) de respuesta CLI |
| `…/telemetry` | Edge | JSON ~1 Hz si `stream on` |
| `…/status` | Edge | LWT / online (si habilitado) |

Broker de lab: auth + ACL vía `desktop_app/scripts/setup_mosquitto.sh` (no anónimo por defecto).

## CLI — comandos

Formato: texto, tokens separados por espacio. Respuestas típicas: `OK …`, `ERR: …`, prompts `> `.

### Lectura / diagnóstico

| Comando | Efecto |
|---------|--------|
| `help` | Lista comandos |
| `ping` / `status` | Lee status/freq/amp/vdc → `Link OK` o `PING FAIL …` |
| `raw <addr>` | FC03 un holding (hex o dec) |
| `pget <id>` | Lee param por ID (`F0.00` / `P0-00`) según profile |
| `r0`/`r1 <ii>` | PDM P0/P1 por índice |
| `dump` | Dump CSV según profile |
| `rs485 status` | Pines DE/guard (DevKit) |
| `profile get\|list` | Drive profile activo |
| `wifi status` / `mqtt status` / `bt status` | Estado de red/BT |

### Escritura / operación (impacto físico)

| Comando | Efecto |
|---------|--------|
| `pset <id> <eng>` | Escribe param (ingeniería) |
| `wraw <addr> <uint>` | FC06 crudo |
| `w0`/`w1` | PDM write |
| `start` / `stop` / `estop` / `reset` | Marcha / paro / paro libre / reset falta |
| `set <pct>` | Consigna % frecuencia (reg familia) |

### Configuración Edge

| Comando | Efecto |
|---------|--------|
| `profile set saj.pdm30\|saj.pdh30` | Activa + **NVS save** (≥0.3.7) |
| `slave <id>` | Slave Modbus |
| `wifi …` / `mqtt …` / `bt …` | Red / broker / BT |
| `stream on\|off` | Telemetría JSON |
| `rs485 de\|guard\|settle\|swaptrx` | Diagnóstico RS485 DevKit |

## Telemetría JSON

Ejemplo (`stream on`):

```json
{"freq":0.00,"amp":0.00,"vdc":0.0,"vout":0.0,"pset":2.0,"pfb":0.0,"status":"stop"}
```

| Campo | Unidad / notas |
|-------|----------------|
| `freq` | Hz (reg `0x1001`, raw/100) |
| `amp` | A (raw/100) |
| `vdc` / `vout` | V (heurística bus) |
| `pset` | bar — PDM `0x0000` / PDH `0xF000` (≥0.3.7) |
| `pfb` | bar — `0x1010` |
| `status` | `run` \| `rev` \| `stop` \| `unknown` |

## Drive profiles

| ID | Mapa | Consigna presión |
|----|------|------------------|
| `saj.pdm30` | P0/P1 `group_direct` | `P0-00` |
| `saj.pdh30` | F-style + D0/E0 | `F0.00` |

Detalle: `docs/PDH_VS_PDM.md`. Catálogos: `drive_profiles/`.

## Errores

- `ERR: Timeout` / `CRC error` / `Busy` — Modbus  
- `ERR: unknown` — comando inválido  
- `PING FAIL step N: … rx_len=K` — link VFD  
- Pérdida de MQTT/USB **no** auto-`estop` (ver SECURITY)

## Evolución

Cambios breaking (topics, JSON fields, semántica de comandos) → bump de versión de firmware + nota en este archivo + release notes.
