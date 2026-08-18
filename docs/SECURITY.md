# Seguridad — VarioField / MULTI_VDF_HMI

Checklist de planta y lab. Fuentes: auditorías en `Auritorias recibidas/`.  
El control del VFD es una **acción física**; no tratar MQTT como “solo telemetría”.

## Estado (sprint seguridad)

| Control | Estado |
|---------|--------|
| Secretos de red de prueba fuera de HEAD | Sí (redactados); **historial** a purgar (filter-repo + force push) |
| Secret scanning / gitleaks en CI | Workflow `secret-scan.yml` |
| Mosquitto setup por defecto con auth | Sí (`allow_anonymous false` salvo `VARIOFIELD_MQTT_ANON=1`) |
| ACL por topic | Sí (app vs device) |
| AP SoftAP password único por unidad | **Deuda** — hoy fijo `sajpdm30` (documentado) |
| Roles CLI en firmware (OPERATOR/ADMIN) | **Deuda** — broker ACL es la primera línea |
| TLS MQTT (8883) | Recomendado si el broker sale de LAN |

## Qué nunca va a git

- Contraseñas Wi‑Fi / MQTT reales  
- `desktop_app/config/connection_profiles.json` (ya en `.gitignore`; usar el `.example`)  
- Dumps/logs con SSID+pass en claro  

Permitido: placeholders (`TU_PASSWORD`), hashes, docs de procedimiento.

## Broker Mosquitto (lab / planta)

```bash
# Default seguro (crea user variofield + ACL):
sudo ./desktop_app/scripts/setup_mosquitto.sh

# Solo lab sin auth (NO usar en planta):
sudo VARIOFIELD_MQTT_ANON=1 ./desktop_app/scripts/setup_mosquitto.sh
```

Variables útiles:

| Env | Default | Uso |
|-----|---------|-----|
| `VARIOFIELD_MQTT_PORT` | `1883` | Puerto listener |
| `VARIOFIELD_MQTT_USER` | `variofield` | Usuario app+device (lab simple) |
| `VARIOFIELD_MQTT_PASS` | generado / pedido | Password |
| `VARIOFIELD_MQTT_ANON` | vacío | Si `1`, anónimo (dev only) |

En el Edge:

```text
mqtt set <IP_BROKER> 1883
mqtt user <user> <pass>
mqtt enable
```

Smoke:

```bash
# Debe FALLAR si auth está activa:
mosquitto_pub -h 127.0.0.1 -t 'saj/pdm30/saj-pdm30/cmd' -m 'ping'

# Debe OK:
mosquitto_pub -h 127.0.0.1 -u "$USER" -P "$PASS" -t 'saj/pdm30/saj-pdm30/cmd' -m 'ping'
```

## SoftAP de campo

SSID `SAJ_Diag_Tool` / pass `sajpdm30` están **fijos en firmware** (`Config.h`).  
Riesgo aceptado temporalmente para taller; flota productiva debe pasar a password derivado (MAC/serial) o provisioning.

## Fail-safe ante pérdida de link

Si cae MQTT/USB/BT **no** se envía `estop` automático al VFD: el variador sigue según su lógica local.  
Parada remota requiere comando explícito (`stop` / `estop`) mientras el canal esté vivo. Documentado también en `docs/PROTOCOL.md`.

## GitHub

1. Settings → Code security → **Secret scanning** + **Push protection** (repos públicos: gratis).  
2. CI: `.github/workflows/secret-scan.yml` (gitleaks).  
3. Tras rotar cualquier secreto que haya estado en git: purgar historial (`git filter-repo`) y force-push coordinado.

## Ver también

- `docs/PROTOCOL.md` — contrato CLI/MQTT  
- `docs/PDH_VS_PDM.md` — perfiles de drive  
- `docs/ROADMAP_MULTI_VDF.md` — M2 bloqueado hasta cerrar este sprint  
