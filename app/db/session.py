"""Compatibility shim.

app.db.session is deprecated; prefer app.core.database.get_db.
We keep this file to avoid service crashes when older modules still import it.
"""

from app.core.database import get_db  # re-export

__all__ = ["get_db"]
