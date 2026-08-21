# VarioField 0.3.7

## Catálogo técnico + Catalog Builder M2

### App (Electron)
- **Más → Catálogo VDF** (modo técnico / PIN): tabla editable `name` / `scale` / `map_status`
- Import / export JSON de perfiles de variador
- Variantes `active` / `live_draft` / `merged` + **Aplicar merged/live_draft → active**
- Overlay escribible `MULTI_VDF_DRIVE_PROFILES_USER` (no pisa el AppImage)
- Perfiles MQTT en `userData/config` (fix discover auth de 0.3.6)

### Tools (`python3 -m tools.catalog_builder`)
- `extract-live --via mqtt|serial` → `results/live_extract_*` + `profile.live_draft.json`
- `merge` → `profile.merged.json` + reportes
- Verificado PDH en DevKit + Guition: **148/150 ok (98.7%)**

### Roadmap
- M1 / seguridad / extract-live / merge / UI catálogo: cerrados
- Siguiente: M3 PD-20

## Binarios
- `VarioField-0.3.7-arm64.AppImage` — Raspberry Pi / Linux ARM
- `VarioField-0.3.7-x86_64.AppImage` — Linux x64 (CI)
- `VarioField-Setup-0.3.7.exe` — Windows x64 (CI)
