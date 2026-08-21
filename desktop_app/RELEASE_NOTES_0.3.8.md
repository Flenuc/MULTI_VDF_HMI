# VarioField 0.3.8

## Sprint A — Seguridad UX / a11y (auditorías frontend)

### Control del variador
- **Marcha** y **Paro** salen de «Acciones rápidas» (diagnóstico).
- Bloque aparte **Control del variador** con botones grandes (aviso / peligro).
- **Marcha** pide confirmación antes de enviar `start`.

### Envío de receta
- En el diálogo de sync, el botón **primario** es **Comparar primero (recomendado)**.
- «Enviar sin comparar» queda como acción secundaria.
- El contenido detrás del overlay se oculta a lectores de pantalla (`importantForAccessibility` / `aria-hidden`).

### Recetas
- Filas con diferencia vs. variador muestran **≠ Diferente** (no solo color de fondo).

## Binarios
- `VarioField-0.3.8-arm64.AppImage`
- `VarioField-0.3.8-x86_64.AppImage`
- `VarioField-Setup-0.3.8.exe`
