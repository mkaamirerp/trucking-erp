# Load Parser Gold manifest

This module is **separate** from DL Gold. Do not move `gold/load-parser` as part of a DL freeze. Do not bake uncommitted Load Parser WIP into `truckerp-api` when deploying DL.

| Item | Value |
|---|---|
| Branch | `gold/load-parser` |
| Immutable tag | `load-parser-gold-2026-09-07` |
| Gold commit | `7df3513b86e1e6a9703f1261fee8c04441a52e96` |
| Status | Unchanged by the 2026-09-12 DL gold (`ac650fff`) |

## Dependent file families (this module only)

- `app/services/load_parser*.py`
- `app/services/loads.py` / load document parse routers and schemas
- `apps/web/src/loadWorkspace/**`
- `apps/web/src/pages/LoadLabPage.tsx`, `LoadWorkspacePage.tsx`, `LoadInboxPage.tsx`
- `docs/load_parser/**`
- `tests/test_load_parser*.py`

Exact file lists for a future Load Parser gold bump belong in an update to **this** file, not in `DL_GOLD_MANIFEST.md`.

See [GOLD_MODULES.md](./GOLD_MODULES.md).
