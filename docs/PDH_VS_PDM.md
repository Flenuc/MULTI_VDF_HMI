# SAJ PDM-30 vs PDH-30 — diferencias para VarioField

Resumen operativo para Edge + app. Manuales completos: `docs/PDM30_User_Manual.*`, `docs/PDH30_User_Manual.*`.

## Perfiles

| | **PDM-30** | **PDH-30** |
|--|------------|------------|
| Drive profile | `saj.pdm30` (default NVS) | `saj.pdh30` |
| CLI | `profile set saj.pdm30` | `profile set saj.pdh30` |
| Catálogo | `drive_profiles/saj/pdm30/` | `drive_profiles/saj/pdh30/` |
| Persistencia | NVS `drv/profile` (firmware ≥ 0.3.7) | igual |

Tras `profile set`, el Edge **guarda en NVS** y mantiene el modelo al reiniciar. La app también envía `profile set` al conectar.

## Mapa de parámetros

| | **PDM-30** | **PDH-30** |
|--|------------|------------|
| Esquema | `group_direct` | `f_style` |
| IDs | `P0-00` … `P1-47` | `F0.00` … `F9.xx`, `FD.*`, `FE.*`, `D0.*`, `E0.*` |
| Dirección | `(group<<8)\|index` → p.ej. P0-00 = `0x0000` | `Fn.mm` → `0xFnmm` (F0.00 = `0xF000`) |
| Dump CLI | chunks P0/P1 | catálogo `Pdh30ParamTable` / IDs |
| Lectura/escritura | `r0`/`w0`/`r1`/`w1` o `pget`/`pset` | `pget`/`pset` / `raw`/`wraw` |

## Presión (planta)

| Uso | **PDM-30** | **PDH-30** |
|-----|------------|------------|
| **Consigna (write)** | `P0-00` @ `0x0000` (0.1 bar) | `F0.00` @ `0xF000` (0.1 bar) |
| **Consigna (telemetría `pset`)** | lee `0x0000` | lee `0xF000` (FW ≥ 0.3.7) |
| **Feedback (`pfb`)** | `0x1010` | `0x1010` (D0.16) |
| Monitor D0.15 `0x100F` | **No usar** en campo PDM (valores absurdos) | “PID setting” de monitor; **no** es el write path de receta |

Write desde app/receta: siempre `pset <id> <eng>` con el ID del profile activo.

## Telemetría común (familia)

Registros especiales compartidos en la práctica de banco:

- `0x1001` frecuencia, `0x1004` corriente, `0x3000` status  
- Bus/Vout: heurística Edge sobre `0x1002`/`0x1003` (PDM de campo suele llevar bus en `0x1003`)

## Transports recomendados

| Placa | USB CLI | WiFi MQTT | BT |
|-------|---------|-----------|-----|
| Guition P4 | OK (USB-JTAG) | OK | BLE NUS |
| ESP32-DevKit + SN75176 | **CDC a veces mudo** tras flasheo | **OK** (preferido) | **BT SPP OK** |

DevKit: RS485 DE turnaround corregido en FW **0.3.6+** (`guard_ms=1`). Si USB no muestra banner, usar MQTT/BT; el enlace al VDF no depende del CDC.

## Banco / checklist rápido

```text
profile set saj.pdh30    # o saj.pdm30
profile get              # tras reboot debe persistir (≥0.3.7)
ping                     # Link OK
pget F0.00               # PDH consigna
pget P0-00               # PDM consigna
stream on                # JSON pset ≈ pget de consigna
```

## Ver también

- Roadmap: `docs/ROADMAP_MULTI_VDF.md` (fase M1)
- Spike taller: `docs/SPIKE_PDH30_TALLER.md`
- Profiles: `drive_profiles/README.md`
