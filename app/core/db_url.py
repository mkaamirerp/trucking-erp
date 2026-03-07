# DB URL normalization source-of-truth. Do not hand-roll driver conversion elsewhere.

from __future__ import annotations


def to_async_pg_url(url: str) -> str:
    """
    Normalize a PostgreSQL URL for use with create_async_engine (asyncpg driver).
    Returns a URL with scheme postgresql+asyncpg://...
    """
    if not url or not url.strip():
        return url
    u = url.strip()
    if u.startswith("postgresql+asyncpg://"):
        return u
    if u.startswith("postgresql+asyncpg:"):
        return "postgresql+asyncpg://" + u.split(":", 1)[1].lstrip("/")
    if u.startswith("postgresql+psycopg2://"):
        return "postgresql+asyncpg://" + u[19:]
    if u.startswith("postgresql+psycopg2:"):
        return "postgresql+asyncpg://" + u.split(":", 1)[1].lstrip("/")
    if u.startswith("postgresql://"):
        rest = u[12:].lstrip("/")  # avoid /// when source has postgresql:///...
        return "postgresql+asyncpg://" + rest
    if u.startswith("postgres://"):
        rest = u[10:].lstrip("/")
        return "postgresql+asyncpg://" + rest
    return u


def to_sync_pg_url(url: str) -> str:
    """
    Normalize a PostgreSQL URL for use with create_engine (sync psycopg2 driver).
    Returns a URL with scheme postgresql://...
    """
    if not url or not url.strip():
        return url
    u = url.strip()
    if u.startswith("postgresql://") and "+" not in u.split("://", 1)[0]:
        return u
    if u.startswith("postgresql+asyncpg://"):
        return "postgresql://" + u[19:]
    if u.startswith("postgresql+asyncpg:"):
        return "postgresql://" + u.split(":", 1)[1].lstrip("/")
    if u.startswith("postgresql+psycopg2://"):
        return "postgresql://" + u[19:]
    if u.startswith("postgresql+psycopg2:"):
        return "postgresql://" + u.split(":", 1)[1].lstrip("/")
    if u.startswith("postgres://"):
        return "postgresql://" + u[10:]
    return u
