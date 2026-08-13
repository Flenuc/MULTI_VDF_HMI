# Spike PDH-30 en taller — procedimiento

**Hardware disponible ahora:** Edge + **PDH-30** (prueba de mapa) y **PDM-30** (regresión).  
PD-20 / Danfoss / 8200B / Bedford: cuando haya unidad.

## Preparación

1. Edge con firmware de campo flasheado (VarioField 0.3.3 / stack actual).
2. RS485: Edge A/B/GND ↔ VDF (terminación según instalación).
3. VDF: alimentación ON, dirección Modbus típica **1**, baud **9600 8N1** (confirmar en teclado).
4. USB Edge → PC (`/dev/ttyACM0` en Linux, `COMx` en Windows).
5. **Cerrar** VarioField y cualquier monitor serie.

## Paso A — Spike PDH-30 (mapa)

```bash
cd "/home/master-pi/Desktop/VF patron"   # o ruta del repo
python3 tools/spike_pdh30_map.py --port /dev/ttyACM0 --label pdh30
```

Qué hace:
- `ping` + `slave 1`
- Lee registros especiales `0x1001…0x3000`
- Para cada scheme (`group_direct`, `f_style`, `group_100`) lee fingerprints G0/G1
- Escribe `results/spike_map_pdh30_<timestamp>.json` y `.csv`

**Interpretación:**
- PDH manual dice F3.15 → `0xF30F` → scheme **`f_style`** debería ganar.
- Si gana `group_direct`, el PDH se comporta como el PDM (¡mejor para reutilizar driver!).
- Anotá en el JSON qué valores coinciden con el display del VDF (fmax, dirección, etc.).

## Paso B — Regresión PDM-30

Cambiar RS485 al **PDM-30** (o segundo Edge):

```bash
python3 tools/spike_pdh30_map.py --port /dev/ttyACM0 --label pdm30 --also-cli
```

Esperado: **`group_direct`** gana; `r0`/`r1` devuelven eng+raw coherentes.

## Paso C — Lecturas manuales útiles en CLI Edge

```
ping
slave 1
raw 0xF000          # F0.00 si f_style
raw 0x0000          # P0-00 si group_direct
raw 0xF105          # F1.05 fmax candidate
raw 0x0105          # P1-05 fmax PDM
raw 0x1001          # run freq
raw 0x3000          # status
```

## Catálogo de parámetros (post-spike)

Ya generado desde el manual (grupos pedidos):

```bash
python3 tools/catalog_builder/extract_pdh30_from_manual.py
```

- `drive_profiles/saj/pdh30/profile.json` — F0–F9, FD, FE, D0, E0  
- `drive_profiles/saj/pdh30/parameters.csv` — hoja de trabajo  
- `drive_profiles/saj/pdh30/plant_priority_ids.json` — subset planta (F0,F2,F3,F8,D0)

### Lectura de un F-code con firmware actual

```
raw 0xF000    # F0.00 pre-set pressure
raw 0xF008    # F0.08 sensor range
raw 0xF207    # F2.07 max output frequency
raw 0xF800    # F8.00 comm address
raw 0x1001    # D0.00 operating frequency
```

Fórmula: **Fn.mm → registro `0xF(n)mm`** (ej. F3.15 → `0xF30F`).

## Dump completo en banco (Edge CLI)

```bash
python3 tools/bank_dump_pdh30.py --port /dev/ttyACM0
# → results/pdh30_full_dump_<ts>.{csv,json} + pdh30_full_dump_latest.*
```

**Resultado 2026-08-13 (Guition + PDH, profile saj.pdh30):**
- **146/150 OK (97.3%)** en ~40 s  
- Subset planta (F0/F2/F3/F8/D0): **81/81 OK**  
- Fails recurrentes: `F4.15`, `FD.00` (ya vistos en mapa catálogo)

## Siguiente después del spike + catálogo

1. ✅ Validar dump completo + subset planta
2. Ajustar escalas en profile si eng≠display HMI
3. ✅ Firmware: `profile set saj.pdh30` + pget/pset/dump
4. ✅ App: recetas con `drive_profile_id` + compare/sync por ID
5. ✅ End-to-end receta: `ejemplo_pdh30.json` → dump/compare → pset sync  
   ```bash
   python3 tools/e2e_pdh30_recipe.py --port /dev/ttyACM0
   # App: Conectar USB → modelo «SAJ PDH-30» → receta «PDH30 planta» → Comparar → Enviar
   ```
6. ✅ Selector de modelo en UI (pestañas Equipo + Recetas; filtro de listas; `profile set` al conectar)

## Checklist de campo (imprimir)

- [x] PDH-30: spike JSON guardado en `results/`
- [x] Scheme recomendado: **f_style**
- [x] Dump completo: `pdh30_full_dump_latest.json` (97.3%)
- [ ] Slave id leído: _______________
- [ ] Fmax raw leído: _______________ (display VDF: _____ Hz)
- [ ] PDM-30 regresión: group_direct OK
- [ ] Foto / nota de cableado RS485
