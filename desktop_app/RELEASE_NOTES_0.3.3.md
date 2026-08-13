# VarioField 0.3.3 — Notas de versión (producción)

**Fecha:** 2026-08-13  
**Producto:** VarioField — recetas y enlace a variadores en campo  
**Código interno:** MULTI_VDF_HMI

## Qué hay de nuevo (desde 0.3.2)

- **Bluetooth Classic SPP estable** en Windows y Linux (RFCOMM + COM en Windows; scan off / timeouts en Linux).
- **Broker MQTT local (Mosquitto)** con instalación y configuración asistida:
  - Botón en la app: **«Preparar broker local (Mosquitto)»**
  - Scripts: `desktop_app/scripts/setup_mosquitto.sh` (Linux) y `setup_mosquitto.ps1` (Windows)
  - API: `GET /broker/status`, `POST /broker/setup`
  - Crea/asegura el perfil **Local Mosquitto** (127.0.0.1:1883)
- **Multi-VDF / SAJ PDH-30 (perfil `saj.pdh30`)**:
  - Edge CLI: `profile set|get`, `pget`/`pset` por ID (`F0.00`…), `dump` profile-aware
  - App: selector de modelo, recetas por ID, nombres del manual en filas, compare/sync con espera de respuesta
  - Receta planta: `param_lists/ejemplo_pdh30.json`
  - Banco: dump completo ~97 % OK; E2E receta compare+sync
- Empaques actualizados (AppImage arm64 + Setup Windows Electron).

## Archivos de esta release

| Archivo | Plataforma | Uso |
|---------|------------|-----|
| `VarioField-0.3.3-arm64.AppImage` | Linux ARM64 (Raspberry Pi) | Ejecutable portable (Electron) |
| `VarioField-Setup-0.3.3.exe` | Windows 10/11 x64 | Instalador Electron + Python embed + scripts Mosquitto |
| `VarioField-Electron-Setup-0.3.3.exe` | Windows 10/11 x64 | Mismo instalador (nombre explícito) |

Descargas: https://github.com/Flenuc/MULTI_VDF_HMI/releases/tag/v0.3.3

## Mosquitto (broker local)

### Desde la app
1. Modo de conexión **Red / Wi‑Fi (MQTT)**.
2. Pulsa **Preparar broker local (Mosquitto)**.
3. Si pide permisos de administrador:
   - **Linux:** `sudo bash …/scripts/setup_mosquitto.sh`
   - **Windows (admin):** `powershell -ExecutionPolicy Bypass -File …\scripts\setup_mosquitto.ps1`
4. Usa el perfil **Local Mosquitto** (127.0.0.1:1883).
5. En el **Edge**, apunta al broker con la **IP LAN de este PC** (no 127.0.0.1):  
   `mqtt set <IP_DEL_PC> 1883`

### Manual (Linux)
```bash
sudo bash desktop_app/scripts/setup_mosquitto.sh
# o:
sudo apt install mosquitto mosquitto-clients
sudo systemctl enable --now mosquitto
```

### Manual (Windows)
```powershell
winget install EclipseFoundation.Mosquitto
# o el script setup_mosquitto.ps1 como Administrador
```

Config de campo (anónimo, puerto 1883): `scripts/mosquitto-variofield.conf`.

> En planta, el broker en el PC de trabajo debe ser alcanzable por Wi‑Fi desde el módulo.  
> Ajustá firewall si hace falta (TCP 1883).

## Instalación Windows

1. Ejecutá `VarioField-Setup-0.3.3.exe` (SmartScreen: Más info → Ejecutar de todas formas).
2. Atajo **VarioField** → ventana Electron.
3. Carpeta: `%LOCALAPPDATA%\MULTI_VDF_HMI\VarioField`

## Instalación Linux AppImage

```bash
chmod +x VarioField-0.3.3-arm64.AppImage
./VarioField-0.3.3-arm64.AppImage
```

Mosquitto no va *dentro* del AppImage (es un servicio del sistema). Usá el botón de la app o el script con `sudo`.

## Cómo usar (resumen operario)

1. **Inicio → Conectar el módulo** (cable, red o Bluetooth).  
2. **Elegir la receta**.  
3. **Comprobar** el variador.  
4. **Enviar** la receta.  

## Checklist QA de campo (v0.3.3)

### Empaque
- [ ] AppImage arm64 arranca sin error de backend
- [ ] Setup Windows instala y abre ventana Electron
- [ ] `/health` devuelve version `0.3.3`

### Conexiones
- [ ] USB: listar puerto, conectar, telemetría
- [ ] MQTT: broker local con «Preparar Mosquitto» o script; perfil Local Mosquitto; conectar
- [ ] MQTT Edge: `mqtt set <IP_PC> 1883` y stream desde módulo
- [ ] Bluetooth Classic: buscar SAJ-PDM30-Edge, conectar, telemetría (Linux y Windows)
- [ ] BT no cae tras “SPP ready” (bug timeout corregido)

### Producto
- [ ] Tutorial: saltar y reabrir desde Ayuda
- [ ] Abrir / guardar receta JSON
- [ ] Buscar parámetro
- [ ] Comparar y enviar (con y sin comparar)
- [ ] Banner de error con reintentar

### Mosquitto
- [ ] Sin Mosquitto: botón indica comando elevado
- [ ] Con script/sudo: puerto 1883 abierto; perfil creado
- [ ] Re-ejecutar script es idempotente

## Compilar de nuevo

```bash
# Linux AppImage (en el host de la arquitectura)
cd desktop_app && ./build_desktop_linux.sh

# Windows Setup Electron (desde Linux, incl. Pi)
cd desktop_app && ./build_variofield_windows_electron_setup.sh

# Solo Mosquitto
sudo ./desktop_app/scripts/setup_mosquitto.sh
```

## Notas técnicas

- Backend local: `127.0.0.1:8765`
- Repo: https://github.com/Flenuc/MULTI_VDF_HMI
- Roadmap UX: `frontend/UX_PRODUCTION_ROADMAP.md` (siguiente: Fase 5 roles)
