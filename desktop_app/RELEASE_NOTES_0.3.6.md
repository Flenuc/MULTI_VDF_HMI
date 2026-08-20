# VarioField 0.3.6

## Fix: «Buscar módulos» / discovery MQTT

Bluetooth mostraba bien el prefijo (`saj/pdm30/vf-…`) en la consola, pero
**Buscar módulos** fallaba o devolvía lista vacía.

### Causa

Tras activar auth en Mosquitto, el AppImage guardaba los perfiles MQTT en una
ruta no escribible (bundle PyInstaller). El perfil «Local Mosquitto» quedaba
**sin usuario/contraseña**, y discovery no podía listar Edges online.

### Qué cambia

- Perfiles MQTT en `userData/config` (`MULTI_VDF_CONFIG_DIR`), persistentes.
- Error claro si falta usuario/contraseña al pulsar «Buscar módulos».
- Auto-relleno del prefijo MQTT desde líneas BT/USB (`edge id=…`, `mqtt topics cmd=…`).
- Backend: rechazo explícito de discover sin credenciales (rc=5 / auth).

### Qué hacer vos

1. Instalá / abrí **VarioField 0.3.6**.
2. **Más → Red del equipo**: en el perfil del broker, usuario `variofield` y la
   contraseña del setup de Mosquitto (la misma que ya usan los Edges).
3. Equipo → MQTT → **Buscar módulos** → elegí `vf-…` → Conectar.

Si ya conectaste por BT y viste el prefijo en consola, al pasar a MQTT el campo
de prefijo debería rellenarse solo.
