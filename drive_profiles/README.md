# Drive profiles (multi-VDF)

Catálogos de variador para VarioField. Ver roadmap: `docs/ROADMAP_MULTI_VDF.md`.

## Estado

| Profile ID | Modelo | Estado |
|------------|--------|--------|
| `saj.pdm30` | SAJ PDM-30 | **production** (generado desde firmware de campo) |
| `saj.pdh30` | SAJ PDH-30 | **catalog_from_manual** (F0–F9, FD, FE, D0, E0; mapa F-style) |
| `saj.pd20` | SAJ PD-20 | planned |
| `saj.8200b` | SAJ 8200B | planned |
| `danfoss.vlt_micro` | Danfoss VLT Micro | planned (cuando haya unidad) |
| `bedford.w713ba` | Bedford W713ba | planned (spike de protocolo) |

## Regenerar perfiles SAJ

```bash
# PDM-30 (firmware de campo)
python3 tools/catalog_builder/generate_saj_pdm30_profile.py

# PDH-30 (manual Ch.4: F0–F9, FD, FE, D0, E0)
python3 tools/catalog_builder/extract_pdh30_from_manual.py
# → drive_profiles/saj/pdh30/profile.json
# → drive_profiles/saj/pdh30/parameters.csv
# → drive_profiles/saj/pdh30/plant_priority_ids.json
```

### Grupos PDH-30 mapeados

| Grupo | Uso típico | Address |
|-------|------------|---------|
| F0–F9 | Función (bomba, motor, PID, com…) | `0xFnmm` (F3.15→`0xF30F`) |
| FD | Usuario / fábrica / lock | `0xFDmm` |
| FE | Agente / tiempos | `0xFEmm` |
| D0 | Monitor en vivo | `0x1000…` (tabla Ch.6) |
| E0 | Histórico de fallos | `0xE0mm` (verificar en banco) |

**F6:** no aparece en el manual extractado (0 códigos).

## Spike mapa PDH-30 (taller)

1. Edge flasheado con firmware de campo, RS485 al **PDH-30** (slave 1, 9600 8N1 típico).
2. USB del Edge al PC (`/dev/ttyACM0` o COMx).
3. Cerrar VarioField / monitores serie.
4. Ejecutar:

```bash
# PDH-30
python3 tools/spike_pdh30_map.py --port /dev/ttyACM0 --label pdh30

# Regresión PDM-30 (mismo Edge, cable al PDM)
python3 tools/spike_pdh30_map.py --port /dev/ttyACM0 --label pdm30 --also-cli
```

5. Revisar `results/spike_map_*.json` — el scheme con mayor `score` y valores coherentes con el display del VDF gana.

## Convención de escalas

`eng = raw / scale` (igual que `ScaleTable` del Edge).  
Ej.: scale 10, raw 26 → 2.6 bar.
