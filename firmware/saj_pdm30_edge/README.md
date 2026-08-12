# SAJ PDM-30 Edge (MQTT)

ESP32 / ESP32-P4: Modbus RS485 + Wi‑Fi (perfiles) + Ethernet (P4) + **MQTT** + Serial CLI.

WebSocket se eliminó a favor de MQTT (más simple y multiplataforma).

## Placas / entornos PlatformIO

| Env | Placa |
|-----|--------|
| `esp32dev` | ESP32 DevKit + SN75176B externo (GPIO 14/25/27) |
| `guition_jc_esp32p4_m3` | **Guition JC-ESP32P4-M3-DEV** (RS485 onboard 26/27 + ETH) |

Detalle P4: ver [`README_GUITION_P4.md`](README_GUITION_P4.md).

## Build / flash

```bash
cd firmware/saj_pdm30_edge

# Classic ESP32
../.pio-venv/bin/pio run -e esp32dev -t upload

# Guition JC-ESP32P4-M3-DEV
../.pio-venv/bin/pio run -e guition_jc_esp32p4_m3 -t upload
```

## Red

| | |
|--|--|
| AP | `SAJ_Diag_Tool` / `sajpdm30` → `192.168.4.1` |
| STA | Perfiles NVS (`wifi profile …`) |
| mDNS | `saj-pdm30.local` |

## MQTT topics

```
saj/pdm30/saj-pdm30/cmd         # PC → ESP (comandos CLI)
saj/pdm30/saj-pdm30/rsp         # ESP → PC (respuestas)
saj/pdm30/saj-pdm30/telemetry   # JSON stream
saj/pdm30/saj-pdm30/status      # online / offline (LWT)

### Bluetooth

| Placa | Radio | Modo app | Nombre BLE/BT |
|-------|--------|----------|----------------|
| **Guition P4+C6** | BLE (NUS) | Bluetooth LE (NUS) | `SAJ-PDM30-Edge` |
| **ESP32 DevKit** | Classic SPP | Bluetooth (SPP) | `SAJ-PDM30-Edge` |

```bash
# Guition — BLE Nordic UART
pio run -e guition_jc_esp32p4_m3 -t upload

# ESP32 classic — SPP
pio run -e esp32dev -t upload
```

Servicio NUS: `6E400001-…` / RX `…002` (write) / TX `…003` (notify).
```

### Configurar broker (USB o ya en MQTT)

```
mqtt set 192.168.203.10 1883
mqtt user miuser mipass   # opcional
mqtt enable
mqtt status
```

### Perfiles Wi‑Fi en el Edge

```
wifi profile save ROWA REDACTED_SSID ********
wifi profile use ROWA
wifi profile list
wifi profile delete ROWA
wifi set SSID PASS          # atajo → perfil "default"
```

## Broker en el PC (ejemplo Mosquitto)

```bash
# Debian/Ubuntu
sudo apt install mosquitto mosquitto-clients
sudo systemctl enable --now mosquitto

# Prueba
mosquitto_sub -h 127.0.0.1 -t 'saj/pdm30/#' -v
mosquitto_pub -h 127.0.0.1 -t 'saj/pdm30/saj-pdm30/cmd' -m 'ping'
```

El broker debe ser alcanzable desde la IP STA del ESP32 (misma LAN).
