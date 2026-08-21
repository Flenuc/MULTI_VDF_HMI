# VarioField 0.3.11

## Sprint D — ConfirmDialog, plataforma, modularización

### Confirmaciones
- Nuevo `ConfirmDialog` (overlay Electron/Web-safe)
- Marcha del variador y acciones del Catálogo (descartar / aplicar variante) usan ConfirmDialog en lugar de `Alert.alert` multi-botón

### Plataforma
- **Oficial:** Electron + Expo Web
- **iOS/Android** en `app.json`: experimentales / no listos (prefs y archivos JSON dependen de APIs web) — documentado en `desktop_app/README.md`

### Código
- `Chip` / `Badge` / `StepCard` → `components/primitives.tsx`
- Errores de validación de parámetros en español operativo
- Pista visible de acceso técnico (Más → PIN; atajo «?»)

Incluye Sprints A–C (seguridad UX, a11y labels, contraste/foco).

## Binarios
- `VarioField-0.3.11-arm64.AppImage`
- `VarioField-0.3.11-x86_64.AppImage`
- `VarioField-Setup-0.3.11.exe`
