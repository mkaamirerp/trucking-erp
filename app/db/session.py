"""
DEPRECATED (Phase 9.5)

Do not use this module.

All DB access must go through:
  app.core.database (engine, AsyncSessionLocal, get_db)

This file was kept only to avoid confusion during refactors.
"""

raise RuntimeError(
    "app.db.session is deprecated. Import get_db from app.core.database instead."
)
