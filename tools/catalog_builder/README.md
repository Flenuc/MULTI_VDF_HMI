# Catalog Builder (M2)

CLI to list / validate / regenerate `drive_profiles/` from manuals **and** live Edge dumps.

```bash
# from repo root
python3 -m tools.catalog_builder list
python3 -m tools.catalog_builder validate saj.pdh30
python3 -m tools.catalog_builder validate saj.pdm30
python3 -m tools.catalog_builder extract-manual saj.pdh30
python3 -m tools.catalog_builder extract-manual saj.pdm30
python3 -m tools.catalog_builder diff saj.pdm30 saj.pdh30

# Live dump over MQTT (lab: Mosquitto auth + vf-… prefix)
python3 -m tools.catalog_builder extract-live saj.pdh30 \
  --via mqtt --mqtt-profile "Local Mosquitto" --write-draft

# Or explicit MQTT args
python3 -m tools.catalog_builder extract-live saj.pdh30 \
  --via mqtt --host 127.0.0.1 --prefix saj/pdm30/vf-e23fc4 \
  --username variofield --password "$VARIOFIELD_MQTT_PASS" --write-draft

# Live dump over USB serial
python3 -m tools.catalog_builder extract-live saj.pdh30 \
  --via serial --port /dev/ttyACM0 --write-draft
```

## Status

| Command | Status |
|---------|--------|
| `list` / `validate` / `diff` | OK |
| `extract-manual saj.pdh30` | wraps `extract_pdh30_from_manual.py` |
| `extract-manual saj.pdm30` | wraps `generate_saj_pdm30_profile.py` |
| `extract-live --via mqtt\|serial` | OK — writes `results/live_extract_*` + optional `profile.live_draft.json` |
| `merge` formal | planned |
| UI técnica | planned |

## Outputs (`extract-live`)

- `results/live_extract_<profile>_<ts>.json` — summary + rows
- `results/live_extract_<profile>_latest.json`
- With `--write-draft`: `drive_profiles/<vendor>/<model>/profile.live_draft.json`  
  (does **not** overwrite `profile.json`)

Password: prefer `--mqtt-profile` (local gitignored store) or env `VARIOFIELD_MQTT_PASS`.

Roadmap: `docs/ROADMAP_MULTI_VDF.md` § M2.
