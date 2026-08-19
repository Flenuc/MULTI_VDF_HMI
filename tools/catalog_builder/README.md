# Catalog Builder (M2 MVP)

CLI to list / validate / regenerate `drive_profiles/` from manuals.

```bash
# from repo root
python3 -m tools.catalog_builder list
python3 -m tools.catalog_builder validate saj.pdh30
python3 -m tools.catalog_builder validate saj.pdm30
python3 -m tools.catalog_builder extract-manual saj.pdh30
python3 -m tools.catalog_builder extract-manual saj.pdm30
python3 -m tools.catalog_builder diff saj.pdm30 saj.pdh30
```

## Status

| Command | Status |
|---------|--------|
| `list` / `validate` / `diff` | MVP |
| `extract-manual saj.pdh30` | wraps `extract_pdh30_from_manual.py` |
| `extract-manual saj.pdm30` | wraps `generate_saj_pdm30_profile.py` |
| `extract-live` | planned (MQTT/serial dump → draft) |
| UI técnica | planned |

Roadmap: `docs/ROADMAP_MULTI_VDF.md` § M2.
