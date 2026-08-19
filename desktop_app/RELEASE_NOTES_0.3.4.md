# VarioField 0.3.4

## Cambios

- Conexión MQTT por **Edge id** (`vf-XXXXXX`): campo de prefijo + **Buscar módulos**
- Backend `POST /mqtt/discover` (lista Edges online en el broker)
- Catálogos `drive_profiles` empaquetados
- Mosquitto scripts con auth/ACL por defecto

## Asset Linux (ARM64)

`VarioField-0.3.4-arm64.AppImage`

```bash
chmod +x VarioField-0.3.4-arm64.AppImage
./VarioField-0.3.4-arm64.AppImage
```

## Uso MQTT

1. Equipo → Por red → perfil Local Mosquitto  
2. **Buscar módulos** → elegir `vf-7cf194` / `vf-e23fc4`  
3. Conectar  

Firmware Edge recomendado: **≥ 0.3.8** (ids por placa).
