# Continuación de iteración — SAJ PDM-30 Edge + Desktop

**Fecha de handoff:** 2026-08-11  
**Workspace:** `/home/master-pi/Desktop/VF patron`  
**Objetivo de este documento:** permitir retomar el trabajo en otra shell/sesión sin re-descubrir contexto.

---

## 1. Resumen del sistema

```
[PC: SAJ Edge Configurator]
        │
        ├─ USB Serial 115200  ─────────────────────────────┐
        │                                                    │
        └─ MQTT (recomendado) ──► broker (Mosquitto) ──► [ESP32 Edge]
                                                              │
                                                         RS485 / Modbus RTU
                                                              │
                                                         [VDF SAJ PDM-30]
```

- El **ESP32** es maestro Modbus RTU hacia el VDF y cliente MQTT (y/o Serial CLI).
- La **app de escritorio** (CustomTkinter) envía comandos CLI por Serial o MQTT y recibe telemetría JSON.
- **WebSocket se abandonó** como canal principal (saturación en `dump`, fricción multiplataforma). MQTT es el camino preferido.

---

## 2. Estado actual (qué está hecho)

### Firmware Edge — `firmware/saj_pdm30_edge/`

| Capacidad | Estado |
|-----------|--------|
| Modbus RTU no bloqueante (FC03/06) | OK |
| CLI multi-canal (Serial + MQTT) | OK |
| Escalas ingeniería `r0/w0/r1/w1` | OK |
| `start` / `stop` / `set` / `dump` / `stream` | OK |
| Dump en lotes + pace WS legacy / MQTT | OK (pace + batch CSV) |
| Wi‑Fi AP + STA + perfiles NVS | OK |
| MQTT (PubSubClient) + topics | OK |
| Variante **ESP32 DevKit** (`esp32dev`) | Compila OK |
| Variante **Guition JC-ESP32P4-M3-DEV** (`guition_jc_esp32p4_m3`) | Compila OK |
| UI display en Guition (LVGL) | **No implementado** (solo Edge headless) |

### App desktop — `desktop_app/`

| Capacidad | Estado |
|-----------|--------|
| CRUD parámetros + JSON | OK |
| Serial + Dummy + **MQTT** | OK |
| Perfiles Wi‑Fi/MQTT en PC (`config/connection_profiles.json`) | OK |
| Sync / Compare con busy-lock + timeout + cancel | OK |
| Telemetría live | OK |
| Modo WebSocket en UI | Deprecado (código residual en `comms/ws_client.py`) |

### Pruebas de campo ya hechas

- **ESP32 clásico** (ACM0 vía Uno sin MCU como USB-serial):
  - Discovery mapa: **P0-ii → 0x00ii**, **P1-ii → 0x01ii**
  - STA a `REDACTED_SSID` → IP **192.168.203.68** (puede cambiar por DHCP)
  - mDNS `saj-pdm30.local` OK en esa red
  - MQTT no se validó end-to-end en la última sesión (falta broker en LAN + firmware MQTT flasheado en la unidad de campo)
- Dump por Wi‑Fi/WebSocket se truncaba; se corrigió con batch+pace (requiere firmware actual flasheado).

---

## 3. Estructura del repo (relevante)

```
VF patron/
├── CONTINUACION_ITERACION.md          ← este archivo
├── arduino/                           # sketches legacy (discover / CLI / modbus)
│   ├── saj_pdm30_discover/
│   ├── saj_pdm30_cli/
│   └── saj_pdm30_modbus/
├── firmware/saj_pdm30_edge/           # ★ firmware actual (PlatformIO)
│   ├── platformio.ini                 # envs: esp32dev | guition_jc_esp32p4_m3
│   ├── include/
│   │   ├── Config.h
│   │   ├── boards/
│   │   │   ├── board_esp32dev.h
│   │   │   └── board_guition_jc_esp32p4_m3.h
│   │   ├── HwRs485.h, ModbusRtuMaster.h, SajPdm30.h
│   │   ├── CliEngine.h, NetworkService.h, TelemetryService.h
│   │   ├── WifiProfiles.h, ResponseChannel.h, ScaleTable.h
│   │   └── UsbCli.h
│   ├── src/
│   │   ├── main.cpp
│   │   ├── CliEngine.cpp, NetworkService.cpp, WifiProfiles.cpp
│   │   ├── TelemetryService.cpp, ScaleTable.cpp
│   ├── boards/guition_jc_esp32p4_m3.json
│   ├── README.md
│   └── README_GUITION_P4.md
├── firmware/.pio-venv/                # PlatformIO CLI (pip) para builds
├── desktop_app/                       # ★ app de campo
│   ├── main.py, gui/app.py, models.py, storage.py, profiles.py
│   ├── comms/  (base, serial_client, mqtt_client, dummy_client, ws_client legacy)
│   ├── config/connection_profiles.json
│   ├── param_lists/
│   ├── requirements.txt, .venv/
│   └── README.md
├── docs/                              # manuales PDM30/PDH30
└── results/                           # logs de tests
```

---

## 4. Hardware y pines

### A) ESP32 DevKit + SN75176B externo (`esp32dev`)

| Señal | GPIO |
|-------|------|
| RS485 TX (DI) | 14 |
| RS485 RX (RO) | 25 |
| DE/RE | 27 |
| LED actividad | 2 |
| VDF | slave **1**, **9600 8N1** |

Flash: a menudo vía **Arduino Uno sin MCU** como USB-serial en `/dev/ttyACM0` → hace falta **BOOT+EN** manual para flashear.

### B) Guition JC-ESP32P4-M3-DEV (`guition_jc_esp32p4_m3`)

| Señal | GPIO / nota |
|-------|-------------|
| RS485 TX | **26** (onboard MAX485) |
| RS485 RX | **27** |
| DE | auto (−1) |
| Ethernet IP101 | MDC 31, MDIO 52, PWR 51, CLK 50 |
| C6 hosted SDIO | CLK 18, CMD 19, D0–3 14–17, RST 54 |
| Wi‑Fi | vía **ESP32-C6** (hosted); Ethernet es el camino confiable para MQTT |

Detalle: `firmware/saj_pdm30_edge/README_GUITION_P4.md`.

### VDF SAJ PDM-30

- Mapa descubierto: **P0-ii → holding `0x00ii`**, **P1-ii → `0x01ii`**
- Especiales: `0x1000` set %, `0x1001` f, `0x1002` Vbus, `0x1004` I, `0x2000` cmd, `0x3000` status
- Comandos: `1=fwd`, `6=decel stop`, `5=free stop`, `7=reset`

---

## 5. Protocolo de aplicación (CLI / MQTT)

### Comandos CLI (Serial o MQTT `.../cmd`)

```
help | ping | dump | stream on|off
r0|r1 <ii>     w0|w1 <ii> <float_eng>
start | stop | estop | reset | set <pct>
slave <id>
wifi status | wifi set <ssid> <pass> | wifi reconnect
wifi profile list|save <name> <ssid> <pass>|use <name>|delete <name>
mqtt status | mqtt set <host> [port] | mqtt user <u> <p>
mqtt enable | mqtt disable
```

Valores `r0/w0` son **ingeniería** (float), no raw. Escalas en `ScaleTable.cpp`.

### Topics MQTT

```
saj/pdm30/saj-pdm30/cmd
saj/pdm30/saj-pdm30/rsp
saj/pdm30/saj-pdm30/telemetry
saj/pdm30/saj-pdm30/status          # online / offline (LWT)
```

Telemetría ejemplo:
```json
{"freq":0.00,"amp":0.00,"vdc":310.0,"vout":220,"status":"stop"}
```

### AP de campo (firmware)

- SSID: `SAJ_Diag_Tool`
- Pass: `sajpdm30`
- IP: `192.168.4.1`

### Red de prueba usada

- SSID: `REDACTED_SSID`
- Password: `********` (también en `desktop_app/config/connection_profiles.json` perfil **ROWA**)
- Perfil MQTT de ejemplo: `Local Mosquitto` → `127.0.0.1:1883` (solo útil si broker y app están en la misma máquina; el ESP necesita la **IP LAN del broker**)

---

## 6. Cómo construir y ejecutar (comandos listos)

### PlatformIO (venv del proyecto)

```bash
export PATH="/home/master-pi/Desktop/VF patron/firmware/.pio-venv/bin:$PATH"
cd "/home/master-pi/Desktop/VF patron/firmware/saj_pdm30_edge"

# ESP32 clásico
pio run -e esp32dev
pio run -e esp32dev -t upload --upload-port /dev/ttyACM0

# Guition P4
pio run -e guition_jc_esp32p4_m3
pio run -e guition_jc_esp32p4_m3 -t upload --upload-port /dev/ttyACM0

pio device monitor -b 115200
```

Si el upload falla con “No serial data received”: modo descarga manual (**BOOT** + pulso **EN**).

### App desktop

```bash
cd "/home/master-pi/Desktop/VF patron/desktop_app"
source .venv/bin/activate
pip install -r requirements.txt   # customtkinter, pyserial, paho-mqtt
python main.py
```

Broker local (para MQTT):

```bash
sudo apt install -y mosquitto mosquitto-clients
sudo systemctl enable --now mosquitto
# Comprobar
mosquitto_sub -h 127.0.0.1 -t 'saj/pdm30/#' -v
```

**Importante:** en el ESP, `mqtt set` debe apuntar a la IP del PC/servidor en la LAN (no `127.0.0.1` desde el ESP).

### Secuencia de puesta en marcha típica (MQTT)

1. Flashear firmware Edge (board correcta).
2. Conectar Serial → configurar Wi‑Fi o Ethernet:
   ```text
   wifi profile save ROWA REDACTED_SSID ********
   wifi profile use ROWA
   wifi status
   mqtt set <IP_PC_EN_LAN> 1883
   mqtt enable
   mqtt status
   ```
3. En PC: Mosquitto en marcha.
4. App → modo **MQTT** → perfil broker → Conectar → `stream on` automático.

---

## 7. Decisiones de diseño (no reabrir sin motivo)

1. **Sin `delay()`** en firmware; SM Modbus + `millis()`.
2. **Sin `String` Arduino** en código propio; `snprintf` + buffers estáticos.
3. **MQTT > WebSocket** para multiplataforma y dumps grandes.
4. **Mapa GROUP_DIRECT** (no F-style) confirmado en hardware.
5. Dump: **1 frame multi-línea por chunk de 12** + gap 60 ms (evita saturar colas TX).
6. Compare en app: flag `_busy` + timeout deslizante + botón **Cancelar op.**

---

## 8. Problemas conocidos / pendientes

| ID | Tema | Notas |
|----|------|--------|
| P1 | Flasheo por ACM0 (Uno sin MCU) | Requiere BOOT+EN manual |
| P2 | MQTT end-to-end en campo | Validar con Mosquitto en LAN y firmware MQTT flasheado |
| P3 | Wi‑Fi en Guition P4 | Depende de ESP-Hosted/C6; Ethernet es plan A |
| P4 | DE del MAX485 Guition | Auto (−1); si half-duplex falla, mapear EN a un GPIO real del rev. de PCB |
| P5 | UI táctil Guition | No hay LVGL/HMI en este firmware (solo Edge) |
| P6 | SSID/pass con espacios | CLI no soporta; perfiles sin espacios |
| P7 | IP DHCP del ESP | Anotar tras `wifi status` / `mqtt status` |
| P8 | App: rebuild PyInstaller | Ejecutables Linux viejos pueden no incluir MQTT/perfiles |

---

## 9. Siguiente trabajo sugerido (prioridad)

1. **Flashear** firmware MQTT actual en la unidad de campo (esp32dev o Guition).
2. Instalar/usar **Mosquitto en la LAN** y validar:
   - `mosquitto_pub -t saj/pdm30/saj-pdm30/cmd -m ping`
   - App modo MQTT + telemetría + dump/compare.
3. En Guition: validar **RS485 onboard** con VDF y **Ethernet → MQTT**.
4. Si hace falta HMI en pantalla Guition: nueva iteración LVGL (separada del Edge core).
5. Endurecer seguridad: password AP, MQTT auth, no credenciales en claro en git si el repo es público.

---

## 10. Checklist rápido al abrir nueva shell

```bash
# 1) Ir al workspace
cd "/home/master-pi/Desktop/VF patron"

# 2) Leer este handoff
less CONTINUACION_ITERACION.md

# 3) Ver puertos
ls -la /dev/ttyACM* /dev/ttyUSB*

# 4) Build firmware
export PATH="$PWD/firmware/.pio-venv/bin:$PATH"
cd firmware/saj_pdm30_edge && pio run -e esp32dev   # o guition_jc_esp32p4_m3

# 5) App
cd ../../desktop_app && source .venv/bin/activate && python main.py
```

---

## 11. Contacto técnico del diseño

- Protocolo VDF: manuales en `docs/PDM30_User_Manual.pdf`, `docs/PDH30_User_Manual.pdf` (Modbus familia PDH30).
- Discovery histórico: `results/` y sketches en `arduino/saj_pdm30_discover/`.

**Fin del handoff.** Cualquier agente o humano que continúe debería actualizar este archivo al cerrar la siguiente sesión.
