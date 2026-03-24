# DB URL normalization source-of-truth. Do not hand-roll driver conversion elsewhere.

from __future__ import annotations

# Exact scheme prefixes (length-sensitive: use len() when slicing, never magic offsets).
_PG = "postgresql://"
_PG_ASYNC = "postgresql+asyncpg://"
_PG_PSYCOPG2 = "postgresql+psycopg2://"
_POSTGRES = "postgres://"


def to_async_pg_url(url: str) -> str:
    """
    Normalize a PostgreSQL URL for use with create_async_engine (asyncpg driver).
    Returns a URL with scheme postgresql+asyncpg://...
    """
    if not url or not url.strip():
        return url
    u = url.strip()
    if u.startswith(_PG_ASYNC):
        return u
    if u.startswith("postgresql+asyncpg:"):
        return _PG_ASYNC + u.split(":", 1)[1].lstrip("/")
    if u.startswith(_PG_PSYCOPG2):
        return _PG_ASYNC + u[len(_PG_PSYCOPG2):]
    if u.startswith("postgresql+psycopg2:"):
        return _PG_ASYNC + u.split(":", 1)[1].lstrip("/")
    if u.startswith(_PG):
        rest = u[len(_PG):].lstrip("/")
        return _PG_ASYNC + rest
    if u.startswith(_POSTGRES):
        rest = u[len(_POSTGRES):].lstrip("/")
        return _PG_ASYNC + rest
    return u


def to_sync_pg_url(url: str) -> str:
    """
    Normalize a PostgreSQL URL for use with create_engine (sync psycopg2 driver).
    Returns a URL with scheme postgresql://...
    """
    if not url or not url.strip():
        return url
    u = url.strip()
    if u.startswith(_PG) and "+" not in u.split("://", 1)[0]:
        return u
    if u.startswith(_PG_ASYNC):
        return _PG + u[len(_PG_ASYNC):]
    if u.startswith("postgresql+asyncpg:"):
        return _PG + u.split(":", 1)[1].lstrip("/")
    if u.startswith(_PG_PSYCOPG2):
        return _PG + u[len(_PG_PSYCOPG2):]
    if u.startswith("postgresql+psycopg2:"):
        return _PG + u.split(":", 1)[1].lstrip("/")
    if u.startswith(_POSTGRES):
        return _PG + u[len(_POSTGRES):]
    return u
