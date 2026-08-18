# MULTI_VDF_HMI — Auditoría técnica integral y plan de correcciones

**Repositorio auditado:** https://github.com/Flenuc/MULTI_VDF_HMI  
**Fecha de auditoría:** 2026-08-14  
**Alcance:** revisión estática del repositorio público, arquitectura, firmware ESP32, comunicaciones Modbus/RS485 + MQTT/BLE/USB, backend FastAPI, UI desktop, perfiles de VFD, CI/CD, tests, configuración y evidencias de campo.  
**Limitación:** esta auditoría no sustituye una prueba de penetración ni una validación eléctrica/funcional sobre cada modelo de VFD. Las recomendaciones de seguridad funcional deben validarse con el equipo de ingeniería antes de aplicarse en campo.

---

## 1. Resumen ejecutivo

### Conclusión

El repositorio tiene una **base técnica sólida y funcional**, especialmente en:

- separación entre firmware, transportes y UI;
- implementación Modbus RTU no bloqueante;
- soporte de múltiples transportes;
- perfiles de drive;
- pruebas reales sobre hardware;
- persistencia de resultados;
- empaquetado de firmware.

Sin embargo, **todavía no está endurecido como producto industrial distribuible**. Los mayores riesgos actuales son:

1. **MQTT anónimo y sin TLS por defecto**.
2. **Comandos de control y configuración sin una capa explícita de autorización por canal/rol**.
3. **Credenciales por defecto embebidas en firmware**.
4. **Backend local demasiado permisivo para una API que puede disparar acciones de campo**.
5. **Arquitectura de desktop todavía híbrida/legacy**.
6. **Contrato de `drive_profiles` insuficientemente fuerte para declarar capacidades, permisos y parámetros soportados**.
7. **CI enfocada en release, pero sin una barrera de calidad completa para PRs**.
8. **La validación E2E del perfil PDH30 todavía registra diferencias/missing y marca `ok=false`**.

### Evaluación orientativa

| Área | Nivel | Prioridad |
|---|---|---|
| Arquitectura | Bueno | P1 |
| Firmware | Bueno | P1 |
| Modbus/RS485 | Bueno | P1 |
| Transporte MQTT | Funcional, inseguro por defecto | **P0** |
| Bluetooth | Funcional, credenciales heredadas | **P0/P1** |
| Backend | Funcional, endurecimiento pendiente | **P0/P1** |
| UI desktop | En transición | P2 |
| Drive profiles | Buena base, falta formalización | P1 |
| Tests | Buenos tests unitarios/funcionales, CI incompleta | P1 |
| Release firmware | Existe | P1 |
| Seguridad funcional | No suficientemente formalizada | **P0** |
| Producción industrial | Aún no | P0/P1 |

---

# 2. Arquitectura actual

La arquitectura documentada separa:

```text
React Native / Expo
        │
        │ HTTP + WebSocket
        ▼
FastAPI backend
        │
        ▼
comms/
 ├─ Serial
 ├─ MQTT
 ├─ BT SPP
 └─ BLE NUS
        │
        ▼
ESP32 / Guition
        │
        │ Modbus RTU / RS485
        ▼
SAJ PDM-30 / PDH30
```

La documentación del repositorio describe explícitamente esta separación y mantiene CustomTkinter como frontend legacy durante la transición. Ver `desktop_app/ARCHITECTURE.md`.

## Evaluación

### Lo que está bien

- La UI no tiene por qué conocer `pyserial`, MQTT o Bluetooth.
- El backend centraliza sesión y transportes.
- El firmware encapsula Modbus y telemetría.
- Existen perfiles de drive.
- El transporte puede cambiar sin reescribir toda la UI.

### Problema estructural

Hay dos arquitecturas coexistiendo:

```text
Arquitectura nueva:
React Native → FastAPI → comms

Arquitectura legacy:
CustomTkinter → comms directamente
```

Esto aumenta el número de caminos de ejecución que deben mantenerse.

### Corrección recomendada

Definir una arquitectura objetivo única:

```text
UI
 ↓
Application API
 ↓
Device Manager
 ↓
Transport Manager
 ↓
Drive Protocol
 ↓
Modbus
 ↓
VFD
```

CustomTkinter y el cliente WebSocket legacy deben pasar a modo de compatibilidad hasta retirarse.

---

# 3. Hallazgos críticos — P0

## P0-01 — MQTT anónimo

### Evidencia

`desktop_app/scripts/setup_mosquitto.sh` tiene como fallback:

```conf
listener ${PORT}
allow_anonymous true
```

El script usa además el puerto `1883` por defecto.

El firmware define:

```cpp
#define MQTT_DEFAULT_PORT 1883
```

y utiliza tópicos de comando:

```text
saj/pdm30/<id>/cmd
```

El README también describe MQTT como transporte principal.

### Riesgo

Cualquier host con acceso a la red donde escucha el broker puede intentar publicar comandos.

La superficie no es sólo lectura. El firmware soporta comandos como:

```text
start
stop
estop
reset
set
w0
w1
wraw
wifi set
mqtt set
mqtt user
```

En un VFD esto no debe considerarse una vulnerabilidad “teórica”: un comando remoto puede producir una acción física.

### Corrección obligatoria

Eliminar:

```conf
allow_anonymous true
```

y reemplazar por autenticación:

```conf
listener 8883
allow_anonymous false

password_file /etc/mosquitto/passwd
acl_file /etc/mosquitto/acl
```

Para producción:

```text
MQTTS + TLS + usuario/contraseña + ACL
```

### Diseño de ACL recomendado

```text
device/<id>/telemetry    → publish: device
device/<id>/status       → publish: device
device/<id>/response     → publish: device

device/<id>/command      → subscribe: device
```

y desde la aplicación:

```text
operator:
  publish command only
  subscribe response/status/telemetry

maintenance:
  operator +
  parameter write

admin:
  maintenance +
  network/config
```

### Criterio de aceptación

- El broker rechaza clientes anónimos.
- Un usuario de telemetría no puede publicar comandos.
- Un usuario operador no puede cambiar configuración MQTT/Wi-Fi.
- Un cliente no puede enviar comandos a otro `device_id`.
- Las pruebas de integración verifican ACL.

---

## P0-02 — Sin autorización de comandos por canal

### Evidencia

`CliEngine.cpp` recibe comandos y los despacha según texto.

Actualmente hay comandos de lectura, operación y configuración en el mismo parser:

```text
ping
dump
pget
pset
wraw
start
stop
estop
reset
wifi ...
mqtt ...
bt ...
profile ...
```

No existe una política centralizada de permisos tipo:

```text
READ_ONLY
OPERATOR
MAINTENANCE
ADMIN
```

### Riesgo

Aunque MQTT se autentique, un usuario correctamente autenticado puede terminar teniendo más privilegios de los necesarios.

### Corrección

Introducir una capa de autorización antes de `dispatch()`.

Ejemplo:

```cpp
enum class Permission : uint8_t {
    READ_ONLY,
    OPERATOR,
    MAINTENANCE,
    ADMIN
};

enum class CommandId : uint8_t {
    PING,
    STATUS,
    DUMP,
    PGET,
    PSET,
    START,
    STOP,
    ESTOP,
    RESET,
    WRAW,
    WIFI_CONFIG,
    MQTT_CONFIG,
    BT_CONFIG,
    PROFILE_CONFIG
};
```

Luego:

```cpp
struct CommandPolicy {
    CommandId id;
    Permission required;
};
```

### Matriz propuesta

| Comando | Rol mínimo |
|---|---|
| `ping` | READ_ONLY |
| `status` | READ_ONLY |
| `dump` | READ_ONLY |
| `pget` | READ_ONLY |
| `r0/r1` | READ_ONLY |
| `telemetry` | READ_ONLY |
| `start` | OPERATOR |
| `stop` | OPERATOR |
| `estop` | OPERATOR |
| `reset` | OPERATOR |
| `pset` | MAINTENANCE |
| `w0/w1` | MAINTENANCE |
| `wraw` | ADMIN |
| `wifi set` | ADMIN |
| `wifi profile ...` | ADMIN |
| `mqtt set/user/enable` | ADMIN |
| `bt clearbonds` | ADMIN |
| `profile set` | ADMIN |

### Criterio de aceptación

Cada comando debe fallar explícitamente si el canal no tiene permiso:

```text
ERR forbidden command=start role=READ_ONLY
```

---

## P0-03 — Credenciales por defecto embebidas en firmware

### Evidencia

`firmware/saj_pdm30_edge/include/Config.h` define:

```cpp
#define BT_PIN_CODE "1234"
#define WIFI_AP_SSID "SAJ_Diag_Tool"
#define WIFI_AP_PASS "sajpdm30"
```

### Riesgo

Si varias unidades salen con los mismos defaults, la identidad de red se vuelve predecible.

### Corrección

Cada dispositivo debe tener una identidad propia:

```text
device_id = MAC / efuse ID / UUID
ssid = SAJ-Edge-<suffix>
password = secret único generado en provisioning
```

La credencial inicial debe:

- generarse por unidad;
- mostrarse sólo durante provisioning;
- poder rotarse;
- nunca quedar publicada como una constante universal.

Bluetooth:

- usar SSP/secure pairing cuando el hardware lo permita;
- eliminar PIN fijo de producto;
- almacenar pairing/bonds de forma controlada.

### Criterio de aceptación

Dos unidades flasheadas con la misma imagen no deben compartir la contraseña del AP.

---

## P0-04 — Separación entre “parada lógica” y seguridad funcional

El software implementa:

```text
stop
estop
reset
```

pero el propio README indica que para marcha/paro por bus se debe mantener disponible la parada de emergencia física.

### Riesgo

Un comando llamado `estop` en el protocolo de software puede confundirse con una función de seguridad funcional real.

### Corrección

Renombrar semánticamente la operación de software:

```text
software_trip
free_stop
decel_stop
fault_reset
```

y documentar:

> El comando de software NO sustituye un circuito de parada de emergencia ni una función STO certificada.

La UI debe evitar etiquetar como “E-STOP” una acción que no sea realmente un E-Stop físico/certificado.

### Criterio de aceptación

- La documentación lo distingue explícitamente.
- La UI usa terminología inequívoca.
- El software jamás presenta su comando remoto como función de seguridad certificada.

---

# 4. Hallazgos altos — P1

## P1-01 — Broker local expuesto en 0.0.0.0

El script prueba finalmente:

```text
broker escuchando en 0.0.0.0:${PORT}
```

aunque verifica el puerto a través de loopback.

### Riesgo

El broker puede quedar accesible desde la LAN.

### Corrección

Por defecto:

```conf
listener 1883 127.0.0.1
```

Para conexión desde el Edge por LAN:

- habilitar listener LAN sólo con autenticación;
- preferiblemente TLS;
- firewall local;
- ACL por device ID.

No se debe elegir `0.0.0.0` sólo por comodidad.

---

## P1-02 — CORS demasiado permisivo

La documentación identifica CORS abierto para desarrollo.

Además, el backend debe considerarse una superficie de control, no sólo una API informativa.

### Corrección

En desarrollo:

```python
DEV_ORIGINS = [
    "http://127.0.0.1:8081",
    "http://localhost:8081",
    "http://127.0.0.1:19006",
    "http://localhost:19006",
]
```

En producción:

```python
PROD_ORIGINS = [
    "http://127.0.0.1:<desktop-port>"
]
```

Y no exponer el backend a LAN salvo que exista autenticación explícita.

---

## P1-03 — API de configuración sin autorización propia

El backend expone endpoints para:

- perfiles;
- Wi-Fi;
- MQTT;
- listas;
- drive profiles;
- comandos;
- conexión;
- broker setup.

Esto requiere distinguir:

```text
read API
operator API
maintenance API
admin API
```

### Corrección

Introducir autenticación local para operaciones sensibles.

Ejemplo conceptual:

```text
GET /health                 public localhost
GET /telemetry              read
POST /command               operator+
PUT /profiles               maintenance+
POST /broker/setup          admin
PUT /network                admin
```

---

## P1-04 — Endpoint de setup de Mosquitto demasiado poderoso

El script puede:

- instalar paquetes;
- escribir configuración;
- activar servicios;
- usar `sudo`.

Eso es correcto para un instalador, pero no debería estar mezclado con el camino normal de operación.

### Corrección

Separar:

```text
desktop installer / provisioning tool
```

de:

```text
runtime backend
```

Idealmente:

```text
backend runtime
  └─ broker status

installer
  └─ broker install/configure
```

Si se mantiene `/broker/setup`, debe exigir `ADMIN` y estar estrictamente limitado a `localhost`.

---

## P1-05 — Protocolo de comandos basado en texto

Actualmente MQTT transporta CLI textual.

Ejemplo:

```text
set 50
```

### Ventaja

Es excelente para debugging.

### Problema

Faltan:

- correlation ID;
- schema;
- versión de protocolo;
- timestamp;
- idempotencia;
- error codes estables;
- trazabilidad.

### Corrección recomendada

Mantener CLI textual para diagnóstico y crear un protocolo estructurado para la aplicación.

Ejemplo:

```json
{
  "version": 1,
  "id": "cmd-7f1a2e",
  "command": "set_frequency",
  "value": 50.0,
  "unit": "percent",
  "device_id": "saj-001"
}
```

Respuesta:

```json
{
  "version": 1,
  "id": "cmd-7f1a2e",
  "ok": true,
  "command": "set_frequency",
  "value": 50.0,
  "device_id": "saj-001"
}
```

### Error:

```json
{
  "version": 1,
  "id": "cmd-7f1a2e",
  "ok": false,
  "error": {
    "code": "FORBIDDEN",
    "message": "command requires OPERATOR role"
  }
}
```

---

## P1-06 — Falta idempotencia y protección ante comandos repetidos

Un problema típico de MQTT es la repetición de mensajes.

Ejemplo peligroso:

```text
start
start
start
```

o una escritura repetida después de reconexión.

### Corrección

Agregar:

```text
command_id
sequence_number
created_at
expires_at
```

y en firmware:

```cpp
if (alreadyProcessed(commandId)) {
    return cachedResponse(commandId);
}
```

Para comandos físicos:

```text
TTL <= 2 s
```

o el límite que determine el diseño de campo.

---

## P1-07 — Drive profiles necesitan convertirse en contrato formal

El repositorio ya tiene:

```text
saj.pdm30
saj.pdh30
```

y el firmware cambia comportamiento con el perfil.

Eso es bueno, pero la representación actual todavía no cubre toda la semántica que el sistema necesita.

### El perfil debe declarar

```json
{
  "id": "saj.pdm30",
  "vendor": "SAJ",
  "model": "PDM-30",
  "protocol": {
    "kind": "modbus_rtu",
    "baud": 9600,
    "parity": "N",
    "stop_bits": 1
  },
  "capabilities": {
    "start": true,
    "stop": true,
    "free_stop": true,
    "fault_reset": true,
    "parameter_write": true
  },
  "parameters": {}
}
```

Cada parámetro debería tener:

```json
{
  "id": "P0-00",
  "address": "0x0000",
  "data_type": "uint16",
  "scale": 0.1,
  "unit": "bar",
  "readable": true,
  "writable": true,
  "manual_only": false,
  "safety_level": "normal"
}
```

---

# 5. Hallazgos de validación E2E

## P1-08 — Receta PDH30 no pasa el E2E completamente

El último resultado versionado indica:

```text
param_count       = 79
writable_count    = 62
dump_ids          = 143
compare_matches   = 60
compare_mismatches= 2
compare_missing   = 2
sync              = skipped
ok                = false
```

Los faltantes reportados incluyen:

```text
F0.09
F0.19
```

### Interpretación

No significa necesariamente que el firmware esté roto.

Puede indicar:

- parámetro no soportado por la variante real;
- parámetro sólo documental;
- registro no legible;
- nombre diferente;
- mapping incorrecto;
- condición operacional especial.

### Corrección

No representar un parámetro únicamente como:

```text
exists = true/false
```

Usar estados:

```text
SUPPORTED
READ_ONLY
WRITABLE
MANUAL_ONLY
UNAVAILABLE
RESERVED
VARIANT_DEPENDENT
```

Y el comparador debe diferenciar:

```text
missing because unsupported
```

de:

```text
missing because communication failed
```

Esto es importante para no esconder fallas de bus.

---

# 6. Firmware — revisión técnica

## 6.1 Lo correcto

`CliEngine.cpp` ya implementa una estrategia razonable de arbitraje:

- pausa telemetría;
- no bloquea innecesariamente;
- encola una operación;
- evita que USB/MQTT parezcan muertos cuando el stream está activo.

Esto es una muy buena decisión para un dispositivo que comparte CPU y bus.

El código también limita el parsing y usa buffers con tamaño máximo.

## 6.2 Problemas a corregir

### A. Parser y autorización están demasiado acoplados

El parser conoce:

- sintaxis;
- transporte;
- operación;
- configuración;
- modelo de drive.

Separar:

```text
Lexer / Parser
     ↓
Command AST
     ↓
Authorizer
     ↓
Command Executor
```

### B. `atoi()`/parseo básico en entradas críticas

Para parámetros sensibles, utilizar parseo explícito con validación:

```cpp
bool parseUint16Strict(...)
bool parseFloatFinite(...)
bool parsePort(...)
bool parseSlaveId(...)
```

Evitar aceptar silenciosamente:

```text
abc → 0
```

en rutas sensibles.

### C. Escribir registros raw debe requerir modo privilegiado

`wraw` es una herramienta de servicio, no un comando de operador.

Debe estar:

- bloqueada por defecto;
- disponible solamente con `ADMIN`;
- opcionalmente protegida por un “maintenance unlock” temporal.

### D. Parámetros peligrosos deben tener metadata

El código/documentación identifica `P0-38` como peligroso.

Eso debe estar en el perfil:

```json
{
  "id": "P0-38",
  "risk": "HIGH",
  "requires_confirmation": true,
  "requires_role": "ADMIN"
}
```

---

# 7. Modbus / RS485

## Evaluación

El repositorio documenta correctamente:

- baud;
- 8N1;
- slave ID;
- FC 0x03;
- FC 0x06;
- registros especiales;
- tiempos de respuesta;
- mapas P0/P1.

También existe evidencia de campo con lectura y escritura real.

## Correcciones

### A. CRC/error telemetry

Registrar contadores:

```text
modbus_requests
modbus_success
modbus_timeout
modbus_crc_error
modbus_exception_response
modbus_invalid_frame
```

### B. Distinción entre timeout y “registro no existe”

Muy importante para el comparador de perfiles.

```text
NOT_SUPPORTED
TIMEOUT
CRC_ERROR
SLAVE_EXCEPTION
INVALID_VALUE
```

no deben colapsar a:

```text
null
```

### C. Límite de escrituras

Agregar rate limit:

```text
parameter writes per minute
raw writes per minute
control commands per second
```

para proteger el equipo de loops accidentales.

### D. Verificación read-after-write

Para parámetros no volátiles:

```text
write
 ↓
delay
 ↓
read
 ↓
compare
 ↓
report
```

y sólo declarar:

```text
write successful
```

si la confirmación corresponde.

---

# 8. Telemetría

Actualmente la telemetría se publica aproximadamente a 1 Hz.

Es correcto como primera implementación.

Debe formalizarse el esquema:

```json
{
  "version": 1,
  "device_id": "saj-001",
  "timestamp": "...",
  "status": 3,
  "run_frequency_hz": 0.0,
  "set_pressure_bar": 10.0,
  "feedback_pressure_bar": 0.0,
  "bus_voltage_v": 310.0,
  "output_voltage_v": 0,
  "output_current_a": 0
}
```

Agregar:

```text
firmware_version
profile_id
protocol_version
sequence
uptime_s
rssi
mqtt_connected
modbus_health
```

Esto hace mucho más fácil diagnosticar campo.

---

# 9. Backend FastAPI

## Problemas

### A. Endpoints de lectura/escritura mezclados

Separar routers:

```text
routers/
  health.py
  devices.py
  telemetry.py
  commands.py
  profiles.py
  broker.py
  admin.py
```

### B. Errores demasiado genéricos

Hay rutas que convierten cualquier `Exception` en:

```text
400 detail=str(e)
```

Esto tiene tres problemas:

1. mezcla errores internos con errores de usuario;
2. puede filtrar detalles internos;
3. pierde códigos de error estables.

### Corrección

Definir excepciones de dominio:

```python
class DeviceNotConnected(Exception): ...
class DeviceBusy(Exception): ...
class InvalidCommand(Exception): ...
class PermissionDenied(Exception): ...
class TransportTimeout(Exception): ...
```

y mapear:

```text
409 BUSY
400 INVALID_COMMAND
403 FORBIDDEN
504 TRANSPORT_TIMEOUT
404 NOT_FOUND
500 INTERNAL
```

---

# 10. Gestión de secretos

Aunque `connection_profiles.json` está correctamente en `.gitignore`, el diseño todavía debe distinguir:

```text
configuration
```

de:

```text
secret
```

Nunca guardar contraseñas como parte de logs.

### Mejor práctica

```json
{
  "name": "Local Mosquitto",
  "host": "127.0.0.1",
  "port": 8883,
  "username": "operator",
  "password_ref": "os-keyring://multi-vdf/mqtt/operator"
}
```

En Windows:

```text
Credential Manager
```

En Linux:

```text
Secret Service / keyring
```

No usar JSON plano para secretos de producción.

---

# 11. Desktop / React Native / Electron

## Situación actual

La arquitectura documenta:

- Expo;
- FastAPI;
- Electron;
- CustomTkinter legacy.

Eso es razonable durante migración, pero conviene cerrar la transición.

### Objetivo

```text
React Native / Expo
        ↓
FastAPI
        ↓
comms
```

CustomTkinter queda:

```text
legacy/
```

hasta retirar.

### Criterios de limpieza

No deberían existir dos implementaciones para la misma operación en:

```text
GUI → comms
GUI → backend → comms
```

Cada feature nueva debe entrar únicamente por el backend.

---

# 12. Tests

## Lo bueno

Hay tests headless para:

- modelos;
- storage;
- recetas;
- parsing;
- perfiles PDM30/PDH30.

El repositorio también conserva resultados de hardware real.

## Lo que falta

### A. Tests de seguridad

Agregar tests que verifiquen:

```text
anonymous MQTT rejected
operator cannot wraw
read-only cannot start
maintenance cannot change Wi-Fi
device A cannot command device B
expired command rejected
replayed command rejected
```

### B. Tests de protocolo

Fixtures:

```text
valid telemetry
invalid telemetry
malformed command
unknown command
duplicate command
out-of-order response
MQTT reconnect
Modbus timeout
Modbus exception
```

### C. Tests de backend

Añadir:

```text
pytest
pytest-asyncio
httpx
```

para endpoints.

### D. Tests de firmware

Aislar la lógica que no depende de hardware:

```text
command parser
permission policy
parameter scaling
profile selection
packet encoding
```

y probarla en host.

---

# 13. CI/CD

El workflow `release-firmware.yml` está bien como mecanismo de empaquetado, pero actualmente la automatización visible está muy orientada a releases por tag.

## Faltan checks obligatorios de PR

Crear:

```text
.github/workflows/ci.yml
```

con:

```yaml
jobs:
  python:
    - install requirements
    - pytest

  lint:
    - ruff
    - mypy (si se adopta)

  frontend:
    - npm ci
    - npm run build

  firmware:
    - pip install platformio
    - pio run -e esp32dev
    - pio run -e guition_jc_esp32p4_m3

  security:
    - secret scan

  packaging:
    - package firmware
    - verify manifest
```

## Checks de calidad

Añadir:

```text
Ruff
Pytest
Bandit
Gitleaks / secret scanning
npm audit (con política)
PlatformIO compile
```

No recomendaría convertir `npm audit` en “bloqueo absoluto” desde el primer día: primero medir el estado del árbol de dependencias.

---

# 14. Release de firmware

El workflow actual publica ZIP + manifest.

Eso es bueno.

### Faltan

#### SHA256

Publicar:

```text
firmware.zip
firmware.zip.sha256
manifest.json
```

#### Versionado de protocolo

El manifest debería incluir:

```json
{
  "firmware_version": "0.4.0",
  "protocol_version": 1,
  "drive_profiles": [
    "saj.pdm30",
    "saj.pdh30"
  ],
  "build_commit": "abc1234"
}
```

#### Compatibilidad

Ejemplo:

```json
{
  "min_desktop_version": "0.5.0"
}
```

Así se evita que un firmware nuevo rompa una app antigua.

---

# 15. Provisioning recomendado

Actualmente la configuración depende de comandos.

Para producción conviene implementar un flujo de provisioning explícito:

```text
1. Factory reset
2. Generate device ID
3. Generate AP credential
4. Generate MQTT identity
5. Pairing Bluetooth
6. Register firmware version
7. Store provisioning metadata
8. Lock privileged commands
```

Guardar un estado:

```text
PROVISIONING
PROVISIONED
MAINTENANCE
LOCKED
```

---

# 16. Modelo de identidad del dispositivo

Cada Edge debe tener:

```text
device_id
serial_number
hardware_revision
firmware_version
protocol_version
drive_profile
```

Ejemplo:

```json
{
  "device_id": "saj-edge-8A31F2",
  "serial_number": "VF-2026-00031",
  "hardware_revision": "ESP32DEV-R2",
  "firmware_version": "0.4.0",
  "protocol_version": 1,
  "drive_profile": "saj.pdm30"
}
```

Esto debe formar parte de:

- telemetry;
- status;
- logs;
- responses;
- diagnóstico.

---

# 17. Logging y auditoría operacional

Para comandos que cambian el estado físico o parámetros:

```text
timestamp
user/role
device_id
command_id
command
old_value
new_value
result
transport
firmware_version
```

Ejemplo:

```json
{
  "timestamp": "2026-08-14T13:20:31Z",
  "operator": "maintenance",
  "device_id": "saj-edge-8A31F2",
  "command_id": "cmd-123",
  "command": "pset",
  "parameter": "P0-00",
  "old_value": 10.0,
  "new_value": 12.0,
  "result": "verified"
}
```

Esto es esencial para trazabilidad.

---

# 18. Protección específica para `wraw`

`wraw` es útil para diagnóstico, pero es un comando de máximo riesgo.

Implementar:

```text
ADMIN
+
maintenance unlock
+
timeout
+
confirmation token
```

Ejemplo:

```text
unlock maintenance 300
```

y durante cinco minutos:

```text
wraw ...
```

Luego el permiso caduca automáticamente.

Alternativa mejor:

```text
raw register write
```

sólo desde un modo de servicio local USB.

---

# 19. Parámetros peligrosos

Crear metadata como:

```json
{
  "id": "P0-38",
  "label": "Parameter initialization",
  "risk": "HIGH",
  "requires_confirmation": true,
  "requires_role": "ADMIN",
  "backup_before_write": true
}
```

Al escribir un parámetro HIGH:

```text
1. Read current value
2. Create backup/audit record
3. Confirm operation
4. Write
5. Read back
6. Verify
7. Persist audit event
```

---

# 20. Backups / restore

Para perfiles y recetas:

```text
profile.json
profile.meta.json
audit.log
```

El sistema debería preservar:

```text
before.json
after.json
diff.json
```

Nunca realizar una restauración masiva silenciosa.

---

# 21. Descubrimiento de mapa Modbus

El mecanismo de discovery es una de las partes más interesantes del proyecto.

La estrategia:

1. `ping`
2. probar esquemas
3. leer defaults
4. usar `watch`
5. comparar cambios
6. generar CSV

es razonable.

### Corrección

Guardar también un manifest:

```json
{
  "device": "SAJ PDM-30",
  "firmware_version": "3305",
  "capture_date": "...",
  "slave_id": 1,
  "baud": 9600,
  "map_scheme": "MAP_GROUP_DIRECT",
  "confidence": 0.98
}
```

Así el mapping deja de depender de una captura informal.

---

# 22. Registros especiales

Hay observaciones de campo importantes como:

```text
0x100F no coincide con P0-00 en cierta unidad
0x1010 sí funciona como feedback de presión
```

No deben quedar sólo como comentarios dispersos.

Convertirlos en una matriz de compatibilidad:

| Registro | PDM30 | PDH30 | Variante | Escala | Nota |
|---|---|---|---|---|---|
| 0x1000 | ? | ? | ? | % | set freq |
| 0x1001 | sí | sí | ? | 0.01 Hz | run freq |
| 0x100F | variable | ? | unidad-dependiente | ? | no asumir P0-00 |
| 0x1010 | sí | ? | ? | 0.1 bar | feedback |

---

# 23. Errores y códigos de dominio

Crear un catálogo estable:

```text
E000 transport error
E001 timeout
E002 modbus crc
E003 modbus exception
E010 invalid command
E011 invalid parameter
E020 forbidden
E021 maintenance locked
E030 profile mismatch
E031 unsupported parameter
E040 verification failed
E050 device busy
```

No depender solamente de mensajes humanos.

La UI puede mostrar mensajes amigables, pero el backend/firmware debe devolver códigos estables.

---

# 24. Estado del dispositivo

Definir una máquina de estados explícita:

```text
BOOT
  ↓
INITIALIZING
  ↓
READY
  ├── DEGRADED
  ├── MQTT_DISCONNECTED
  ├── MODBUS_FAULT
  ├── MAINTENANCE
  └── ERROR
```

Esto evita que la UI tenga que inferir el estado a partir de múltiples strings.

---

# 25. Concurrencia Modbus / Telemetría / comandos

La estrategia actual de pausar telemetría mientras corre una operación es correcta.

Debe formalizarse como un `BusScheduler`.

Ejemplo:

```text
Priority 0: safety/control
Priority 1: explicit user read/write
Priority 2: health/status
Priority 3: periodic telemetry
Priority 4: dump/discovery
```

Esto es mejor que depender de flags repartidos en `CliEngine`.

---

# 26. Dumps largos

El repositorio ya documenta una solución de pacing/batching para evitar truncados.

Mantener esa lógica, pero protocolizarla:

```text
dump.begin
dump.chunk
dump.end
```

Cada chunk:

```json
{
  "dump_id": "d123",
  "seq": 4,
  "total": 12,
  "records": [...]
}
```

El cliente puede reconstruir el dump y detectar:

```text
missing chunk
duplicate chunk
out-of-order chunk
```

---

# 27. Persistencia

No guardar secretos junto con preferencias normales.

Separar:

```text
settings/
  app.json
  ui.json
  profiles.json

secrets/
  OS keyring

cache/
  last telemetry
  discovery captures

audit/
  commands
  parameter changes
```

---

# 28. Estructura de repositorio recomendada

Objetivo:

```text
MULTI_VDF_HMI/
├── firmware/
│   └── edge/
├── desktop_app/
│   ├── backend/
│   │   ├── api/
│   │   ├── domain/
│   │   ├── transport/
│   │   └── services/
│   ├── frontend/
│   ├── comms/
│   └── tests/
├── drive_profiles/
│   ├── saj/
│   │   ├── pdm30.json
│   │   └── pdh30.json
├── protocol/
│   ├── command.schema.json
│   ├── telemetry.schema.json
│   └── response.schema.json
├── tools/
├── docs/
└── .github/
    └── workflows/
```

---

# 29. Limpieza de legacy

Mover progresivamente:

```text
arduino/
```

a:

```text
legacy/
```

o mantenerlo pero etiquetarlo claramente como historical/reference.

Igual para:

```text
CustomTkinter
ws_client.py
```

La regla debe ser:

> ningún feature nuevo se implementa en legacy.

---

# 30. Correcciones concretas — orden recomendado

## Sprint 1 — Seguridad/P0

- [ ] Desactivar `allow_anonymous`.
- [ ] Añadir autenticación MQTT.
- [ ] Añadir ACL por dispositivo.
- [ ] Añadir roles de comando.
- [ ] Eliminar credenciales universales del firmware.
- [ ] Separar “software stop” de “emergency stop”.
- [ ] Restringir backend a localhost.
- [ ] Corregir CORS.
- [ ] Proteger `/broker/setup`.
- [ ] Proteger `wraw`.

## Sprint 2 — Protocolo/P1

- [ ] Introducir `command_id`.
- [ ] Introducir `protocol_version`.
- [ ] JSON schema para command/response/telemetry.
- [ ] Error codes.
- [ ] Deduplicación de comandos.
- [ ] TTL de comandos.
- [ ] `device_id` obligatorio.
- [ ] Read-after-write.

## Sprint 3 — Drive profiles/P1

- [ ] Definir schema de profile.
- [ ] Describir capabilities.
- [ ] Describir permisos.
- [ ] Describir riesgos.
- [ ] Marcar unsupported/manual-only.
- [ ] Crear matriz de compatibilidad PDM30/PDH30.
- [ ] Resolver o clasificar F0.09 / F0.19.

## Sprint 4 — CI/P1

- [ ] `pytest`.
- [ ] `ruff`.
- [ ] `bandit`.
- [ ] secret scan.
- [ ] build frontend.
- [ ] compile ESP32.
- [ ] compile Guition.
- [ ] package smoke test.
- [ ] tests API.
- [ ] tests protocol.
- [ ] tests security.

## Sprint 5 — Robustez/P2

- [ ] BusScheduler.
- [ ] state machine.
- [ ] métricas Modbus.
- [ ] dump chunk protocol.
- [ ] structured logs.
- [ ] audit trail.

## Sprint 6 — UX / packaging/P2

- [ ] Retirar CustomTkinter gradualmente.
- [ ] Unificar UI.
- [ ] Provisioning wizard.
- [ ] Health dashboard.
- [ ] Firmware compatibility check.
- [ ] checksum verification.

---

# 31. Cambios de código de alta prioridad

## 31.1 MQTT seguro

### Antes

```conf
listener 1883
allow_anonymous true
```

### Después

```conf
listener 8883
allow_anonymous false
password_file /etc/mosquitto/passwd
acl_file /etc/mosquitto/acl

listener 1884 127.0.0.1
allow_anonymous true
```

El listener local anónimo puede mantenerse exclusivamente para la app local si se considera necesario, pero nunca debe mezclarse con el listener LAN.

---

## 31.2 Policy layer de firmware

Crear:

```text
include/CommandPolicy.h
src/CommandPolicy.cpp
```

API:

```cpp
Permission requiredPermission(const ParsedCommand& cmd);
bool authorize(const Channel& channel, Permission required);
```

`CliEngine` debe dejar de decidir permisos implícitamente.

---

## 31.3 Command envelope

Crear:

```text
protocol/CommandEnvelope
```

Campos mínimos:

```text
version
id
device_id
command
args
created_at
expires_at
```

---

## 31.4 Telemetry schema

Versionar el payload:

```json
{
  "v": 1,
  "device_id": "...",
  "fw": "...",
  "profile": "...",
  "seq": 123,
  "ts": "...",
  "status": {...},
  "process": {...},
  "bus": {...}
}
```

---

# 32. Definición de “Done” para producción

El proyecto debería considerarse “release candidate” solamente cuando cumpla:

### Seguridad

```text
[ ] No anonymous MQTT
[ ] No default universal secrets
[ ] TLS para LAN
[ ] Roles
[ ] ACL
[ ] command TTL
[ ] replay protection
[ ] wraw locked
[ ] backend localhost by default
```

### Firmware

```text
[ ] Modbus error counters
[ ] read-after-write
[ ] state machine
[ ] device identity
[ ] version reporting
```

### Desktop

```text
[ ] API error model
[ ] protocol version check
[ ] profile validation
[ ] secret storage
[ ] logs/audit
```

### CI

```text
[ ] PR CI
[ ] firmware compile
[ ] Python tests
[ ] backend tests
[ ] frontend build
[ ] security scan
[ ] release checksum
```

### Field

```text
[ ] PDM30 field validation
[ ] PDH30 field validation
[ ] disconnect/reconnect
[ ] MQTT failure
[ ] Modbus timeout
[ ] power cycle
[ ] wrong profile
[ ] unauthorized command
[ ] duplicate command
```

---

# 33. Tests de aceptación que deben agregarse

## Caso 1 — MQTT anónimo

```text
client without credentials → CONNECT
expected: CONNACK refused
```

## Caso 2 — operador intenta `wraw`

```text
operator → wraw 0x0000 99
expected: FORBIDDEN
```

## Caso 3 — operador ejecuta start

```text
operator → start
expected:
  accepted
  command_id returned
  physical response verified
```

## Caso 4 — comando expirado

```text
created_at = T
expires_at = T-1
expected: EXPIRED_COMMAND
```

## Caso 5 — replay

```text
same command_id twice
expected:
  second request returns cached result
  no second physical action
```

## Caso 6 — perfil incorrecto

```text
PDH30 recipe against PDM30
expected:
  profile mismatch
  no blind writes
```

## Caso 7 — parámetro no soportado

```text
F0.09 unavailable
expected:
  UNSUPPORTED
  not generic "missing"
```

## Caso 8 — read-after-write

```text
write P0-00
read P0-00
expected equal within profile tolerance
```

---

# 34. Riesgos que no deben considerarse “bugs”

Algunas observaciones del repositorio son restricciones de hardware/protocolo y no necesariamente errores:

- diferencias PDM30/PDH30;
- registros no publicados oficialmente;
- tiempos RS485;
- necesidad de discovery;
- parámetros manual-only;
- diferencias por revisión de VFD.

El error sería ocultarlas.

La solución correcta es modelarlas como **capabilities/versiones/variantes**.

---

# 35. Prioridad técnica final

## P0 — impedir acciones no autorizadas

Esto es lo primero.

```text
MQTT security
+
command authorization
+
device identity
+
wraw lock
+
secure defaults
```

## P1 — hacer que el sistema sea determinista

```text
command IDs
+
protocol schema
+
error codes
+
profiles
+
state machine
+
read-after-write
```

## P2 — hacer que sea mantenible

```text
CI
+
unified architecture
+
legacy cleanup
+
observability
```

## P3 — funcionalidades nuevas

Sólo después de lo anterior:

```text
mobile
multi-drive
advanced recipes
remote diagnostics
OTA
cloud integration
```

---

# 36. Conclusión final de auditoría

**No recomiendo reescribir MULTI_VDF_HMI.**

La arquitectura y el firmware tienen suficiente base para continuar.

La prioridad es **endurecer el producto alrededor de una base funcional que ya demostró comunicación real con el VFD**.

El repositorio contiene evidencia de pruebas de campo con lectura/escritura de P0/P1 y dumps completos, lo que valida que la parte esencial del stack funciona. Sin embargo, el resultado E2E PDH30 actual sigue mostrando `ok=false` por parámetros faltantes/mismatches, por lo que la capa de perfiles debe formalizarse antes de confiar en sincronizaciones masivas. 

El orden correcto es:

```text
              ┌────────────────────┐
              │      AHORA         │
              └─────────┬──────────┘
                        │
                 1. SECURITY
                        │
                 2. PROTOCOL
                        │
                 3. PROFILES
                        │
                 4. CI / TESTS
                        │
                 5. ROBUSTNESS
                        │
                 6. UX / FEATURES
                        ▼
              ┌────────────────────┐
              │ PRODUCTO INDUSTRIAL│
              └────────────────────┘
```

### Dictamen

**Arquitectura:** aprobada con refactor incremental.  
**Firmware:** aprobable para seguir evolucionando.  
**Modbus/RS485:** funcional, requiere hardening y métricas.  
**MQTT:** no aprobar para producción hasta corregir autenticación/ACL/TLS.  
**Backend:** no aprobar exposición LAN sin autenticación.  
**Seguridad funcional:** separar claramente software control de funciones de seguridad.  
**Drive profiles:** convertirlos en contrato formal antes de escalar a múltiples VFD.  
**CI/CD:** ampliar a PR gates.  
**UI:** consolidar la arquitectura y retirar legacy progresivamente.

---

# 37. Fuentes / evidencia revisada

- Repositorio principal: https://github.com/Flenuc/MULTI_VDF_HMI
- Arquitectura desktop: `desktop_app/ARCHITECTURE.md`
- Firmware command engine: `firmware/saj_pdm30_edge/src/CliEngine.cpp`
- Configuración firmware: `firmware/saj_pdm30_edge/include/Config.h`
- Backend: `desktop_app/backend/main.py`
- Setup Mosquitto: `desktop_app/scripts/setup_mosquitto.sh`
- Tests headless: `desktop_app/tests/test_logic.py`
- CI de releases: `.github/workflows/release-firmware.yml`
- Validación E2E: `results/e2e_pdh30_recipe_latest.json`
- Evidencia CLI/Modbus: `results/cli_test_report.txt`

---

## Referencias puntuales observadas

### Arquitectura

La documentación declara React Native/Expo → FastAPI → `comms/` y mantiene CustomTkinter como capa de transición. (`desktop_app/ARCHITECTURE.md`)

### Seguridad MQTT

El setup local contiene `allow_anonymous true` como fallback y arranca el listener en el puerto 1883. (`desktop_app/scripts/setup_mosquitto.sh`)

### Credenciales por defecto

`Config.h` contiene el PIN Bluetooth `1234` y credenciales fijas del SoftAP. (`firmware/saj_pdm30_edge/include/Config.h`)

### Comandos sensibles

`CliEngine.cpp` registra y ejecuta comandos de control y configuración como `start`, `stop`, `reset`, `wraw`, `wifi ...`, `mqtt ...` y `bt ...`. (`firmware/saj_pdm30_edge/src/CliEngine.cpp`)

### Resultado E2E

El último reporte versionado muestra 79 parámetros, 62 writable, 60 matches, 2 mismatches/missing y `ok=false`, con `F0.09` y `F0.19` como faltantes. (`results/e2e_pdh30_recipe_latest.json`)

### Evidencia de hardware

El reporte CLI muestra `ping`, lecturas P0/P1, write/readback y dump de parámetros reales. (`results/cli_test_report.txt`)

---

# 38. Checklist ejecutivo para la próxima iteración

- [ ] Cerrar P0 antes de agregar features de control remoto.
- [ ] Crear `CommandPolicy`.
- [ ] Crear schema de command/response/telemetry.
- [ ] Crear `device_id`.
- [ ] Eliminar secretos universales.
- [ ] Pasar MQTT LAN a autenticado/TLS.
- [ ] Aislar broker setup.
- [ ] Formalizar `drive_profiles`.
- [ ] Clasificar parámetros unsupported/manual-only/high-risk.
- [ ] Resolver E2E PDH30.
- [ ] Añadir CI de PR.
- [ ] Añadir tests de seguridad.
- [ ] Añadir read-after-write.
- [ ] Añadir auditoría de cambios.
- [ ] Unificar frontend/backend.
- [ ] Retirar legacy progresivamente.
- [ ] Repetir auditoría tras P0/P1.

**Resultado esperado de la siguiente auditoría:** ningún P0 abierto y todos los comandos sensibles cubiertos por una política de autorización verificable automáticamente.
