# VarioField 0.3.5

## Fix crítico

- **Buscar módulos** fallaba (API 422): el body de `/mqtt/discover` no se parseaba.
- Conexión por prefijo `saj/pdm30/vf-XXXXXX` + acepta escribir solo `vf-XXXXXX`.

## Incluye (desde 0.3.4)

- Campo **Módulo Edge** + discovery MQTT
- Catálogos `drive_profiles`
- Scripts Mosquitto con auth

## Asset Linux (ARM64)

`VarioField-0.3.5-arm64.AppImage`

```bash
chmod +x VarioField-0.3.5-arm64.AppImage
./VarioField-0.3.5-arm64.AppImage
```

Firmware Edge: **≥ 0.3.8**.
