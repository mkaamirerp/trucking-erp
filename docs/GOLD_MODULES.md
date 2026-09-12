# TruckERP gold modules

Each product module that has a verified production freeze gets:

- a **gold branch** (`gold/<module>`) pointing at the exact commit
- an **immutable tag** (`<module>-gold-YYYY-MM-DD`) at that same commit
- a **manifest** listing dependent files, the baked image (if applicable), and parked bugs

Do **not** mix modules in one gold move. Do **not** build production from a dirty tree.

| Module | Branch | Manifest | Current gold commit | Immutable tag |
|---|---|---|---|---|
| Driver licence (OpenCV → processed JPEG → PDF417) | `gold/dl` | [DL_GOLD_MANIFEST.md](./DL_GOLD_MANIFEST.md) | `ac650fff` | `dl-gold-2026-09-12` |
| Load Parser | `gold/load-parser` | [LOAD_PARSER_GOLD_MANIFEST.md](./LOAD_PARSER_GOLD_MANIFEST.md) | `7df3513b` | `load-parser-gold-2026-09-07` |
| Fuel | `gold/fuel` (not created) | [FUEL_GOLD_MANIFEST.md](./FUEL_GOLD_MANIFEST.md) | none | none |

When a new gold module is created, add a row here and a sibling `*_GOLD_MANIFEST.md` that lists **only that module's files**.
