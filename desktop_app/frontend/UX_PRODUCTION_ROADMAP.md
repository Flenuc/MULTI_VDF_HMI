# MULTI_VDF_HMI — Roadmap UX/UI producción

**Audiencia:** operarios de campo con experiencia técnica mínima  
**Objetivo:** menos capacitación, menos errores, cero ruido de desarrollo  
**Base actual:** Expo RN + backend Python (paridad funcional CTk)

---

## 1. Auditoría del frontend actual (hallazgos)

### 1.1 Cosas de desarrollo que el operario **no** debería ver

| Elemento actual | Problema | Destino en producción |
|-----------------|----------|------------------------|
| URL `http://127.0.0.1:8765` en cabecera | Técnico / confuso | Oculto; solo en “Acerca de / Diagnóstico” |
| Badges `API` / `WS open\|close` | Jerga backend | Un solo indicador: **Conectado / Sin enlace / Error** |
| Log crudo (`→ stream on`, `ERR:`, CSV dump) | Ruido de consola | Log “operario” filtrado + log técnico oculto |
| Comandos CLI libres (`help`, `mqtt status`…) | Exige memorar CLI firmware | Acciones con nombre de oficio + CLI solo en modo avanzado |
| Etiquetas `BLE NUS`, `BT SPP`, `param_lists/` | Acrónimos de ingeniería | Lenguaje de campo: “Bluetooth cableado”, “Listas del equipo” |
| Modo **Simulado** siempre visible | Puede confundir en planta | Solo si `EXPO_PUBLIC_DEV_TOOLS=1` o menú avanzado |
| Footer `Paridad CTk · web · listas en backend/…` | Meta-desarrollo | Quitar; versionado en “Acerca de” |
| Mensajes `OK connected via dummy`, `WS backend OK` | Internos | Traducir a español operativo o silenciar |
| Cuatro botones de guardar (servidor / export / …) | Sobrecarga cognitiva | Un flujo: **Abrir / Guardar / Guardar como** |

### 1.2 Problemas de UX / accesibilidad (funcional)

| Área | Hoy | Riesgo |
|------|-----|--------|
| Jerarquía de tareas | 3 pestañas planas, muchas chips | El operario no sabe “por dónde empezar” |
| Conexión | Debe elegir transporte + parámetros técnicos | Error de modo (MQTT vs USB vs BT) |
| Parámetros | Tabla densa, IDs `P0-03` | Difícil de escanear; sin búsqueda |
| Sync / Comparar | Confirmaciones mínimas, jerga VDF | Miedo a escribir mal el variador |
| Errores | `Alert` genéricos + log | No dicen “qué hacer después” |
| Touch / tamaño | Chips y filas pequeñas en tablet | Fallos de toque en guantes |
| Contraste / foco | Aceptable dark, sin foco teclado claro | Accesibilidad web limitada |
| Onboarding | Ninguno | Capacitación verbal larga |
| Branding | Icono default Electron / Expo | Poca confianza “producto propio” |

### 1.3 Lo que **sí** está bien (conservar)

- Separación UI ↔ backend (escalable).
- Telemetría en vivo (freq, Vbus, presión).
- Flujos críticos: conectar, sync, compare, perfiles Wi‑Fi/MQTT al Edge.
- Import/export JSON (base correcta para escritorio).
- Soporte multi-transporte (USB / MQTT / BT).

---

## 2. Principios de diseño para producción

1. **Lenguaje de oficio, no de firmware**  
   “Comprobar variador”, no `ping`. “Enviar receta al VDF”, no `Sync w0/w1`.
2. **Un camino feliz por defecto**  
   Asistente: Conectar → Elegir receta → Comprobar → Enviar.
3. **Progresive disclosure**  
   Básico visible; avanzado (CLI, baud, MAC, simulado) bajo “Más opciones”.
4. **Estados inequívocos**  
   Colores + icono + texto corto: listo / trabajando / error / desconectado.
5. **Errores accionables**  
   “No hay USB. Revisa el cable y pulsa Actualizar puertos.”
6. **Seguridad de campo**  
   Confirmación fuerte antes de Sync; nunca envío accidental de lista vacía.
7. **Capacitación ≤ 15 min**  
   Tutorial in-app de 5 pasos + tooltips en primera sesión.

---

## 3. Roadmap por fases

### Fase 0 — “Modo producción” (1–2 días)  
**Objetivo:** dejar de mostrar basura de desarrollo.

- [ ] Flag `production` / `__DEV__` / `EXPO_PUBLIC_ENV=production`
- [ ] Ocultar URL API, badges WS/API, footer técnico
- [ ] Indicador único de estado de app + enlace al equipo
- [ ] Ocultar modo Simulado y CLI libre en producción
- [ ] Traducir/filtrar mensajes de log (capa “usuario” vs “técnico”)
- [ ] Textos UI en español operativo (glosario, ver §5)
- [ ] Rebuild AppImage / export web con `ENV=production`

**Criterio de salida:** un operario no ve “8765”, “WS”, “param_lists” ni “BLE NUS” sin buscar.

---

### Fase 1 — Flujo de trabajo guiado (3–5 días)  
**Objetivo:** camino feliz sin capacitación larga.

```
[ Inicio ]
    → 1. Conectar equipo (asistente)
    → 2. Elegir / abrir receta (lista)
    → 3. Ver telemetría (¿variador vivo?)
    → 4. Comparar con VDF
    → 5. Enviar receta (sync) con confirmación
```

- [ ] Pantalla **Inicio** con 3–4 tarjetas grandes (no pestañas técnicas)
- [ ] Asistente de conexión:
  - “Por cable USB” / “Por red (Wi‑Fi)” / “Por Bluetooth”
  - Auto-detectar puerto si solo hay uno
  - BT: escanear y preferir `SAJ-PDM30-Edge` sin pedir MAC a mano
- [ ] Tras conectar: **Comprobar enlace** (ping amigable → “Variador responde / no responde”)
- [ ] Telemetría siempre visible en cabecera compacta (no solo en pestaña)
- [ ] Confirmación Sync: resumen “se enviarán N parámetros; M manuales omitidos”

**Criterio de salida:** tarea típica (conectar + comparar + sync) en &lt; 2 min sin CLI.

---

### Fase 2 — UX visual y accesibilidad (3–4 días)

- [ ] Design system mínimo: tokens color, radio, spacing, tipografía
- [ ] Botones primarios ≥ 44×44 pt; contraste WCAG AA en dark
- [ ] Iconos + color (no solo color) en estados
- [ ] Feedback háptico/sonoro opcional en éxito/error (desktop: toast)
- [ ] Tabla de parámetros:
  - Búsqueda / filtro
  - Nombre legible si hay notas (no solo `P0-00`)
  - Chips “OK / Diferente / Manual / Sin lectura”
- [ ] Reducir botones de archivo a: **Abrir · Guardar · Guardar como**
- [ ] Icono y splash de producto (Electron + Expo)
- [ ] Tema claro opcional (cabina con mucha luz)

**Criterio de salida:** checklist accesibilidad básica (contraste, tamaño toque, textos).

---

### Fase 3 — Tutorial y ayuda contextual (2–3 días)

- [ ] **Primera ejecución:** wizard 5 pantallas (saltar + “no mostrar de nuevo”)
  1. Qué es la app  
  2. Cómo conectar  
  3. Qué es una receta  
  4. Comparar vs enviar  
  5. Seguridad (no desconectar a mitad de sync)
- [ ] Botón **?** en cada sección (sheet con 2–3 frases)
- [ ] Glosario in-app (VDF, receta, consigna, enlace…)
- [ ] Pantalla **Acerca de**: versión app, versión backend, “Diagnóstico” (oculta dev tools)
- [ ] (Opcional) PDF/vídeo corto de 3 min embebido o link

**Criterio de salida:** operario nuevo completa tarea demo sin instructor.

---

### Fase 4 — Robustez y mensajes de error (2–3 días)

| Situación | Mensaje tipo producción |
|-----------|-------------------------|
| Backend caído | “No se pudo iniciar el servicio local. Reinicia la aplicación.” |
| Sin puerto USB | “No hay cable detectado. Conecta el convertidor y pulsa Actualizar.” |
| BT no encontrado | “No se ve el equipo. Acércalo, enciéndelo y pulsa Buscar otra vez.” |
| MQTT sin broker | “No hay red con el broker. Revisa Wi‑Fi del PC o el perfil.” |
| Ping sin VDF | “Equipo en línea, pero el variador no responde. Revisa RS485.” |
| Sync a medias | “Envío interrumpido en el parámetro X. No desconectes; reintenta.” |

- [ ] Catálogo de errores con código interno + texto humano
- [ ] Reintentos con un botón “Reintentar”
- [ ] Bloquear Sync si no hay enlace o si compare mostró fallos graves (configurable)

---

### Fase 5 — Roles y simplificación de perfiles (2 días)

- [ ] **Operario:** no edita perfiles MQTT/Wi‑Fi a menos que se habilite
- [ ] **Técnico / Admin:** pin o menú largo para perfiles Edge, CLI, simulado
- [ ] Plantillas de perfil por planta (importar JSON de perfiles)
- [ ] Valores por defecto sensatos (MQTT perfil único preconfigurado en instalación)

---

### Fase 6 — Empaque y release producción (2–3 días)

- [x] Build AppImage con `EXPO_PUBLIC_ENV=production`
- [x] Versión semántica **0.3.2** / **0.3.3** (app Electron + brand + backend health)
- [x] Checklist QA de campo en `RELEASE_NOTES_0.3.3.md`
- [x] Release notes operario + tag GitHub **v0.3.2** / **v0.3.3**
- [x] Artifact: `VarioField-*-arm64.AppImage`
- [x] NSIS Windows (Electron nativo desde Linux + Python embed)
- [x] BT Classic SPP estable Windows/Linux (0.3.3)
- [x] Asistente Mosquitto (scripts + API + botón UI) (0.3.3)
- [ ] Sin consola del backend en Windows (opcional log a archivo)
- [ ] (Opcional) Telemetría de uso anónima off-by-default

---

## 4. Propuesta de información arquitectura UI (producción)

```
┌─────────────────────────────────────────────┐
│  Cabecera: logo · estado enlace · telemetría│
│  [Ayuda] [Acerca de]                        │
├─────────────────────────────────────────────┤
│  Inicio (camino feliz)                      │
│   ① Conectar  ② Receta  ③ Comprobar  ④ Enviar│
├─────────────────────────────────────────────┤
│  Secciones (drawer o tabs amables):         │
│   · Equipo      (conexión)                  │
│   · Recetas     (parámetros + import/export)│
│   · Ajustes     (perfiles, solo si admin)   │
├─────────────────────────────────────────────┤
│  Panel inferior colapsable: “Actividad”     │
│  (mensajes filtrados, no consola raw)       │
└─────────────────────────────────────────────┘
```

Modo **Avanzado / Diagnóstico** (oculto): CLI, log raw, URL API, simulado, WS.

---

## 5. Glosario UI (español operativo)

| Antes (dev) | Producción |
|-------------|------------|
| MQTT | Red / Wi‑Fi |
| USB (Serial) | Cable USB |
| Bluetooth (SPP) | Bluetooth |
| BLE NUS | Bluetooth (placa táctil) — o unificar “Bluetooth” con subtipo |
| Simulado | (oculto) Prueba sin equipo |
| Sync → VDF | Enviar receta al variador |
| Comparar | Comprobar diferencias con el variador |
| stream on/off | Lectura en vivo (automática) |
| ping | Comprobar variador |
| Edge | Equipo de campo / módulo |
| param_lists | Recetas guardadas |
| P0-00 | Consigna de presión (si hay mapa de nombres) |

**Mejora fuerte (Fase 2+):** mapa `P0-xx → nombre de manual` desde JSON de escala/notas.

---

## 6. Métricas de éxito

| Métrica | Objetivo |
|---------|----------|
| Tiempo hasta primer “variador OK” | &lt; 3 min (nuevo usuario con tutorial) |
| Errores de modo de conexión / 10 usos | ≤ 1 |
| Sync accidental cancelado o a medias | Documentado + recoverable |
| Preguntas a soporte “¿qué es MQTT?” | → 0 (lenguaje renombrado) |
| Uso de CLI en producción | &lt; 5 % de sesiones (solo técnicos) |

---

## 7. Orden de implementación recomendado

| Prioridad | Fase | Esfuerzo | Impacto |
|-----------|------|----------|---------|
| P0 | Fase 0 — limpiar dev UI | Bajo | Alto (imagen producto) |
| P0 | Fase 1 — camino feliz | Medio | Muy alto (capacitación) |
| P1 | Fase 3 — tutorial | Medio | Muy alto |
| P1 | Fase 4 — errores | Medio | Alto |
| P2 | Fase 2 — estética / a11y | Medio | Alto |
| P2 | Fase 5 — roles | Bajo-medio | Medio |
| P3 | Fase 6 — release polish | Medio | Necesario salida |

**Secuencia sugerida de sprints (aprox. 2–3 semanas efectivas):**

1. **Sprint A:** Fase 0 + esqueleto Inicio (Fase 1 parcial)  
2. **Sprint B:** Asistente conexión + comparar/enviar amigables  
3. **Sprint C:** Tutorial + catálogo de errores  
4. **Sprint D:** Design system + iconos + rebuild packs  

---

## 8. Fuera de alcance (por ahora)

- Rediseño del firmware CLI.
- Multi-usuario en la nube.
- Traducción multi-idioma (preparar i18n keys desde Fase 0 ayuda).
- App móvil store (el roadmap UI aplica igual cuando se empaquete Expo).

---

## 9. Decisiones de producto (cerradas)

| # | Tema | Decisión |
|---|------|----------|
| 1 | Perfiles Wi‑Fi/MQTT | El **operario puede editarlos**, con instrucciones claras en la UI. |
| 2 | Enviar sin comparar | **Permitido**, con confirmación suave y **recomendación** de comparar. |
| 3 | Nombre comercial | **VarioField** — multi-marca, no atado a una empresa; escalable a otros variadores. |
| 4 | Tutorial | **Se puede saltar**; en Ayuda: **“Ver tutorial otra vez”**. |

### Marca
- **VarioField** — *Recetas y enlace a variadores en campo*
- Código interno / repo: `MULTI_VDF_HMI` (solo diagnóstico)

### Implementación (v0.3)
- UI producción por defecto (sin URL API / WS / CLI a la vista).
- Tutorial 5 pasos + saltar + repetir.
- Sync con diálogo: Comparar primero | Enviar sin comparar | Cancelar.
- Pestaña Ayuda + Diagnóstico opcional (herramientas técnicas).

---

*Documento vivo: actualizar al cerrar cada fase.*
