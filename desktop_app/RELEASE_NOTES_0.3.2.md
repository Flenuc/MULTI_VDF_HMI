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
- Instalador Windows generable desde Linux (mismo método que el flasher).

## Archivos de esta release

| Archivo | Plataforma | Uso |
|---------|------------|-----|
| `VarioField-0.3.2-arm64.AppImage` | Linux ARM64 (Raspberry Pi) | Ejecutable portable (Electron) |
| `VarioField-Setup-0.3.2.exe` | Windows 10/11 **x64** | Instalador de campo (backend Python + UI web) |
| `VarioField-0.3.2-x64.AppImage` | Linux x86_64 | *Opcional* — cuando se genere en un host x64 o CI |

Descargas: https://github.com/Flenuc/MULTI_VDF_HMI/releases/tag/v0.3.2

## Cómo instalar / ejecutar (Windows)

### 1. Descargar e instalar

1. Descargue **`VarioField-Setup-0.3.2.exe`** de la release.
2. Ejecútelo en un PC **Windows 10/11 de 64 bits**.
3. Si SmartScreen avisa: **Más información → Ejecutar de todas formas**.
4. Siga el asistente (instalación por usuario, sin permisos de administrador).

### 2. Primera instalación (Internet)

- Si el PC **no tiene Python 3.12**, el setup lo instala solo (usuario actual).
- Luego ejecuta `pip` para instalar dependencias (`fastapi`, `uvicorn`, `pyserial`, `bleak`, etc.).
- **Hace falta Internet solo la primera vez** (o si re-ejecuta `post_install.bat`).

### 3. Arrancar la app

1. Atajo de escritorio o menú Inicio → **VarioField**.
2. Se abre una **ventana de consola** (es normal: es el servicio local).
3. Se abre el **navegador** en `http://127.0.0.1:8765` con la interfaz.
4. **Deje la consola abierta** mientras use la app.
5. **Cierre la consola** para detener el servicio.

### 4. Si no arranca

Carpeta por defecto:

```text
%LOCALAPPDATA%\MULTI_VDF_HMI\VarioField
```

Dentro, ejecute **`post_install.bat`** (con Internet) y vuelva a abrir **VarioField**.

### Notas del paquete Windows

- Es el instalador **alternativo de campo** (igual filosofía que el flasher): fuentes Python + UI web exportada, compilado con NSIS en Linux.
- **No es** el empaquetado Electron nativo de `electron-builder` (ese requiere Windows o CI desbloqueado).
- La UI y la API son las de producción 0.3.2; el shell es navegador + backend local.

## Cómo instalar / ejecutar (Linux AppImage)

```bash
chmod +x VarioField-0.3.2-arm64.AppImage
./VarioField-0.3.2-arm64.AppImage
```

Ventana Electron propia (no usa el navegador del sistema).

## Cómo usar (resumen)

1. **Inicio → Conectar el módulo** (cable, red o Bluetooth).  
2. **Elegir la receta** (archivo o lista del PC).  
3. **Comprobar** el variador (recomendado).  
4. **Enviar** la receta al variador.  

Ayuda → “Ver tutorial otra vez” si lo necesitas.

## Requisitos del PC

| | Windows (Setup) | Linux (AppImage) |
|--|-----------------|------------------|
| SO | Windows 10/11 **64-bit** | Linux con soporte AppImage |
| Primera vez | Internet para pip | No (todo embebido) |
| USB | Drivers UART del convertidor | Igual |
| Bluetooth | Stack de Windows / BLE | BlueZ (Classic) |
| Red | Broker MQTT alcanzable | Igual |

## Notas técnicas (para el técnico de planta)

- Backend local en `127.0.0.1:8765` (no expuesto a la red por defecto).
- En Windows el navegador carga la UI servida por ese backend.
- Firmwares Edge: release de firmwares del mismo repositorio (`esp32dev`, Guition).
- Repo: https://github.com/Flenuc/MULTI_VDF_HMI

## Checklist QA de campo (antes de dar por buena la release)

- [ ] Arranque AppImage / instalador sin consola de error
- [ ] Windows: Setup → pip → Launch → navegador en :8765
- [ ] Tutorial: saltar y reabrir desde Ayuda
- [ ] Conexión USB + telemetría
- [ ] Conexión MQTT + ping / stream
- [ ] Bluetooth: buscar y conectar (ESP32 Classic)
- [ ] Abrir / guardar receta JSON
- [ ] Buscar parámetro en la receta
- [ ] Comparar con variador
- [ ] Enviar receta (con y sin comparar previo)
- [ ] Perfil Wi‑Fi / MQTT al módulo (instrucciones visibles)
- [ ] Banner de error con reintento (ej. sin cable USB)

## Compilar de nuevo

```bash
# Linux AppImage (en el host de la arquitectura deseada)
cd desktop_app
./build_desktop_linux.sh

# Windows Setup.exe desde Linux (Raspberry Pi / x64) — no necesita Windows
cd desktop_app
./build_variofield_windows_setup.sh
# → dist/windows/VarioField-Setup-0.3.2.exe

# Windows Electron nativo (solo en PC Windows x64 o CI)
build_desktop_windows.bat
```
