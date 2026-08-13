# Roadmap multi-VDF — VarioField / MULTI_VDF_HMI

**Fecha:** 2026-08-13  
**Estado base:** VarioField **0.3.3** operativo (app desktop + Edge ESP32 + SAJ **PDM-30** en campo)  
**Objetivo:** escalar de un stack *dedicado PDM-30* a una plataforma **multi-variador** con la misma lógica de receta → comparar → modificar, y una herramienta para **extraer / catalogar parámetros** de cada modelo.

---

## 1. Contexto: qué ya tenemos (y no hay que romper)

### 1.1 Cadena de valor actual (genérica en transporte)

```
Operario (VarioField)
  → backend local :8765
    → USB | MQTT | BT SPP | BLE NUS
      → Edge ESP32 (CLI de líneas)
        → Modbus RTU master (RS485)
          → VDF
```

Esto **ya es reutilizable**: perfiles de conexión, sesión única, sync/compare por receta JSON, packs Windows/Linux, roles operario/técnico.

### 1.2 Qué está “quemado” a SAJ PDM-30

| Capa | Hardcode PDM-30 |
|------|-----------------|
| Identidad de parámetros | Solo grupos **P0/P1**, índices **0..47** (`models.py`) |
| CLI Edge | `r0/w0/r1/w1`, `dump` CSV `P0-xx` |
| Escalas eng↔raw | `ScaleTable` fija PDM-30 |
| Mapa Modbus | `(group<<8)\|index` en Edge (`MAP_GROUP_DIRECT`) |
| Telemetría / marcha | Registros estilo familia PDH (`0x100x`, `0x2000`, `0x3000`) |
| MQTT / nombre BT | `saj/pdm30/…`, `SAJ-PDM30-Edge` |
| Listas de planta | `param_lists/*pdm30*`, `MAX PRESS 30VF.json` |

### 1.3 Activo ya útil para multi-modelo

- Manuales en repo: `docs/PDM30_User_Manual.*`, `docs/PDH30_User_Manual.*`
- Esquemas de mapa candidatos en `include/saj_pdm30_protocol.h` (`MAP_F_STYLE`, etc.)
- Descubrimiento de mapa de campo: `results/param_map.csv` + scripts de discovery
- UI ya de marca multi-fabricante (**VarioField**)

**Conclusión:** no rehacer la app de campo; **introducir un “Drive Profile”** (catálogo + adaptador) y un **pipeline de extracción** de parámetros desde manuales/dumps.

---

## 2. Principios de diseño multi-VDF

1. **Una receta de planta = lista de consignas en unidades de ingeniería**  
   El operario no ve registros Modbus crudos salvo en modo técnico.
2. **El modelo del variador es un plugin de datos + driver**  
   No un fork de la app.
3. **Misma UX de campo**  
   Conectar → receta → comprobar → enviar, independiente del fabricante.
4. **Edge como traductor**  
   El PC sigue hablando CLI (o API neutra); el Edge conoce el *profile* activo.
5. **Extracción antes que UI perfecta**  
   Sin catálogo verificado no hay compare/sync fiable.
6. **Un Edge ↔ un VDF por sesión** (v1)  
   Multi-slave en el mismo bus = fase posterior.

---

## 3. Arquitectura objetivo

### 3.1 Drive Profile (catálogo JSON versionado)

```json
{
  "id": "saj.pdh30",
  "vendor": "SAJ",
  "family": "PDH",
  "model": "PDH-30",
  "version": "1.0.0",
  "protocol": {
    "link": "modbus_rtu",
    "baud": 9600,
    "parity": "N",
    "stop": 1,
    "slave_default": 1,
    "fc_read": 3,
    "fc_write": 6,
    "max_contiguous": 12
  },
  "addressing": {
    "scheme": "f_style",
    "param_id_format": "F{group}.{index:02d}"
  },
  "parameters": [
    {
      "id": "F0.00",
      "group": 0,
      "index": 0,
      "register": "0xF000",
      "name": "…",
      "unit": "Hz",
      "scale": 0.01,
      "access": "rw",
      "min": 0,
      "max": 400,
      "default": null,
      "notes": "…"
    }
  ],
  "telemetry": [
    { "id": "run_freq", "register": "0x1001", "scale": 0.01, "unit": "Hz" }
  ],
  "commands": {
    "start_fwd": { "register": "0x2000", "value": "0x0001" },
    "stop": { "register": "0x2000", "value": "0x0006" }
  }
}
```

**Ubicación propuesta**

```
drive_profiles/
  saj/
    pdm30/
      profile.json
      scales.json          # opcional si no va embebido
      fingerprint.json     # defaults para autodetectar
    pdh30/
    pd20/
    8200b/
  danfoss/
    vlt_micro/
  bedford/
    w713ba/
```

### 3.2 Capa de adaptadores (firmware + app)

| Componente | Responsabilidad |
|------------|-----------------|
| **Profile registry** (app) | Lista de modelos, carga JSON, validación |
| **Recipe** | Sigue siendo JSON de valores; añade `drive_profile_id` |
| **Param mapper** | `id` humano ↔ register ↔ eng/raw |
| **Edge driver** | Implementación Modbus por familia (`SajPdmFamily`, `DanfossFc`, …) |
| **CLI neutra (fase 2)** | `param get/set <id>`, `profile set saj.pdh30`, `dump` |

Mientras no exista CLI neutra, se mantiene `r0/w0` **solo para perfiles tipo SAJ P0/P1**.

### 3.3 Herramienta de extracción de parámetros

Producto: **VarioField Catalog Builder** (script + UI técnica mínima)

Entradas:
- Manual PDF/TXT (como `docs/*_User_Manual.txt`)
- Dump en vivo (`dump` / lectura Modbus por rangos)
- CSV/Excel de planta

Salidas:
- `profile.json` validado
- Diff “manual vs en vivo”
- Lista plantilla vacía / con defaults de fábrica

Pipeline:

```
Manual / dump → extractores → borrador profile
       → revisión técnico (PIN)
       → prueba en banco (read/write 3–5 params)
       → publicar en drive_profiles/ + receta de planta
```

---

## 4. Prioridad de modelos (producto)

| Prioridad | Modelo | Familia | Notas |
|-----------|--------|---------|--------|
| **P0** | **SAJ PDH-30** | SAJ PDH (Modbus Ch.6 documentado) | Manual ya en `docs/`; mapa F-style probable; máxima cercanía a PDM-30 |
| **P0b** | SAJ PDM-30 | SAJ (actual) | **Mantener y formalizar** como primer `drive_profile` de referencia |
| **P1** | SAJ PD-20 | SAJ legacy | Manual + discovery; grupos/params distintos |
| **P1** | SAJ 8200B | SAJ legacy | Manual + discovery; prioridad tras PD-20 si hay demanda de campo |
| **P2** | Danfoss VLT Micro Drive | Danfoss FC | Parámetros P-xx o index FC; no reutilizar mapa SAJ |
| **P2** | Bedford W713ba | Bedford | Confirmar protocolo (Modbus vs propietario) antes de firmware |

> **PDH-30 primero** (además de formalizar PDM-30): comparte documentación de familia Modbus con lo ya implementado; el salto de producto es “elegir modelo + mapa F vs P” más que reescribir el Edge.

---

## 5. Roadmap por fases

### Fase M0 — Congelar PDM-30 como perfil de referencia (3–5 días)

**Objetivo:** el sistema actual se expresa como el primer Drive Profile, sin cambiar la UX del operario.

- [x] Extraer de `ScaleTable` + `saj_pdm30_protocol.h` → `drive_profiles/saj/pdm30/profile.json`
- [x] Añadir `drive_profile_id: "saj.pdm30"` a recetas (default si falta) + `models.ParameterList`
- [x] Loader `drive_profiles/` + README
- [x] Spike tool RS485: `tools/spike_pdh30_map.py` (raw CLI / schemes)
- [ ] App: selector de modelo (solo PDM-30 visible en operario; más en técnico)
- [ ] Edge: leer profile id por CLI `profile get` (hardcoded `saj.pdm30` al inicio)
- [ ] Tests: dump/compare/sync idénticos a 0.3.3 con profile cargado

**Criterio de salida:** con profile explícito, un banco PDM-30 se comporta igual que hoy.

**Taller (hardware disponible ahora):** PDM-30 (regresión), **PDH-30 (spike activo)**, PD-20 y Danfoss cuando haya unidad; 8200B y Bedford después.

---

### Fase M1 — SAJ PDH-30 (máxima prioridad nueva) (1–2 semanas)

**Objetivo:** primer modelo “nuevo” usable en planta para recetas y compare/write.

1. **Catalogación / spike**
   - [x] Scaffold `drive_profiles/saj/pdh30/profile.json` (F-style + telemetría Ch.6)
   - [x] Tool: `python3 tools/spike_pdh30_map.py --port /dev/ttyACM0 --label pdh30`
   - [ ] **Ejecutar spike en taller** con PDH-30 cableado; archivar `results/spike_map_pdh30_*.json`
   - [ ] Confirmar scheme ganador (esperado: `f_style`)
   - [ ] Parser del manual `docs/PDH30_User_Manual.txt` (tablas F0.xx / registros)
   - [ ] Escalas y unidades por parámetro
   - [ ] Telemetría y comandos marcha/paro validados en banco

2. **Firmware**
   - [ ] `profile set saj.pdh30` / autodetect opcional (fingerprint de defaults)
   - [ ] Driver reutilizando motor Modbus; cambiar solo address + scale tables
   - [ ] CLI: mantener `r0/w0` si PDH se presenta como grupos 0/1 **o** introducir `param get F0.00`

3. **App**
   - [ ] Selector **PDH-30** en conectar / receta
   - [ ] Recetas con IDs del perfil (mostrar nombre de manual, no solo código)
   - [ ] Compare/sync usando el mapper del perfil

4. **Campo**
   - [ ] Banco: 10 params R/W + dump completo + 1 receta de planta
   - [ ] Documentar diferencias PDH vs PDM (presión, PID, límites)

**Criterio de salida:** receta de planta en PDH-30 se compara y envía sin tocar código CTk legacy.

**Riesgo principal:** diferencias sutiles PDM↔PDH en direcciones o escalas pese a “misma familia”. Mitigación: discovery en vivo + fingerprint.

---

### Fase M2 — Herramienta de extracción (Catalog Builder) (1–2 semanas, en paralelo a M1)

**Objetivo:** industrializar la creación de perfiles para PD-20, 8200B y terceros.

- [ ] CLI `tools/catalog_builder/`:
  - `extract-manual --vendor saj --pdf/txt …`
  - `extract-live --via mqtt|serial --profile draft`
  - `merge` / `diff` / `validate`
- [ ] Formato de entrada semi-estructurado (tablas markdown/CSV intermedias)
- [ ] UI técnica (modo técnico VarioField o script notebook):
  - importar borrador, editar escala/access, exportar `profile.json`
- [ ] Suite de validación: % de params leídos OK, % escritura verificada (readback)

**Criterio de salida:** un técnico genera un borrador PDH/PD-20 en &lt; 1 día de trabajo a partir de manual + 1 hora de banco.

---

### Fase M3 — SAJ legacy: PD-20 y 8200B (2–3 semanas)

Orden sugerido: **PD-20 → 8200B** (salvo stock de campo al revés).

Por cada modelo:

1. Manuales en `docs/saj_pd20/`, `docs/saj_8200b/`
2. Extracción M2 + discovery RS485
3. Profile + driver Edge (si el mapa es “SAJ-like”, reutilizar familia; si no, driver nuevo)
4. Plantillas de receta vacías + 1 receta real de planta
5. QA: compare/sync + telemetría mínima (freq/corriente si existe)

**Criterio de salida:** dos modelos legacy en el selector técnico, al menos uno validado en instalación real.

---

### Fase M4 — Otros fabricantes: Danfoss VLT Micro + Bedford W713ba (3–5 semanas)

#### Danfoss VLT Micro Drive
- [ ] Confirmar serie exacta (FC 51 / similar) y manual de parámetros
- [ ] Protocolo: casi siempre **Modbus RTU**; índices P-xx / parámetros FC (no P0/P1 SAJ)
- [ ] Nuevo addressing scheme + nombres
- [ ] Comandos marcha/paro y status según manual (no asumir 0x2000 SAJ)
- [ ] Receta de planta piloto

#### Bedford W713ba
- [ ] **Spike de protocolo** (1–3 días): ¿Modbus RTU? ¿otro bus? baud/slave
- [ ] Solo si Modbus (o protocolo documentado): profile + driver
- [ ] Si es propietario cerrado: valorar pasarela externa o despriorizar

**Criterio de salida:** al menos **un** no-SAJ en producción piloto; Bedford solo si el spike es verde.

---

### Fase M5 — Producto multi-VDF “completo” (2–3 semanas)

- [ ] CLI Edge unificada: `profile list|set|get`, `param get|set|dump`
- [ ] App: receta ligada a modelo; impedir sync a modelo incorrecto (con override técnico)
- [ ] Autodetección suave (fingerprint) + confirmación operario
- [ ] Documentación operario por modelo (1 página)
- [ ] Release **VarioField 0.4.0** multi-VDF
- [ ] (Opcional) multi-slave: lista de direcciones en el mismo RS485

---

## 6. Orden de sprints recomendado

| Sprint | Enfoque | Entregable |
|--------|---------|------------|
| **S1** | M0 + kickoff M1 | `saj.pdm30` como profile; scaffold `saj.pdh30` |
| **S2** | M1 banco PDH-30 | R/W + dump + 1 receta PDH |
| **S3** | M2 Catalog Builder MVP | extract-manual + validate |
| **S4** | M1 cierre + M3 PD-20 start | PDH en release; draft PD-20 |
| **S5–S6** | M3 PD-20 / 8200B | 1–2 legacy en campo |
| **S7–S8** | M4 Danfoss (+ Bedford si procede) | Primer no-SAJ |
| **S9** | M5 polish 0.4.0 | Selector de modelo + docs |

Esfuerzo orientativo total: **~10–14 semanas** con 1 dev full-stack embebido+app (depende de acceso a hardware y calidad de manuales).

---

## 7. Cambios de software por capa (checklist técnico)

### App (VarioField)
- [ ] `drive_profiles/` empaquetados en Electron resources
- [ ] Modelo `DriveProfile` en TS/Python
- [ ] Receta: campo `drive_profile_id` + validación
- [ ] Compare/sync parametrizado (no asumir P0/P1 only a medio plazo)
- [ ] UI: selector de modelo; nombres de manual en lista de params
- [ ] Modo técnico: Catalog Builder / import profile

### Edge firmware
- [ ] Registry de drivers (`IVfdDriver`: read/write param, telemetry, command)
- [ ] `SajPdm30Driver` (actual) + `SajPdh30Driver` (mapa F)
- [ ] Persistencia NVS del profile activo
- [ ] MQTT topic root derivado del profile (o genérico `variofield/<edge_id>/…`)

### Tools
- [ ] `tools/catalog_builder/`
- [ ] Tests de golden files por profile
- [ ] Script de banco “smoke R/W”

---

## 8. Formato de receta de planta (evolución)

**Hoy (PDM-30):**
```json
{ "name": "MAX PRESS 30VF", "parameters": [ { "group": 0, "index": 0, "value": 26 } ] }
```

**Multi-VDF:**
```json
{
  "name": "MAX PRESS 30VF",
  "drive_profile_id": "saj.pdh30",
  "parameters": [
    { "id": "F0.00", "value": 26, "notes": "Pressure setting", "manual_only": false }
  ]
}
```

Compatibilidad: si falta `drive_profile_id` → asumir `saj.pdm30` y `group/index`.

---

## 9. Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|--------|---------|------------|
| Manual ≠ firmware real | Sync incorrecto | Discovery en vivo + readback obligatorio |
| Escalas mal extraídas | Valores x10/x100 | Tabla de escalas en profile + tests banco |
| Un solo CLI para todos | Confusión | Profile activo en Edge + rechazo de IDs ajenos |
| Bedford no-Modbus | Bloqueo P2 | Spike temprano; no bloquear SAJ |
| Alcance infinito de params | Nunca se cierra un modelo | MVP: subset “planta” (20–40 params) + resto read-only después |
| Multi-slave prematuro | Complejidad | Fuera de 0.4; un VDF por Edge |

---

## 10. Criterios de “modelo listo para planta”

Un `drive_profile` se considera **releaseable** cuando:

1. ≥ 95 % de los params de la **receta piloto** leen coherente  
2. Escritura + readback OK en esos params  
3. Compare detecta un cambio forzado a mano en el teclado del VDF  
4. Sync de receta completa sin error de bus  
5. Telemetría mínima (al menos marcha/freq o equivalente)  
6. Documentada IP/slave/baud y precauciones  
7. Probado por un operario con tutorial VarioField sin CLI  

---

## 11. Decisiones a cerrar pronto (producto)

| # | Pregunta | Recomendación |
|---|----------|----------------|
| 1 | ¿PDH-30 es el mismo bus/escalas que PDM-30 en vuestras plantas? | Validar en banco en S1; no asumir |
| 2 | ¿Un Edge solo habla un modelo a la vez? | **Sí** en 0.4 |
| 3 | ¿Operario elige modelo o se autodetecta? | Autodetect suave + confirmación |
| 4 | ¿Recetas mezclan modelos? | **No**; un profile_id por receta |
| 5 | ¿MQTT topic genérico ya en 0.4? | Ideal; si no, alias `saj/pdm30` + `variofield/...` |

---

## 12. Primeros pasos ejecutables (esta semana)

1. **Inventario hardware** en taller: 1× PDH-30, 1× PDM-30 (regresión), cables RS485, slave/baud reales.  
2. **M0:** generar `drive_profiles/saj/pdm30/profile.json` desde código actual.  
3. **Spike PDH-30 (2 días):**  
   - leer F0.00 / P0-00 equivalentes con los 2–3 esquemas de `saj_pdm30_protocol.h`  
   - documentar el esquema ganador  
4. **Borrador extractor** sobre `docs/PDH30_User_Manual.txt` (tabla de params → CSV).  
5. **No empezar Danfoss/Bedford** hasta tener PDH en banco verde.

---

## 13. Relación con roadmaps previos

| Documento | Rol |
|-----------|-----|
| `desktop_app/frontend/UX_PRODUCTION_ROADMAP.md` | UX operario (Fases 0–6) — **cerrado en gran parte en 0.3.3** |
| **Este documento** | Escalado multi-modelo / multi-fabricante |
| `CONTINUACION_ITERACION.md` | Historia técnica PDM-30 Edge |

**Siguiente release de producto sugerido:**  
- **0.3.x** = mantenimiento PDM-30 + app  
- **0.4.0** = multi-VDF con **PDM-30 + PDH-30** y Catalog Builder MVP  

---

*Documento vivo: actualizar al cerrar cada fase M0–M5 y al validar cada `drive_profile` en banco.*
