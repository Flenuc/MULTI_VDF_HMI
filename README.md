# SAJ PDM-30 Edge / field tools

Stack de campo para el variador **SAJ PDM-30**:

| Pieza | Ruta | Descripción |
|-------|------|-------------|
| **Firmware Edge** | `firmware/saj_pdm30_edge/` | ESP32 / Guition P4 — Modbus RTU master, SoftAP, MQTT, BLE NUS / BT SPP |
| **App de escritorio** | `desktop_app/` | CustomTkinter — USB, MQTT, Bluetooth LE (NUS), SPP, perfiles Wi‑Fi |
| **Sketches legacy** | `arduino/` | Descubrimiento / CLI Arduino clásico |
| **Scripts / resultados** | `scripts/`, `results/` | Tests de conectividad y capturas |
| **Docs** | `docs/`, `CONTINUACION_ITERACION.md` | Manuales y handoff de iteración |

El manual del PDM-30 **no publica** el mapa registro↔parámetro; se usó el de la familia **PDH30** y descubrimiento por lectura.

### Placas firmware (PlatformIO)

```bash
cd firmware/saj_pdm30_edge
# ESP32 DevKit + SN75176 (+ Bluetooth Classic SPP)
pio run -e esp32dev -t upload
# Guition JC-ESP32P4-M3-DEV (RS485 onboard, MQTT, BLE NUS)
pio run -e guition_jc_esp32p4_m3 -t upload
```

### App

```bash
cd desktop_app
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# Copiar perfiles de ejemplo (no se versionan secretos locales)
cp config/connection_profiles.example.json config/connection_profiles.json
python main.py
```

### Flasheo (GUI + paquetes)

```bash
# Generar zip + manifest (local)
python3 scripts/package_firmware.py --version 0.1.0
# → dist/firmware/MULTI_VDF_HMI-firmware-0.1.0.zip

# GUI: baja el último release de GitHub y graba el micro
cd desktop_app && python run_flasher.py
```

Repo público de releases: **https://github.com/Flenuc/MULTI_VDF_HMI**  
CI: tag `v*` → workflow `.github/workflows/release-firmware.yml` publica el zip.

### Git / secretos / protocolo

- `desktop_app/config/connection_profiles.json` está en **`.gitignore`** (Wi‑Fi/MQTT reales).
- Usá `connection_profiles.example.json` como plantilla.
- Builds PlatformIO (`.pio/`), `dist/` y venvs no se suben.
- Seguridad planta/lab: **`docs/SECURITY.md`** (MQTT auth, SoftAP, fail-safe).
- Contrato CLI/MQTT: **`docs/PROTOCOL.md`**.
- CI: `.github/workflows/secret-scan.yml` (gitleaks).

---

# SAJ PDM-30 ↔ ESP32 (Modbus RTU / RS485) — contexto histórico

Programa Arduino para **ESP32** que se comunica con el variador **SAJ PDM-30** por RS485 (Modbus RTU), más herramientas para **descubrir la dirección de memoria** de cada parámetro `P0-00`…`P0-47` y `P1-00`…`P1-47`.

El manual del PDM-30 **no publica** el mapa registro↔parámetro. El de la familia **PDH30** sí documenta el protocolo Mod-Bus y un ejemplo de codificación (`F3.15` → `0xF30F`). Este proyecto se basa en eso y en un **descubrimiento por lectura** (fingerprint de defaults + modo *watch*).

Manuales descargados en `docs/`.

---

## Hardware

```
ESP32  ──UART──  conversor RS485 (MAX485 / SP3485 / …)  ──A+/B-──  VDF SAJ PDM-30
                      │
                     DE/RE (dirección TX/RX)
```

| Señal ESP32 (por defecto) | Conversor RS485 | VFD PDM-30 |
|---------------------------|-----------------|------------|
| GPIO 17 (TX)              | DI              | —          |
| GPIO 16 (RX)              | RO              | —          |
| GPIO 4                    | DE + RE unidos  | —          |
| GND                       | GND             | GND (recomendado) |
| —                         | A+              | A+ (S+)    |
| —                         | B−              | B− (S−)    |

Pines configurables en `arduino/*/config.h`.

### Ajustes en el VFD (panel)

| Parámetro | Valor | Significado |
|-----------|-------|-------------|
| **P1-35** | `1` | Dirección Modbus (slave ID) |
| **P1-36** | `1` | Baud **9600** |
| **P1-37** | `0` | Formato **8N1** |
| **P1-34** | `2` | Fuente de mando = **serie** (solo para arrancar/parar por Modbus) |
| **P1-38** | `2` | Retardo de respuesta (ms), por defecto |

Si cambias baud/ID en el VFD, replica en `config.h`.

---

## Protocolo (familia SAJ / PDH30 Ch.6)

- **Modbus RTU**
- **FC 0x03** leer holding registers  
- **FC 0x06** escribir un registro  
- Lectura continua de parámetros: máximo **12** registros  

### Registros especiales (telemetría / control)

| Dirección | Acceso | Significado |
|-----------|--------|-------------|
| `0x1000` | R/W | Consigna frecuencia en % de f.max (−10000…10000 = −100.00%…100.00%) |
| `0x1001` | R | Frecuencia de marcha (0.01 Hz) |
| `0x1002` | R | Tensión de bus (0.1 V) |
| `0x1003` | R | Tensión de salida (1 V) |
| `0x1004` | R | Corriente de salida (0.01 A) |
| `0x1005`…`0x100E` | R | Potencia, par, RPM, DI/DO, AI, horas, energía |
| `0x100F` | R | Presión consignada (0.1 bar) |
| `0x1010` | R | Presión real (0.1 bar) |
| `0x2000` | W | Comando: 1=fwd, 2=rev, 5=parada libre, 6=parada decelerada, 7=reset fallo |
| `0x3000` | R | Estado: 1=fwd, 2=rev, 3=stop |

### Codificación de parámetros Pn.mm (a confirmar con discovery)

En PDH30: `F3.15` → dirección `0xF30F` (byte alto = grupo con prefijo `0xF`, byte bajo = índice).

Para PDM-30 se prueban tres esquemas:

| Esquema | `P0-12` | `P1-35` |
|---------|---------|---------|
| **0** `MAP_GROUP_DIRECT` | `0x000C` | `0x0123` |
| **1** `MAP_F_STYLE` (tipo PDH30) | `0xF00C` | `0xF123` |
| **2** `MAP_GROUP_100` | `12` | `135` |

Tras el descubrimiento, fija el esquema en `config.h` (`PARAM_MAP_SCHEME`).

---

## Proyectos Arduino

### 1. Control normal — `arduino/saj_pdm30_modbus/`

Abre la carpeta en Arduino IDE (o PlatformIO), placa **ESP32**, sube el sketch.

Monitor serie **115200**. Comandos:

| Comando | Acción |
|---------|--------|
| `h` | ayuda |
| `s` | estado + telemetría |
| `p` | presiones |
| `r 0 0` | leer P0-00 |
| `w 0 0 40` | escribir P0-00 = 40 (raw → 4.0 bar si unidad 0.1) |
| `f 5000` | consignar 50.00 % de f.max |
| `go` / `stop` / `estop` / `reset` | marcha / parada / paro libre / reset |
| `scan` | sondear registros especiales |
| `map 1` | forzar esquema de direcciones |

### 2. Descubrimiento de mapa — `arduino/saj_pdm30_discover/`

**Solo lecturas** (salvo que tú escribas a mano). Flujo recomendado:

1. Sube `saj_pdm30_discover`, abre monitor serie 115200.  
2. `ping` — comprueba enlace.  
3. `schemes` — puntúa los 3 esquemas con defaults de fábrica del manual.  
4. Si la confianza es alta → `csv` o `dump` y guarda el log.  
5. Si no → `watch`:  
   - el ESP32 hace un snapshot de candidatos,  
   - **tú cambias un solo parámetro en el teclado del VFD** (p.ej. P0-00 de 3.0 → 4.0),  
   - al cabo de 15 s relee y muestra qué dirección cambió y a qué `Pn-ii` corresponde.  
6. Opcional: `fullscan` (lento) vuelca todos los registros legibles en rangos típicos.

Copia el log del monitor a un archivo y parsea:

```bash
python3 scripts/parse_discovery_log.py mi_captura.txt -o param_map.csv
```

O automatiza el puerto USB (p.ej. `/dev/ttyACM0`):

```bash
pip install pyserial
python3 scripts/discover_via_serial.py --port /dev/ttyACM0 --cmd schemes
python3 scripts/discover_via_serial.py --port /dev/ttyACM0 --cmd csv -o discovery_capture.txt
```

---

## Valores raw vs. display

El registro guarda un **entero**; la unidad está en el manual:

| Ejemplo | Display | Unidad | Valor Modbus típico |
|---------|---------|--------|---------------------|
| P0-00   | 3.0 bar | 0.1 bar | `30` |
| P0-36   | 2.0 s   | 0.1 s   | `20` |
| 0x1001  | 50.00 Hz| 0.01 Hz | `5000` |
| 0x1010  | 2.5 bar | 0.1 bar | `25` |

Al escribir con `w G I V`, usa siempre el **entero raw**.

---

## Seguridad

- No escribas direcciones al azar: puedes alterar protecciones o bloquear parámetros.  
- El discovery es **solo lectura**.  
- Para marcha/paro por bus: `P1-34 = 2` y ten a mano la parada de emergencia del VFD.  
- No uses `P0-38` (inicialización) salvo que sepas lo que haces.

---

## Estructura del repo

```
VF patron/
├── README.md
├── docs/                          # manuales PDM30 / PDH30
├── include/saj_pdm30_protocol.h   # definiciones compartidas
├── arduino/
│   ├── saj_pdm30_modbus/          # control diario
│   └── saj_pdm30_discover/        # mapeo P0/P1 ↔ dirección
└── scripts/
    ├── discover_via_serial.py
    └── parse_discovery_log.py
```

---

## Siguiente paso tras mapear

1. Anota el **esquema ganador** en `config.h` → `PARAM_MAP_SCHEME`.  
2. Guarda `param_map.csv` como referencia.  
3. Usa `saj_pdm30_modbus` para control/PID/presión según tu aplicación.

Si tras `ping` no hay respuesta: invierte A/B, verifica GND común, DE pin, baud e ID slave.
