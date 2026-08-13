# MULTI_VDF_HMI — Frontend (React Native / Expo)

UI multiplataforma. **No** habla con el puerto serie ni BlueZ directamente:
todo pasa por el backend Python en `../backend` (`http://127.0.0.1:8765`).

## Requisitos

1. Backend corriendo: `cd .. && ./run_backend.sh`
2. Node 18+ / npm

## Comandos

```bash
npm install
npx expo install react-dom react-native-web @expo/metro-runtime   # solo primera vez (web)
npm run web      # escritorio en navegador
npm start        # Expo Go / emuladores
```

Variable opcional:

```bash
export EXPO_PUBLIC_API_URL=http://127.0.0.1:8765
```

## Estructura

- `App.tsx` — UI completa (paridad CustomTkinter):
  - **Conexión:** MQTT / USB / BLE / BT SPP / Simulado, telemetría, CLI
  - **Parámetros:** listas JSON, editor, Sync → VDF, Comparar (dump)
  - **Edge / Perfiles:** Wi‑Fi y MQTT al Edge, perfiles en PC
- `src/api/client.ts` — REST + WebSocket
- `src/lib/params.ts` — modelos de parámetros + parse dump

Ver `../ARCHITECTURE.md` para el diseño completo.
