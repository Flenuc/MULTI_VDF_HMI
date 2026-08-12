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

**Nueva (multiplataforma):** React Native (Expo) + backend Python local.

```
frontend/ (Expo RN)  ──HTTP/WS──►  backend/ (FastAPI)
                                        │
                                        ▼
comms/ ── Serial · MQTT · BT SPP · BLE NUS · Dummy
```

Ver **[ARCHITECTURE.md](./ARCHITECTURE.md)** para detalles y API.

```bash
# Backend (transportes)
./run_backend.sh

# UI React Native (web desktop)
./run_rn_web.sh

# App de escritorio empaquetada (Electron + backend embebido)
./build_desktop_linux.sh          # → electron/dist/*.AppImage
# Windows (en PC x64): build_desktop_windows.bat
# Dev shell:  cd electron && npm install && npm start
```

**Legacy (sigue operativo):** CustomTkinter en-proceso.

```
GUI (CustomTkinter) ── CommsClient ──┬── SerialClient
                                     ├── BleNusClient / BluetoothClient
                                     ├── MqttClient / DummyClient
```

UI CTk no bloqueante: cola de eventos + `after(40ms)`.

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

## Flasheo de firmwares (GUI)

Herramienta para bajar el **último release** de GitHub (`Flenuc/MULTI_VDF_HMI`) y grabar el micro con **esptool**:

```bash
cd desktop_app
pip install -r requirements.txt   # incluye esptool
python run_flasher.py
# o: ./run_flasher.sh
```

1. **Buscar último firmware** (API Releases + zip `MULTI_VDF_HMI-firmware-*.zip`)
2. Elegir placa (`guition_jc_esp32p4_m3` / `esp32dev`) y puerto serial
3. **Flashear**

También podés **Cargar carpeta local…** apuntando a `dist/firmware/<version>/manifest.json` generado con:

```bash
python3 scripts/package_firmware.py --version 0.1.0
```

CI: al pushear un tag `v*` se ejecuta `.github/workflows/release-firmware.yml` y publica el zip en Releases.
