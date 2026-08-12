# MULTI_VDF_HMI — Arquitectura UI multiplataforma

## Objetivo

Separar **frontend** (React Native / Expo) del **backend** de campo (Python),
reutilizando `comms/` (USB, MQTT, BT Classic SPP, BLE NUS).

- **Hoy:** desktop Linux/Windows (Expo web o CTk legacy).
- **Mañana:** misma app RN en móvil/web; el backend Python sigue en el host
  de campo (PC, Pi) o se empaqueta junto a la UI.

## Capas

```
┌─────────────────────────────────────────────┐
│  frontend/   React Native (Expo)            │
│  · Conexión, telemetría, CLI                │
│  · HTTP + WebSocket → localhost:8765        │
└──────────────────┬──────────────────────────┘
                   │ REST + WS
┌──────────────────▼──────────────────────────┐
│  backend/    FastAPI (Python)               │
│  · /connect /command /ports /bt/* /ws/events│
│  · SessionManager → comms/*                 │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│  comms/  Serial · MQTT · BT SPP · BLE NUS   │
│  firmware Edge (ESP32 / Guition)            │
└─────────────────────────────────────────────┘
```

La GUI **CustomTkinter** (`gui/app.py`) sigue disponible en transición;
no usa el backend HTTP (habla a `comms` en-proceso).

## API local (resumen)

| Método | Ruta | Uso |
|--------|------|-----|
| GET | `/health` | Backend vivo |
| GET | `/status` | Estado de enlace |
| GET | `/ports` | Puertos serie |
| GET | `/bt/classic?scan_seconds=` | Inquiry SPP |
| GET | `/bt/ble?scan_seconds=` | Scan NUS |
| POST | `/connect` | body JSON transporte |
| POST | `/disconnect` | |
| POST | `/command` | `{ "line": "ping" }` |
| WS | `/ws/events` | `line` / `json` / `status` / `error` |

CORS abierto para desarrollo local (Expo web / Metro).

## Desarrollo

```bash
# Terminal 1 — backend
cd desktop_app
./run_backend.sh

# Terminal 2 — UI
cd desktop_app/frontend
npm install
npm run web          # desktop navegador
# npm start          # Expo Go / emuladores
```

Variables opcionales:

- `EXPO_PUBLIC_API_URL=http://127.0.0.1:8765` (default)

## Escalado futuro

1. **Empaquetado desktop:** Electron/Tauri cargando el build web + proceso
   Python embebido o servicio de sistema.
2. **Móvil:** Expo iOS/Android; API en la Pi/PC de campo (misma red) o
   túnel; BLE/USB nativos solo si se portan al cliente (fase 2).
3. **Flasher:** puede quedar en Python/NSIS o exponerse como endpoints
   adicionales del backend.

## Mapa de carpetas

```
desktop_app/
  backend/           # FastAPI
  frontend/          # Expo RN
  comms/             # transportes (compartidos)
  gui/               # CTk legacy
  models.py profiles.py storage.py
  run_backend.sh
  main.py            # entry CTk
```
