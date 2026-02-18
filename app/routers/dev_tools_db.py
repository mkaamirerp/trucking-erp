"""
Temporary dev-only read-only DB inspector. Password-protected via Step 1 cookie.
Uses tenant DB session. No shell, no writes. Will be removed later.
"""
import re
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.tools.dev_tools_auth import require_tools_unlocked
from app.deps.tenant_db import get_tenant_db_for_tools

TABLE_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]*$")

router = APIRouter(prefix="/api/v1/tools/db", tags=["Dev Tools DB"])


def _validate_table(table: str) -> None:
    if not table or not TABLE_NAME_RE.match(table):
        raise HTTPException(status_code=400, detail="Invalid table name")


@router.get("/describe")
async def describe_table(
    request: Request,
    table: str = "drivers",
    db: AsyncSession = Depends(get_tenant_db_for_tools),
):
    require_tools_unlocked(request)
    _validate_table(table)
    result = await db.execute(
        text("""
            SELECT
              column_name,
              data_type,
              is_nullable,
              column_default
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table
            ORDER BY ordinal_position
        """),
        {"table": table},
    )
    rows = result.mappings().all()
    columns = [
        {
            "name": r["column_name"],
            "type": r["data_type"],
            "nullable": r["is_nullable"] == "YES",
            "default": r["column_default"],
        }
        for r in rows
    ]
    return {"ok": True, "table": table, "columns": columns}


@router.get("/count")
async def count_table(
    request: Request,
    table: str = "drivers",
    db: AsyncSession = Depends(get_tenant_db_for_tools),
):
    require_tools_unlocked(request)
    _validate_table(table)
    # Table name validated by regex ^[a-z_][a-z0-9_]*$ — safe to use as identifier
    result = await db.execute(text(f"SELECT COUNT(*) AS count FROM public.{table}"))
    row = result.mappings().first()
    count = row["count"] if row else 0
    return {"ok": True, "table": table, "count": count}


@router.get("/tables")
async def list_tables(
    request: Request,
    db: AsyncSession = Depends(get_tenant_db_for_tools),
):
    require_tools_unlocked(request)
    result = await db.execute(
        text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """)
    )
    rows = result.mappings().all()
    tables = [r["table_name"] for r in rows]
    return {"ok": True, "tables": tables}


def _row_to_json_safe(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if v is None or isinstance(v, (bool, int, float, str)):
            out[k] = v
        elif hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        else:
            out[k] = str(v)
    return out


@router.get("/sample")
async def sample_table(
    request: Request,
    table: str = "drivers",
    limit: int = 10,
    db: AsyncSession = Depends(get_tenant_db_for_tools),
):
    require_tools_unlocked(request)
    _validate_table(table)
    limit = max(1, min(25, limit))
    # Check table exists
    check = await db.execute(
        text("""
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = :table
        """),
        {"table": table},
    )
    if not check.mappings().first():
        raise HTTPException(status_code=404, detail="TABLE_NOT_FOUND")
    # limit already clamped 1–25; use literal to avoid driver LIMIT binding issues
    result = await db.execute(text(f"SELECT * FROM public.{table} LIMIT {limit}"))
    rows = result.mappings().all()
    json_rows = [_row_to_json_safe(dict(r)) for r in rows]
    return {"ok": True, "table": table, "rows": json_rows}
