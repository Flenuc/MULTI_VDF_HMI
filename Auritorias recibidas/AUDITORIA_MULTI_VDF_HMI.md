# Auditoría técnica — MULTI_VDF_HMI

**Repositorio:** https://github.com/Flenuc/MULTI_VDF_HMI
**Fecha de auditoría:** 2026-08-18
**Contexto:** stack de campo para el variador SAJ PDM-30 — firmware ESP32 (Modbus RTU / MQTT / BLE), app de escritorio en CustomTkinter (congelada) y app React Native en desarrollo activo como cliente principal.

---

## 1. Resumen ejecutivo

El proyecto tiene una base técnica sólida en el firmware (máquina de estados sin bloqueo, sin `String` de Arduino, escalas de ingeniería separadas del valor raw) y una arquitectura de comunicación razonable (MQTT como canal principal, USB/BLE como alternativas). El riesgo más urgente **no es de diseño sino de higiene de repositorio**: hay una credencial Wi-Fi real en texto plano, commiteada en un repo público. Eso se corrige hoy, no en el próximo sprint.

El segundo tema estructural es la migración a React Native: el protocolo (CLI, topics MQTT, JSON de telemetría) hoy vive implícito en el código de `desktop_app/` y en la documentación. Si la app RN lo reimplementa por su cuenta sin una fuente única de verdad, los dos clientes van a divergir con el tiempo.

**Nivel de riesgo global: medio-alto**, dominado por el hallazgo de credenciales expuestas (crítico) y por ausencia de autenticación en los canales de control del variador (alto).

---

## 2. Metodología y alcance

Esta auditoría se hizo sobre:
- `README.md` (raíz del repo)
- `CONTINUACION_ITERACION.md` (documento de handoff, fechado 2026-08-11)
- La estructura de carpetas listada por GitHub

**No se tuvo acceso directo** al código fuente completo (`.cpp`/`.h` del firmware, `.py` de `desktop_app`, ni al repositorio/carpeta de la app React Native, que según la conversación aún no está integrada a este repo). Los hallazgos de las secciones 5 y 6 se basan en lo que el propio equipo documentó como estado y pendientes, no en revisión línea por línea. Se recomienda una segunda pasada con acceso al código fuente completo, especialmente del cliente React Native, antes de dar por cerrada esta auditoría.

---

## 3. Hallazgos de seguridad

### 3.1 🔴 CRÍTICO — Credencial Wi-Fi real en texto plano, commiteada en repo público

`CONTINUACION_ITERACION.md` incluye el SSID y la contraseña reales de la red de pruebas (`REDACTED_SSID`), usados también en el perfil `ROWA` de `connection_profiles.json`. El archivo está trackeado por git y el repo es público, así que la credencial ya circuló.

**Riesgo:** cualquiera con acceso a esa red física puede usarla. Borrar la línea del archivo *no* revierte la exposición — el string ya está en el historial de git y pudo haber sido cacheado o clonado.

**Corrección concreta:**
1. Rotar la contraseña de esa red **hoy**, independientemente de lo que se haga con el repo.
2. Purgar el string del historial completo con `git filter-repo` (o BFG Repo-Cleaner) y forzar push.
3. Revisar si esa misma contraseña se reutiliza en otras redes/servicios y rotarla ahí también.

### 3.2 🟠 ALTO — Sin autenticación obligatoria en los comandos MQTT que operan el variador

El CLI expone comandos como `start`, `stop`, `estop`, `set <pct>`, `w0/w1` sobre el topic `saj/pdm30/<id>/cmd`. Existe el comando `mqtt user <u> <p>` en el firmware, pero nada en la documentación indica que la autenticación sea obligatoria ni que el broker tenga ACL por topic. Si el broker queda abierto en la LAN (o expuesto más allá), cualquier cliente MQTT puede arrancar, parar o reconfigurar el variador.

**Corrección concreta:**
- Exigir usuario/contraseña en el broker (no dejarlo anónimo por default).
- Configurar ACL en Mosquitto para que solo clientes autorizados puedan publicar en `.../cmd`.
- Si el broker sale de la LAN local en algún momento, agregar TLS.

### 3.3 🟠 ALTO — Credenciales del AP de campo fijas e iguales en todas las unidades

El SSID `SAJ_Diag_Tool` / password `sajpdm30` está hardcodeado y es igual para cualquier unidad desplegada. Una sola filtración compromete el modo de acceso directo de toda la flota de dispositivos en campo.

**Corrección concreta:** derivar el password del AP a partir de un identificador único por dispositivo (MAC, número de serie) en vez de un valor fijo compartido, o implementar un flujo de provisioning que lo genere en el primer arranque.

### 3.4 🟡 MEDIO — Perfiles de conexión en texto plano en disco (desktop)

`connection_profiles.json` guarda credenciales Wi-Fi/MQTT sin cifrar en el filesystem local. Está correctamente en `.gitignore`, pero vale la pena:
- Confirmar con `git log --all --full-history -- desktop_app/config/connection_profiles.json` que nunca se coló un commit real antes de que se agregara al `.gitignore`.
- Documentar este riesgo como aceptado (es común en herramientas de campo locales) en vez de dejarlo implícito.

### 3.5 🟢 BAJO — Sin escaneo de secretos automatizado

No hay evidencia de gitleaks, trufflehog, ni GitHub secret scanning activado. Este control hubiera detectado el hallazgo 3.1 antes del push.

**Corrección concreta:** activar GitHub secret scanning (gratis en repos públicos) y/o agregar un hook de pre-commit con gitleaks.

---

## 4. Arquitectura y deuda técnica — la bifurcación de clientes

### 4.1 Riesgo de divergencia de protocolo entre CustomTkinter, React Native y firmware

Hoy el protocolo de aplicación (comandos CLI, topics MQTT, formato del JSON de telemetría) vive de facto en el código de `desktop_app/` y en la memoria del equipo, no en un documento versionado independiente del cliente. Con la app React Native avanzando en paralelo, el riesgo real es que cada cliente termine con su propia interpretación de "cómo se arma un comando `w0`" o "qué campos trae la telemetría", y que diverjan silenciosamente.

**Corrección concreta:** extraer el protocolo a una especificación propia, versionada junto al firmware (por ejemplo `docs/PROTOCOL.md` o un JSON Schema de los payloads MQTT), que tanto `desktop_app` como la app RN referencien en vez de reimplementar cada uno por su cuenta. Esto es más barato ahora, con dos clientes, que después con tres.

### 4.2 Canal USB Serial no está resuelto para React Native

`pyserial` en desktop resuelve USB trivialmente. En React Native, Android tiene soporte parcial (bibliotecas tipo `react-native-usb-serialport`, con limitaciones) y iOS prácticamente no permite acceso a USB serie sin certificación MFi. Si el flasheo o debug de campo depende de USB, ese flujo probablemente deba seguir viviendo en la app de escritorio o en una CLI aparte.

**Corrección concreta:** decidir y documentar explícitamente qué canales cubre cada cliente (RN = BLE + MQTT; desktop = USB + BLE + MQTT), en vez de dejarlo implícito.

### 4.3 CustomTkinter congelada sin marcarlo formalmente

El código sigue activo en el repo sin ninguna indicación de que está en modo mantenimiento. Esto puede confundir a quien se sume al proyecto.

**Corrección concreta:** agregar una nota clara en `desktop_app/README.md` y en el README raíz indicando que es la versión de referencia/debug, no el cliente principal a futuro.

### 4.4 Código WebSocket legacy sin remover

`comms/ws_client.py` sigue en el repo, marcado como deprecado pero no eliminado. Riesgo bajo pero real: alguien puede copiarlo como base para el cliente RN sin saber que fue abandonado por saturación en `dump`.

**Corrección concreta:** eliminarlo o moverlo a una carpeta `legacy/` claramente señalizada.

### 4.5 Sin tests automatizados

No hay mención de tests unitarios ni de integración en ningún lado de la documentación revisada, ni un step de test en CI (solo hay build + release del firmware).

**Corrección concreta, mínimo viable:**
- Test de `ScaleTable` (conversión raw ↔ valor de ingeniería): es el punto donde un bug se traduce directo en "el variador hace algo distinto a lo que pediste".
- Test del parser de discovery log (`parse_discovery_log.py`).
- Validación de esquema del JSON de telemetría MQTT, para que un cambio en el firmware no rompa a los clientes en silencio.

---

## 5. Firmware — hallazgos puntuales

| Hallazgo | Detalle |
|---|---|
| Buenas prácticas ya aplicadas | Sin `delay()`, sin `String` de Arduino, máquina de estados con `millis()` — mantener como estándar del proyecto. |
| DE/RE automático sin confirmar en Guition P4 | Marcado como pendiente (P4 en el handoff): si el half-duplex falla, hay que mapear EN a un GPIO real. Requiere prueba de hardware dedicada antes de dar la placa por estable. |
| Manejo de fallos Modbus no documentado | No hay mención explícita de timeouts/reintentos/CRC ante fallos de comunicación con el VFD. Confirmar que existe y documentarlo. |
| Estado seguro ante pérdida de link | Confirmar explícitamente que, si se cae MQTT o Serial en medio de una marcha, el firmware no queda en un estado de "sigue corriendo indefinidamente" sin forma de pararlo. Si no hay un fail-safe definido, es el hallazgo de mayor impacto de esta sección. |

---

## 6. App de escritorio (CustomTkinter) — hallazgos puntuales

- Builds viejos de PyInstaller pueden no incluir MQTT/perfiles (P8 del handoff). Si se va a congelar esta app, conviene fijar y etiquetar la última build completa antes de archivarla.
- Sin tests, igual que el firmware (ver 4.5).

---

## 7. Documentación y control de versiones

| Hallazgo | Corrección concreta |
|---|---|
| README mezcla el estado actual (PlatformIO/MQTT) con contexto histórico (sketches Arduino clásicos) en un solo archivo largo | Separar en `README.md` (estado actual únicamente) + `docs/HISTORY.md` (contexto legacy), para que un colaborador nuevo no tenga que distinguir qué está vigente. |
| Sin `CHANGELOG.md` | CI publica releases por tag pero no hay changelog legible por humanos. Agregar uno mínimo, aunque sea generado desde los tags. |
| Sin `LICENSE` visible en la raíz | Si el repo sigue público, aclarar términos de uso/reutilización explícitamente. |
| Sin `CONTRIBUTING.md` | Con la app RN sumando otro frente de trabajo, conviene formalizar convención de commits, ramas y dónde vive cada cliente. |

---

## 8. CI/CD

- El único workflow (`release-firmware.yml`) cubre exclusivamente el firmware. No hay lint/build check para `desktop_app` (Python) ni, previsiblemente, para la app React Native.
- No hay escaneo de secretos en CI (ver 3.5) — es el control que hubiera evitado el hallazgo crítico de esta auditoría.

**Corrección concreta:**
- Agregar un workflow simple de lint (`ruff` o `flake8`) para `desktop_app/`.
- Cuando la app RN se sume al repo (o a uno propio), agregar build + lint (`eslint`/TypeScript) desde el día uno, no después.
- Agregar gitleaks o GitHub secret scanning al pipeline.

---

## 9. Tabla de correcciones priorizada

| # | Prioridad | Hallazgo | Acción concreta |
|---|---|---|---|
| 1 | 🔴 Crítica | Password Wi-Fi expuesta en git | Rotar contraseña hoy + purgar historial (`git filter-repo`) + force push |
| 2 | 🔴 Crítica | Sin escaneo de secretos | Activar GitHub secret scanning / gitleaks en CI |
| 3 | 🟠 Alta | Comandos de control del VFD sin auth obligatoria por MQTT | Exigir user/pass + ACL por topic en el broker; TLS si sale de la LAN |
| 4 | 🟠 Alta | AP de campo con credenciales fijas compartidas | Password derivado por dispositivo (MAC/serial) o flujo de provisioning |
| 5 | 🟠 Alta | Protocolo duplicado implícitamente entre 3 clientes | Documento/spec único de protocolo (`docs/PROTOCOL.md` o JSON Schema) referenciado por todos |
| 6 | 🟡 Media | Fail-safe ante pérdida de link no confirmado | Confirmar y documentar comportamiento del firmware si se cae MQTT/Serial durante una marcha |
| 7 | 🟡 Media | Sin tests automatizados | Tests mínimos: `ScaleTable`, parser de discovery, schema del JSON MQTT |
| 8 | 🟡 Media | Código WebSocket legacy sin remover | Eliminar `ws_client.py` o moverlo a `legacy/` |
| 9 | 🟡 Media | Historial de git sin auditar por otros secretos | `git log --all` sobre `connection_profiles.json` y archivos sensibles similares |
| 10 | 🟡 Media | Canal USB no resuelto para React Native | Documentar explícitamente qué cliente cubre qué canal (USB/BLE/MQTT) |
| 11 | 🟢 Baja | README mezcla estado actual e histórico | Separar en README + `docs/HISTORY.md` |
| 12 | 🟢 Baja | Sin `LICENSE`/`CONTRIBUTING.md` | Agregar ambos si el repo sigue público |
| 13 | 🟢 Baja | CustomTkinter congelada sin marcarlo formalmente | Nota explícita de "modo mantenimiento" en su README |
| 14 | 🟢 Baja | UI LVGL en Guition sin dueño claro | Decidir si se retoma o se descarta frente al avance de RN |

---

## 10. Orden de ejecución sugerido

1. Rotar la contraseña Wi-Fi expuesta (hoy, sin depender de nada más).
2. Activar secret scanning en el repo.
3. Auditar el historial completo de git buscando otros secretos.
4. Definir y documentar la spec de protocolo compartida entre firmware / desktop / RN.
5. Agregar autenticación y ACL a MQTT antes de cualquier prueba de campo real con la app RN.
6. Confirmar el comportamiento de fail-safe del firmware ante pérdida de link.
7. Resto de los puntos medios/bajos según capacidad del equipo.

---

*Auditoría basada en `README.md` y `CONTINUACION_ITERACION.md` al 2026-08-18. Se recomienda repetir con acceso al código fuente completo (firmware, desktop_app y app React Native) para validar o descartar los puntos marcados como "a confirmar".*
