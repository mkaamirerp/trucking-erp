"""Regression: forbid removed duplicate URL helpers; provisioning must use app.core.db_url."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
# Avoid spelling deprecated names as single literals (CI rg guard scans sources).
BANNED_SUBSTRINGS = (
    "_ensure" + "_asyncpg_url",
    "ensure" + "_asyncpg_url",
)


def _iter_scanned_files() -> list[Path]:
    out: list[Path] = []
    for sub in ("app", "scripts", "tests", ".github"):
        base = REPO_ROOT / sub
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if "__pycache__" in path.parts:
                continue
            if not path.is_file():
                continue
            if path.suffix in {".py", ".sh", ".yml", ".yaml"}:
                out.append(path)
    return sorted(out)


@pytest.mark.parametrize("banned", BANNED_SUBSTRINGS)
def test_repo_sources_exclude_deprecated_asyncpg_url_helpers(banned: str) -> None:
    hits: list[str] = []
    for path in _iter_scanned_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        if banned in text:
            hits.append(str(path.relative_to(REPO_ROOT)))
    assert not hits, f"{banned!r} found in: {hits}"


def test_tenant_provisioning_defines_provisioning_entrypoints() -> None:
    # Parse only: importing the module would require DATABASE_URL + asyncpg at import time.
    path = REPO_ROOT / "app/services/tenant_provisioning.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    async_defs = {n.name for n in tree.body if isinstance(n, ast.AsyncFunctionDef)}
    assert "provision_tenant_db" in async_defs
    assert "backfill_tenant_creator_person" in async_defs
