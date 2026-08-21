# Screens / modularización (Sprint D+)

`App.tsx` sigue siendo el orquestador (~3500 líneas). Extracciones hechas:

| Módulo | Contenido |
|--------|-----------|
| `components/primitives.tsx` | `Badge`, `Chip`, `StepCard` |
| `components/ConfirmDialog.tsx` | Overlay confirm multi-botón (Electron/Web) |
| `components/CatalogEditor.tsx` | Catálogo técnico |
| `components/ErrorBanner.tsx` | Errores de campo |

**Siguiente** (cuando toque): `HomeTab`, `ConnectTab`, `ParamsTab`, `MoreTab` como componentes con props explícitas, sin mover lógica de sesión todavía.
