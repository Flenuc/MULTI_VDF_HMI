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

## Siguiente después del spike

1. Actualizar `drive_profiles/saj/pdh30/profile.json`:
   - `status`: `validated` si f_style (u otro) confirmado
   - rellenar `parameters[]` desde manual + escalas
2. Firmware: `profile set saj.pdh30` + address scheme runtime
3. App: selector de modelo + recetas con `drive_profile_id`

## Checklist de campo (imprimir)

- [ ] PDH-30: spike JSON guardado en `results/`
- [ ] Scheme recomendado: _______________
- [ ] Slave id leído: _______________
- [ ] Fmax raw leído: _______________ (display VDF: _____ Hz)
- [ ] PDM-30 regresión: group_direct OK
- [ ] Foto / nota de cableado RS485
