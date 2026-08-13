# VarioField 0.3.2 — Notas de versión (producción)

**Fecha:** 2026-08-12  
**Producto:** VarioField — recetas y enlace a variadores en campo  
**Código interno:** MULTI_VDF_HMI

## Qué es

Aplicación de escritorio para conectar con el módulo de campo (USB, red Wi‑Fi o Bluetooth), ver lecturas en vivo y gestionar **recetas de parámetros** del variador. Pensada para operarios con formación mínima.

## Novedades 0.3.x

- Nombre comercial **VarioField** (multi-marca, no atado a un fabricante).
- Pantalla **Inicio** con 4 pasos grandes: conectar → receta → comprobar → enviar.
- Tutorial al primer uso (se puede saltar y volver a ver en Ayuda).
- Lenguaje de oficio (sin jerga de desarrollo en pantalla).
- Importar / exportar recetas JSON (diálogos nativos en el pack).
- Búsqueda y filtros en la lista de parámetros.
- Avisos de error con **qué hacer** y botón **Reintentar**.
- Enviar receta sin comparar permitido, con recomendación de comparar antes.
- Icono y empaquetado de escritorio (Electron + backend Python).
- Instalador Windows **Electron nativo** generable desde Linux (sin PC Windows ni CI).

## Archivos de esta release

| Archivo | Plataforma | Uso |
|---------|------------|-----|
| `VarioField-0.3.2-arm64.AppImage` | Linux ARM64 (Raspberry Pi) | Ejecutable portable (Electron) |
| `VarioField-Setup-0.3.2.exe` | Windows 10/11 **x64** | **Instalador principal** — Electron nativo + Python embebido |
| `VarioField-Electron-Setup-0.3.2.exe` | Windows 10/11 **x64** | Mismo instalador (nombre explícito) |
| `VarioField-0.3.2-x64.AppImage` | Linux x86_64 | *Opcional* — host x64 o CI |

Descargas: https://github.com/Flenuc/MULTI_VDF_HMI/releases/tag/v0.3.2

## Cómo instalar / ejecutar (Windows — Electron nativo)

### Qué incluye el Setup

- **`VarioField.exe`**: shell Electron (Chromium embebido) — ventana de app, no el navegador del sistema.
- **Python embebido** (`resources/python`) + dependencias Windows ya empaquetadas.
- **Backend** (`resources/pyapp`) y **UI** (`resources/ui`).
- **No requiere** Python, Node ni Internet en el PC destino.

Tamaño orientativo del instalador: ~90–100 MB.

### Instalación

1. Descargue **`VarioField-Setup-0.3.2.exe`** (o `VarioField-Electron-Setup-0.3.2.exe`).
2. Ejecútelo en un PC **Windows 10/11 de 64 bits**.
3. Si SmartScreen avisa: **Más información → Ejecutar de todas formas**.
4. Siga el asistente (instalación por usuario, sin administrador).

### Arranque

1. Atajo de escritorio o menú Inicio → **VarioField**.
2. Se abre la **ventana de la app** (Electron).
3. El backend local queda en `http://127.0.0.1:8765` (la UI lo usa por dentro).
4. Cierre la ventana de VarioField para detener el servicio.

Carpeta por defecto:

```text
%LOCALAPPDATA%\MULTI_VDF_HMI\VarioField
```

### Notas técnicas del pack Windows

| Pieza | Origen |
|-------|--------|
| Electron win32-x64 | Binarios oficiales (descargados en el build) |
| Python 3.12 embed | `python.org` embeddable amd64 |
| Librerías Python | Wheels `win_amd64` preextraídos en site-packages |
| UI | Expo web export (production) |
| Instalador | NSIS (`makensis` en Linux) |

Build desde Raspberry Pi / Linux:

```bash
cd desktop_app
./build_variofield_windows_electron_setup.sh
# → dist/windows/VarioField-Setup-0.3.2.exe
```

> El backend **no** es `multi_vdf_backend.exe` (PyInstaller); es CPython embebido.  
> El resultado de `electron-builder` en Windows/CI sería equivalente en UX, con backend one-file opcional.

## Cómo instalar / ejecutar (Linux AppImage)

```bash
chmod +x VarioField-0.3.2-arm64.AppImage
./VarioField-0.3.2-arm64.AppImage
```

Ventana Electron propia (backend PyInstaller embebido en el AppImage).

## Cómo usar (resumen)

1. **Inicio → Conectar el módulo** (cable, red o Bluetooth).  
2. **Elegir la receta** (archivo o lista del PC).  
3. **Comprobar** el variador (recomendado).  
4. **Enviar** la receta al variador.  

Ayuda → “Ver tutorial otra vez” si lo necesitas.

## Requisitos del PC

| | Windows (Setup Electron) | Linux (AppImage) |
|--|--------------------------|------------------|
| SO | Windows 10/11 **64-bit** | Linux con soporte AppImage |
| Primera vez | Sin Internet (todo embebido) | No |
| USB | Drivers UART del convertidor | Igual |
| Bluetooth | Stack de Windows / BLE | BlueZ (Classic) |
| Red | Broker MQTT alcanzable | Igual |

## Notas técnicas (para el técnico de planta)

- Backend local en `127.0.0.1:8765` (no expuesto a la red por defecto).
- Firmwares Edge: release de firmwares del mismo repositorio (`esp32dev`, Guition).
- Repo: https://github.com/Flenuc/MULTI_VDF_HMI

## Checklist QA de campo

- [ ] Windows: Setup → VarioField.exe abre ventana Electron
- [ ] Windows: UI carga y responde (home / conectar)
- [ ] Linux AppImage: arranque sin error
- [ ] Tutorial: saltar y reabrir desde Ayuda
- [ ] Conexión USB + telemetría
- [ ] Conexión MQTT + ping / stream
- [ ] Bluetooth: buscar y conectar (ESP32 Classic)
- [ ] Abrir / guardar receta JSON
- [ ] Buscar parámetro en la receta
- [ ] Comparar con variador
- [ ] Enviar receta (con y sin comparar previo)
- [ ] Banner de error con reintento

## Compilar de nuevo

```bash
# Linux AppImage (arquitectura del host)
cd desktop_app
./build_desktop_linux.sh

# Windows Setup Electron nativo (desde Linux, incl. Raspberry Pi)
cd desktop_app
./build_variofield_windows_electron_setup.sh

# Windows Setup ligero (solo navegador + pip; sin Electron)
./build_variofield_windows_setup.sh

# Windows electron-builder nativo (solo en PC Windows x64 o CI)
build_desktop_windows.bat
```
