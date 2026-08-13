# Drive profiles (multi-VDF)

Catálogos de variador para VarioField. Ver roadmap: `docs/ROADMAP_MULTI_VDF.md`.

## Estado

| Profile ID | Modelo | Estado |
|------------|--------|--------|
| `saj.pdm30` | SAJ PDM-30 | **production** (generado desde firmware de campo) |
| `saj.pdh30` | SAJ PDH-30 | **spike** (mapa F-style del manual; params pendientes) |
| `saj.pd20` | SAJ PD-20 | planned |
| `saj.8200b` | SAJ 8200B | planned |
| `danfoss.vlt_micro` | Danfoss VLT Micro | planned (cuando haya unidad) |
| `bedford.w713ba` | Bedford W713ba | planned (spike de protocolo) |

## Regenerar PDM-30

```bash
python3 tools/catalog_builder/generate_saj_pdm30_profile.py
```

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
