"""Compatibility shim.

Old imports used: from app.db.session import get_db
Canonical location: from app.core.database import get_db

We keep this file to avoid service crashes when older modules still import it.
"""

from app.core.database import get_db  # re-export

__all__ = ["get_db"]
