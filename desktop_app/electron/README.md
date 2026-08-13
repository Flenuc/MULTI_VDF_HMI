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
cd desktop_app          # una sola vez desde el repo
./build_desktop_linux.sh
# → electron/dist/MULTI_VDF_HMI-*-arm64.AppImage
```

**Nota:** el target `.deb` no se genera en Raspberry Pi (aarch64): electron-builder
usa `fpm` x86. En x86_64 Linux puedes forzar: `cd electron && npm run dist:linux:deb`.

### Ejecutar

```bash
# Si ya estás en desktop_app:
chmod +x electron/dist/MULTI_VDF_HMI-*.AppImage
./electron/dist/MULTI_VDF_HMI-0.2.0-arm64.AppImage

# Dev (Electron + backend .venv o binario en resources/):
cd electron    # NO "cd desktop_app/electron" si ya estás en desktop_app
npm start
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

## Import / export JSON (listas de parámetros)

En el pack Electron, la UI usa diálogos nativos vía `preload` + IPC:

| Acción UI | Comportamiento desktop |
|-----------|------------------------|
| **Abrir JSON…** | `dialog.showOpenDialog` → lee `.json` del disco |
| **Guardar como…** | `dialog.showSaveDialog` → escribe `.json` |
| **Guardar en servidor** | API `PUT /param-lists/…` (carpeta `param_lists/`) |
| **Export + servidor** | Guarda en disco y copia a `param_lists/` |

En navegador (sin Electron): file picker HTML + descarga.
