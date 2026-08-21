# VarioField — APK Android (experimental / smoke)

**Objetivo:** comprobar que la UI Expo arranca en Android.  
**No incluye** el backend Python (eso vive en Electron). Sin `EXPO_PUBLIC_API_URL`, el APK apunta a `10.0.2.2:8765` (emulador → PC host).

## Requisitos

1. Cuenta [Expo](https://expo.dev)
2. Desde `desktop_app/frontend`:

```bash
cd desktop_app/frontend
npm install
npx eas-cli login
npx eas-cli init          # crea/enlaza proyecto (escribe projectId en app.json)
npm run build:apk        # eas build -p android --profile preview → .apk
```

3. Cuando termine, EAS da una URL de descarga del APK.

## Build local (PC x86_64 con Android Studio)

```bash
cd desktop_app/frontend
npx expo prebuild --platform android --clean
cd android && ./gradlew assembleRelease
# → android/app/build/outputs/apk/release/app-release.apk
```

En **Raspberry Pi arm64** el SDK oficial de Android no está soportado de forma fiable; preferí EAS cloud.

## Limitaciones del smoke APK

| Función | Estado |
|---------|--------|
| Arranque UI / tutorial / tabs | OK (prefs en memoria) |
| Import/export JSON archivos | No (falta document picker nativo) |
| Backend / MQTT / USB | Solo si el teléfono alcanza el backend en LAN (`EXPO_PUBLIC_API_URL`) |

## Notas de código

- `src/lib/storage.ts` — localStorage en web, memoria en nativo
- `eas.json` — profile `preview` genera **APK** (no AAB)
