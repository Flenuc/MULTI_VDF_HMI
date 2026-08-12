# SAJ Edge Configurator

Aplicación de escritorio para el VDF **SAJ PDM-30** vía ESP32 Edge.

## Enlaces soportados

| Modo | Uso |
|------|-----|
| **MQTT** (recomendado) | Multiplataforma, estable, telemetría pub/sub |
| **USB Serial** | Puesta en marcha / sin red |
| **Bluetooth LE (NUS)** | Serie BLE (Nordic UART) — **Guition P4+C6** |
| **Bluetooth (SPP)** | Serie Classic RFCOMM — **ESP32 DevKit** |
| **Simulado** | Pruebas de UI sin hardware |

WebSocket dejó de ser el canal principal (problemas multiplataforma y saturación en dumps).

### Bluetooth LE — Nordic UART (Guition)

- Firmware Guition (`guition_jc_esp32p4_m3`) anuncia **`SAJ-PDM30-Edge`** con servicio NUS.
- App: modo **Bluetooth LE (NUS)** → **Escanear BT** → Conectar.
- Dependencia: `pip install bleak`
- Mismo CLI que USB (líneas + telemetría JSON por notify).

### Bluetooth Classic SPP (ESP32 DevKit)

- Firmware `esp32dev` + **Bluetooth (SPP)** en la app.
- Guition **no** soporta Classic (radio C6 = BLE only).

## Arquitectura

```
GUI (CustomTkinter) ── CommsClient ──┬── SerialClient
                                     ├── BleNusClient (BLE NUS / bleak)
                                     ├── BluetoothClient (SPP / RFCOMM)
                                     ├── MqttClient  (paho-mqtt)
                                     └── DummyClient
```

UI no bloqueante: cola de eventos + `after(40ms)`.

## Perfiles guardados

Archivo: `config/connection_profiles.json`

- **Wi‑Fi**: SSID/pass para enviar al Edge (`wifi profile save/use`)
- **MQTT**: host, puerto, auth, topic prefix

UI: botones **Perfiles…** y **Wi‑Fi Edge…**

## MQTT topics (Edge)

```
saj/pdm30/saj-pdm30/cmd
saj/pdm30/saj-pdm30/rsp
saj/pdm30/saj-pdm30/telemetry
saj/pdm30/saj-pdm30/status
```

Broker local (ejemplo):

```bash
sudo apt install mosquitto mosquitto-clients
sudo systemctl enable --now mosquitto
```

## Ejecución

```bash
cd desktop_app
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```
