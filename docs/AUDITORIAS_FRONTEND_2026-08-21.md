# Auditorías frontend — resumen y plan (21 ago 2026)

**Fuentes (repo local, sin commit obligatorio):**

| Archivo | Enfoque |
|---------|---------|
| `Auritorias recibidas/Auditoria_front.md` | a11y/UX corto (WCAG AA, 7 hallazgos) |
| `Auritorias recibidas/AUDITORIA_UX_ACCESIBILIDAD_FRONTEND_VARIOFIELD.md` | UX industrial amplio (seguridad de acciones, tablas, Alert.alert, App.tsx) |
| `Auritorias recibidas/AUDITORIA_UX_ACCESIBILIDAD_VarioField.md` | a11y cuantitativa + contraste WCAG + roturas nativo iOS/Android |

**Producto auditado:** `desktop_app/frontend` (RN/Expo/Web/Electron) — VarioField ≥0.3.7  
**Conclusión común:** no rehacer la app; **sprint de consolidación UX/a11y** antes de más modelos VDF.

---

## 1. Qué conservar

- Camino feliz Inicio (4 pasos) y `StepCard`
- Lenguaje de campo en `i18n/es.ts`
- Catálogo accionable `lib/errors.ts` + `ErrorBanner` (modelo a11y)
- Roles operario/técnico + PIN
- Tokens `touchMin = 48` y botones principales grandes
- Confirmación de sync (overlay propio, no Modal RN)

---

## 2. Hallazgos priorizados (consolidado)

### P0 — Seguridad / prevención de errores

| ID | Hallazgo | Evidencia típica |
|----|----------|------------------|
| **P0-01** | `Marcha` / `Paro` mezclados con chips de diagnóstico | Acciones rápidas = mismo peso visual que Wi‑Fi |
| **P0-02** | Diálogo de envío: «Enviar sin comparar» demasiado destacado | Jerarquía visual vs. recomendación de comparar primero |
| **P0-03** | Overlay sync sin aislamiento total de fondo | A11Y-04 / foco lector al `ScrollView` detrás |

### P1 — Accesibilidad core

| ID | Hallazgo |
|----|----------|
| **P1-01** | Pocos `accessibilityLabel` / `accessibilityRole` vs. decenas de `Pressable` |
| **P1-02** | `TextInput` sin label asociado (dependen de texto visual suelto) |
| **P1-03** | Estados dinámicos (`statusLine`, telemetría) sin `accessibilityLiveRegion` consistente |
| **P1-04** | Títulos de sección sin `accessibilityRole="header"` |
| **P1-05** | Listas seleccionables (USB / BT / Edges MQTT) sin role/state selected |

### P2 — Contraste, ergonomía, teclado

| ID | Hallazgo |
|----|----------|
| **P2-01** | `colors.textDim` (~3.1–3.9:1) bajo WCAG AA en telemetría y notas |
| **P2-02** | Hex sueltos (`#6b7280`, etc.) en vez de tokens |
| **P2-03** | `CatalogEditor`: filas 36px, chips map 22×22, estilos ad hoc |
| **P2-04** | Foco teclado Web/Electron poco visible (`borderFocus` definido pero casi no usado) |
| **P2-05** | `hitSlop` / targets en `?` y links secundarios |
| **P2-06** | Mismatch de receta solo por color de fondo (falta símbolo/texto ≠) |
| **P2-07** | `html lang="en"` en export web (contenido 100 % ES) |

### P3 — Plataforma / mantenibilidad

| ID | Hallazgo |
|----|----------|
| **P3-01** | `localStorage` / `document` → rotos en iOS/Android nativo (si se promete en `app.json`) |
| **P3-02** | ~30–39 `Alert.alert` multi-botón frágiles en Web; falta `ConfirmDialog` reutilizable |
| **P3-03** | Errores en inglés que saltan el catálogo (`params.ts` validate) |
| **P3-04** | `App.tsx` ~3500 líneas — riesgo de regresiones a11y |
| **P3-05** | Gesto largo en `?` para técnico poco descubrible / malo con lectores |

---

## 3. Plan de sprints propuesto

### Sprint A — Seguridad UX (1–2 días)

1. Bloque **Control del variador** separado (Marcha/Paro con confirmación o estilo danger/secondary distinto).
2. En overlay sync: primario = **Comparar primero**; secundario = Enviar sin comparar.
3. `importantForAccessibility="no-hide-descendants"` / `aria-hidden` en contenido detrás del overlay sync.
4. Indicador textual en filas mismatch (`≠` / «Diferente»).

**Criterio de salida:** no se puede lanzar marcha con un toque accidental junto a “Estado Wi‑Fi”; sync prioriza el camino seguro.

### Sprint B — a11y core (2–3 días)

1. `accessibilityRole="header"` en secciones.
2. `accessibilityLabel` (+ hint) en todos los `TextInput`.
3. Labels/roles/state en listas USB, BT, Edges MQTT y `Switch`.
4. `accessibilityLiveRegion` en `statusLine` (polite) y errores (assertive donde aplique).
5. Extender patrón `Chip` / fila de params al resto de `Pressable` críticos.

**Criterio de salida:** conteo razonable label/role; smoke con NVDA o TalkBack en 1 flujo Conectar→Receta.

### Sprint C — Tokens / contraste / CatalogEditor (1–2 días)

1. Subir `textDim` a ≥4.5:1 o sustituir usos informativos por `textMuted`.
2. Eliminar hex sueltos en `CatalogEditor` → tokens; filas/chips ≥44–48 px.
3. Estilo `focused` con `colors.borderFocus` en Chip/botones.
4. `hitSlop` en `?` y links pequeños.
5. `app.json` / export: `lang: "es"`.

**Criterio de salida:** contraste AA en textos de telemetría/notas; CatalogEditor alineado al design system.

### Sprint D — Plataforma y deuda (cuando toque)

1. Decidir: **solo Web+Electron** (quitar ios/android de `app.json`) **o** capa AsyncStorage + document picker.
2. `ConfirmDialog` reutilizable; migrar Alert multi-botón críticos.
3. Traducir/mapear errores de `validateParam` al catálogo.
4. Pista visible o retirar long-press de `?`.
5. (Opcional) partir `App.tsx` en pantallas.

---

## 4. Orden recomendado vs. roadmap multi-VDF

| Prioridad | Trabajo |
|-----------|---------|
| **Ahora** | Sprint A (+ B si hay tiempo) — reduce riesgo en campo con 0.3.7 |
| **Luego** | Sprint C (CatalogEditor recién nacido) |
| **Paralelo / después** | M3 PD-20 (producto) |
| **Aplazable** | Sprint D nativo iOS/Android si el target real sigue siendo AppImage/NSIS |

---

## 5. Verificación

- Manual: teclado Tab en Electron, NVDA/TalkBack en flujo Inicio→Conectar→Receta.
- Contraste: recalcular pares tras cambiar `textDim`.
- Guantes / tablet: targets ≥48 en control VFD y catálogo.
- No sustituye prueba con operarios reales (recomendada post Sprint A–B).

---

## 6. Estado

- [x] Auditorías leídas y consolidadas (2026-08-21)
- [x] Sprint A implementado (2026-08-21)
  - Marcha/Paro fuera de «Acciones rápidas»; bloque Control con confirmación de marcha
  - Sync: primario = Comparar primero; secundario = Enviar sin comparar
  - Overlay sync: contenido detrás con `importantForAccessibility` / `aria-hidden`
  - Filas mismatch: badge textual `≠ Diferente`
- [x] Sprint B implementado (2026-08-21)
  - `accessibilityRole="header"` en secciones
  - `accessibilityLabel` (+ hints) en TextInput / Switch / Chip
  - Listas USB / BT / Edges MQTT con role + selected
  - `accessibilityLiveRegion` en statusLine, progreso y ErrorBanner (assertive)
- [ ] Sprint C implementado
- [ ] Decisión P3-01 documentada en README / app.json
