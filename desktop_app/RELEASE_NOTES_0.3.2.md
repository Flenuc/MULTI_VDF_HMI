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

## Archivos de esta release

| Archivo | Plataforma | Uso |
|---------|------------|-----|
| `VarioField-0.3.2-arm64.AppImage` | Linux ARM64 (Raspberry Pi) | Ejecutable portable |
| `VarioField-0.3.2-x64.AppImage` | Linux x86_64 (si se genera) | Ejecutable portable |
| `VarioField-Setup-0.3.2.exe` | Windows x64 (si se genera en PC Windows) | Instalador |

> En Raspberry Pi solo se genera el AppImage **arm64**. Windows y Linux x64 se construyen en un PC con esa arquitectura.

## Cómo instalar / ejecutar (Linux AppImage)

```bash
chmod +x VarioField-0.3.2-arm64.AppImage
./VarioField-0.3.2-arm64.AppImage
```

## Cómo usar (resumen)

1. **Inicio → Conectar el módulo** (cable, red o Bluetooth).  
2. **Elegir la receta** (archivo o lista del PC).  
3. **Comprobar** el variador (recomendado).  
4. **Enviar** la receta al variador.  

Ayuda → “Ver tutorial otra vez” si lo necesitas.

## Requisitos del PC

- Linux con soporte AppImage (o Windows con el instalador).
- Para Bluetooth Classic: BlueZ (Linux).
- Para USB: drivers del convertidor UART.
- Para red: broker MQTT alcanzable (p. ej. Mosquitto en el PC de planta).

## Notas técnicas (para el técnico de planta)

- Backend local en `127.0.0.1:8765` (no visible al operario).
- Firmwares Edge: release de firmwares del mismo repositorio (`esp32dev`, Guition).
- Repo: https://github.com/Flenuc/MULTI_VDF_HMI

## Checklist QA de campo (antes de dar por buena la release)

- [ ] Arranque AppImage / instalador sin consola de error
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
# Linux (en el host de la arquitectura deseada)
cd desktop_app
./build_desktop_linux.sh

# Windows x64
build_desktop_windows.bat
```
