# TruckERP Core Rules (ALWAYS)

## Non-negotiables
- Small changes only; one concern at a time.
- Never edit multiple files without asking first.
- Prefer: plan → patch → run checks → summarize.
- Never "clean up" or refactor unless asked.
- If unsure, ask for the exact command/log/output rather than guessing.

## Commands (prefer these)
- Backend tests: `pytest -q`
- Format: (only if requested) ruff / black
- Docker logs: `docker compose logs --since 15m truckerp-api`
