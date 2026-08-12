# MULTI_VDF_HMI — Desktop shell (Electron + Python)

Empaqueta la UI React Native (export web) y el backend FastAPI en una app de escritorio.

```
┌──────────────────────────┐
│  Electron BrowserWindow  │
│  http://127.0.0.1:8765/  │
└────────────┬─────────────┘
             │
┌────────────▼─────────────┐
│  multi_vdf_backend       │  ← PyInstaller (onefile)
│  FastAPI + static UI     │
│  comms/ USB·MQTT·BT·BLE  │
└──────────────────────────┘
```

## Desarrollo (sin empaquetar)

Terminal 1 — backend (opcional si Electron lo lanza):

```bash
cd desktop_app && ./run_backend.sh
```

Terminal 2 — Electron en modo dev (lanza backend con `.venv` si no hay binario):

```bash
cd desktop_app/electron
npm install
npm start
```

O UI en navegador: `./run_rn_web.sh` + `./run_backend.sh`.

## Build Linux (esta máquina)

```bash
cd desktop_app
./build_desktop_linux.sh
# → electron/dist/*.AppImage  y/o  *.deb
```

## Build Windows

En un PC Windows x64 con Python 3.12 + Node:

```bat
cd desktop_app
build_desktop_windows.bat
# → electron/dist\MULTI_VDF_HMI-Setup-0.2.0.exe
```

## Recursos embebidos

Tras el build:

```
electron/resources/
  backend/multi_vdf_backend[.exe]
  ui/          ← expo export web
```

Electron define `MULTI_VDF_UI_DIR` al arrancar el backend.

## Notas

- Un solo puerto **8765** (API + UI estática).
- BT Classic en Linux requiere BlueZ en el host (no va dentro del binario).
- Drivers USB-UART del SO para modo USB.
- AppImage: `chmod +x MULTI_VDF_HMI-*.AppImage && ./MULTI_VDF_HMI-*.AppImage`
