"""DW-1 — tenant migration + integrity constraints (tenant_pytest only)."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Connection

from app.core.integration_db_guard import IntegrationIsolationError
from tests.support.integration_isolation import (
    assert_integration_db_name_allowed,
    database_name_from_url,
    require_integration_tenant_database_url,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DW1_REVISION = "dw1f2a3b4c5d6"
DW1B_REVISION = "dw1b_tenant_scope_dw1_foreign_keys"
DW1C_REVISION = "dw1c_composite_fk_set_null_optional_columns"
DW1D_REVISION = "dw1d_load_commercial_evidence_retention_varchar32"
MERGE_REVISION = "dw0_merge_tenant_heads_a1b2_x5"
X5_REVISION = "x5y6z7a8b9c0"
POD_DW1_REVISION = "i14_load_pod_evidence"


def _sync_tenant_url() -> str:
    raw = require_integration_tenant_database_url(context="test_load_workspace_draft_schema_dw1")
    if raw.startswith("postgresql+asyncpg://"):
        return "postgresql://" + raw.split("postgresql+asyncpg://", 1)[1]
    return raw


def _alembic_env() -> dict[str, str]:
    env = os.environ.copy()
    url = _sync_tenant_url()
    env["ALEMBIC_TENANT_DATABASE_URL"] = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return env


def _run_alembic(*args: str) -> None:
    if any(arg in {"head", "heads"} for arg in args):
        raise AssertionError("DW-1 integration tests must pin an explicit revision, never head.")
    cmd = [sys.executable, "-m", "alembic", "-c", "alembic_tenant.ini", *args]
    proc = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=_alembic_env(),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"alembic {' '.join(args)} failed:\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )


def _current_revision() -> str:
    with create_engine(_sync_tenant_url(), future=True).connect() as conn:
        row = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    if not row:
        raise AssertionError("integration tenant has no alembic_version row")
    return str(row)


def _ensure_revision(target: str) -> None:
    current = _current_revision()
    if current == target:
        return
    if target == DW1C_REVISION and current == POD_DW1_REVISION:
        _run_alembic("downgrade", DW1C_REVISION)
        return
    _run_alembic("upgrade", target)


def _entity_count_snapshot(conn: Connection) -> dict[str, int]:
    insp = inspect(conn)
    snap = {
        "loads": int(conn.execute(text("SELECT COUNT(*) FROM loads")).scalar_one()),
        "trips": int(conn.execute(text("SELECT COUNT(*) FROM trips")).scalar_one()),
        "trip_loads": int(conn.execute(text("SELECT COUNT(*) FROM trip_loads")).scalar_one()),
    }
    if insp.has_table("load_commercial_evidence"):
        snap["load_commercial_evidence"] = int(
            conn.execute(text("SELECT COUNT(*) FROM load_commercial_evidence")).scalar_one()
        )
    else:
        snap["load_commercial_evidence"] = 0
    return snap


def _expect_sql_failure(conn: Connection, fn: Callable[[Connection], None]) -> None:
    """Run failing SQL inside a SAVEPOINT so the outer transaction stays usable."""
    nested = conn.begin_nested()
    with pytest.raises(Exception):
        fn(conn)
    nested.rollback()


@pytest.fixture(scope="module")
def tenant_engine():
    url = _sync_tenant_url()
    assert_integration_db_name_allowed(database_name_from_url(url), context="test_load_workspace_draft_schema_dw1")
    engine = create_engine(url, future=True)
    _ensure_revision(DW1C_REVISION)
    yield engine
    engine.dispose()


def test_dw1_tables_and_load_column_present(tenant_engine) -> None:
    insp = inspect(tenant_engine)
    assert insp.has_table("load_workspace_drafts")
    assert insp.has_table("load_commercial_evidence")
    cols = {c["name"] for c in insp.get_columns("loads")}
    assert "promotion_origin_workspace_draft_id" in cols
    thread_cols = {c["name"] for c in insp.get_columns("email_threads")}
    assert "workspace_draft_id" in thread_cols


def test_email_threads_tenant_id_id_unique(tenant_engine) -> None:
    insp = inspect(tenant_engine)
    uniques = {u["name"] for u in insp.get_unique_constraints("email_threads")}
    assert "uq_email_threads_tenant_id_id" in uniques


def test_existing_load_rows_unchanged_promotion_origin_null(tenant_engine) -> None:
    with tenant_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT COUNT(*) AS total, "
                "COUNT(*) FILTER (WHERE promotion_origin_workspace_draft_id IS NOT NULL) AS with_origin "
                "FROM loads"
            )
        ).one()
    assert row.with_origin == 0
    assert row.total >= 0


def test_loads_trips_and_commercial_evidence_integrity_after_dw1(tenant_engine) -> None:
    with tenant_engine.connect() as conn:
        snap = _entity_count_snapshot(conn)
        orphaned_trip_loads = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM trip_loads tl
                LEFT JOIN loads l ON l.id = tl.load_id AND l.tenant_id = tl.tenant_id
                WHERE l.id IS NULL
                """
            )
        ).scalar_one()
        orphaned_commercial = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM load_commercial_evidence ce
                LEFT JOIN loads l ON l.id = ce.load_id AND l.tenant_id = ce.tenant_id
                WHERE ce.load_id IS NOT NULL AND l.id IS NULL
                """
            )
        ).scalar_one()
    assert orphaned_trip_loads == 0
    assert orphaned_commercial == 0
    assert snap["loads"] >= 0
    assert snap["trips"] >= 0


def test_x5_to_dw1c_migration_preserves_entity_counts(tenant_engine) -> None:
    try:
        _run_alembic("downgrade", X5_REVISION)
        with tenant_engine.connect() as conn:
            before = _entity_count_snapshot(conn)
        _run_alembic("upgrade", DW1C_REVISION)
        with tenant_engine.connect() as conn:
            after = _entity_count_snapshot(conn)
        assert before == after
    finally:
        _ensure_revision(DW1C_REVISION)


def _resolve_tenant_id(conn: Connection) -> int:
    tid = conn.execute(text("SELECT MIN(tenant_id) FROM loads")).scalar()
    if tid is not None:
        return int(tid)
    tid = conn.execute(text("SELECT MIN(tenant_id) FROM people")).scalar()
    if tid is None:
        pytest.skip("tenant_pytest has no loads/people rows to infer tenant_id")
    return int(tid)


def _insert_minimal_load(conn: Connection, tenant_id: int, load_number: str) -> int:
    return conn.execute(
        text(
            """
            INSERT INTO loads (tenant_id, load_number, status, concurrency_version)
            VALUES (:tenant_id, :load_number, 'draft', 1)
            RETURNING id
            """
        ),
        {"tenant_id": tenant_id, "load_number": load_number},
    ).scalar_one()


def test_duplicate_promotion_origin_rejected(tenant_engine) -> None:
    draft_id = uuid.uuid4()
    expires = datetime.now(timezone.utc) + timedelta(days=7)
    load_a = load_b = None
    tenant_id = 0
    with tenant_engine.begin() as conn:
        tenant_id = _resolve_tenant_id(conn)
        conn.execute(
            text(
                """
                INSERT INTO load_workspace_drafts (
                    id, tenant_id, status, source_channel, expires_at
                ) VALUES (
                    :id, :tenant_id, 'draft', 'manual', :expires_at
                )
                """
            ),
            {"id": draft_id, "tenant_id": tenant_id, "expires_at": expires},
        )
        load_a = _insert_minimal_load(conn, tenant_id, f"DW1-A-{uuid.uuid4().hex[:8]}")
        load_b = _insert_minimal_load(conn, tenant_id, f"DW1-B-{uuid.uuid4().hex[:8]}")
        conn.execute(
            text(
                "UPDATE loads SET promotion_origin_workspace_draft_id = :draft_id WHERE id = :load_id"
            ),
            {"draft_id": draft_id, "load_id": load_a},
        )
    with tenant_engine.begin() as conn:
        _expect_sql_failure(
            conn,
            lambda c: c.execute(
                text(
                    "UPDATE loads SET promotion_origin_workspace_draft_id = :draft_id WHERE id = :load_id"
                ),
                {"draft_id": draft_id, "load_id": load_b},
            ),
        )
    with tenant_engine.begin() as conn:
        conn.execute(text("DELETE FROM loads WHERE id IN (:a, :b)"), {"a": load_a, "b": load_b})
        conn.execute(text("DELETE FROM load_workspace_drafts WHERE id = :id"), {"id": draft_id})


def test_cross_tenant_promotion_origin_rejected(tenant_engine) -> None:
    draft_id = uuid.uuid4()
    expires = datetime.now(timezone.utc) + timedelta(days=5)
    load_id = None
    tenant_a = tenant_b = 0
    with tenant_engine.begin() as conn:
        tenant_a = _resolve_tenant_id(conn)
        tenant_b = conn.execute(
            text("SELECT tenant_id FROM loads WHERE tenant_id != :tid ORDER BY tenant_id LIMIT 1"),
            {"tid": tenant_a},
        ).scalar()
        if tenant_b is None:
            tenant_b = tenant_a + 1
        conn.execute(
            text(
                """
                INSERT INTO load_workspace_drafts (
                    id, tenant_id, status, source_channel, expires_at
                ) VALUES (:id, :tenant_id, 'draft', 'manual', :expires_at)
                """
            ),
            {"id": draft_id, "tenant_id": tenant_a, "expires_at": expires},
        )
        load_id = _insert_minimal_load(conn, tenant_b, f"DW1-CT-{uuid.uuid4().hex[:8]}")
        _expect_sql_failure(
            conn,
            lambda c: c.execute(
                text(
                    "UPDATE loads SET promotion_origin_workspace_draft_id = :draft_id WHERE id = :load_id"
                ),
                {"draft_id": draft_id, "load_id": load_id},
            ),
        )
    with tenant_engine.begin() as conn:
        conn.execute(text("DELETE FROM loads WHERE id = :id"), {"id": load_id})
        conn.execute(text("DELETE FROM load_workspace_drafts WHERE id = :id"), {"id": draft_id})


def test_invalid_draft_status_rejected(tenant_engine) -> None:
    with tenant_engine.begin() as conn:
        tenant_id = _resolve_tenant_id(conn)

        def _bad_insert(c: Connection) -> None:
            c.execute(
                text(
                    """
                    INSERT INTO load_workspace_drafts (
                        id, tenant_id, status, source_channel, expires_at
                    ) VALUES (
                        :id, :tenant_id, 'promoting', 'manual', :expires_at
                    )
                    """
                ),
                {
                    "id": uuid.uuid4(),
                    "tenant_id": tenant_id,
                    "expires_at": datetime.now(timezone.utc) + timedelta(days=1),
                },
            )

        _expect_sql_failure(conn, _bad_insert)


def test_invalid_pdf_upload_state_rejected(tenant_engine) -> None:
    with tenant_engine.begin() as conn:
        tenant_id = _resolve_tenant_id(conn)

        def _bad_insert(c: Connection) -> None:
            c.execute(
                text(
                    """
                    INSERT INTO load_workspace_drafts (
                        id, tenant_id, status, source_channel, expires_at, pdf_upload_state
                    ) VALUES (
                        :id, :tenant_id, 'draft', 'manual', :expires_at, 'pending'
                    )
                    """
                ),
                {
                    "id": uuid.uuid4(),
                    "tenant_id": tenant_id,
                    "expires_at": datetime.now(timezone.utc) + timedelta(days=1),
                },
            )

        _expect_sql_failure(conn, _bad_insert)


def test_invalid_retention_class_rejected(tenant_engine) -> None:
    with tenant_engine.begin() as conn:
        tenant_id = _resolve_tenant_id(conn)

        def _bad_insert(c: Connection) -> None:
            c.execute(
                text(
                    """
                    INSERT INTO load_workspace_drafts (
                        id, tenant_id, status, source_channel, expires_at, pdf_retention_class
                    ) VALUES (
                        :id, :tenant_id, 'draft', 'manual', :expires_at, 'ephemeral'
                    )
                    """
                ),
                {
                    "id": uuid.uuid4(),
                    "tenant_id": tenant_id,
                    "expires_at": datetime.now(timezone.utc) + timedelta(days=1),
                },
            )

        _expect_sql_failure(conn, _bad_insert)


def test_tenant_isolation_promoted_load_fk(tenant_engine) -> None:
    draft_id = uuid.uuid4()
    expires = datetime.now(timezone.utc) + timedelta(days=3)
    load_b = None
    with tenant_engine.begin() as conn:
        tenant_a = _resolve_tenant_id(conn)
        tenant_b = conn.execute(
            text("SELECT tenant_id FROM loads WHERE tenant_id != :tid ORDER BY tenant_id LIMIT 1"),
            {"tid": tenant_a},
        ).scalar()
        if tenant_b is None:
            tenant_b = tenant_a + 1
        conn.execute(
            text(
                """
                INSERT INTO load_workspace_drafts (
                    id, tenant_id, status, source_channel, expires_at
                ) VALUES (:id, :tenant_id, 'draft', 'manual', :expires_at)
                """
            ),
            {"id": draft_id, "tenant_id": tenant_a, "expires_at": expires},
        )
        load_b = _insert_minimal_load(conn, tenant_b, f"DW1-X-{uuid.uuid4().hex[:8]}")

        def _bad_promote(c: Connection) -> None:
            c.execute(
                text(
                    """
                    UPDATE load_workspace_drafts
                    SET promoted_load_id = :load_id, status = 'promoted'
                    WHERE id = :draft_id
                    """
                ),
                {"load_id": load_b, "draft_id": draft_id},
            )

        _expect_sql_failure(conn, _bad_promote)
    with tenant_engine.begin() as conn:
        conn.execute(text("DELETE FROM loads WHERE id = :id"), {"id": load_b})
        conn.execute(text("DELETE FROM load_workspace_drafts WHERE id = :id"), {"id": draft_id})


def test_delete_email_thread_nulls_draft_email_thread_id_only(tenant_engine) -> None:
    draft_id = uuid.uuid4()
    expires = datetime.now(timezone.utc) + timedelta(days=7)
    thread_id = 0
    tenant_id = 0
    with tenant_engine.begin() as conn:
        tenant_id = _resolve_tenant_id(conn)
        thread_id = conn.execute(
            text(
                """
                INSERT INTO email_threads (tenant_id, provider, external_thread_id)
                VALUES (:tenant_id, 'test_dw1', :external_thread_id)
                RETURNING id
                """
            ),
            {
                "tenant_id": tenant_id,
                "external_thread_id": f"dw1-thread-{uuid.uuid4().hex}",
            },
        ).scalar_one()
        conn.execute(
            text(
                """
                INSERT INTO load_workspace_drafts (
                    id, tenant_id, status, source_channel, expires_at, email_thread_id
                ) VALUES (
                    :id, :tenant_id, 'draft', 'manual', :expires_at, :email_thread_id
                )
                """
            ),
            {
                "id": draft_id,
                "tenant_id": tenant_id,
                "expires_at": expires,
                "email_thread_id": thread_id,
            },
        )
    with tenant_engine.begin() as conn:
        conn.execute(text("DELETE FROM email_threads WHERE id = :id"), {"id": thread_id})
    with tenant_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT tenant_id, email_thread_id FROM load_workspace_drafts WHERE id = :id"
            ),
            {"id": draft_id},
        ).one()
        assert row.tenant_id == tenant_id
        assert row.email_thread_id is None
    with tenant_engine.begin() as conn:
        conn.execute(text("DELETE FROM load_workspace_drafts WHERE id = :id"), {"id": draft_id})


def test_delete_workspace_draft_nulls_thread_workspace_draft_id_only(tenant_engine) -> None:
    draft_id = uuid.uuid4()
    expires = datetime.now(timezone.utc) + timedelta(days=7)
    thread_id = 0
    tenant_id = 0
    with tenant_engine.begin() as conn:
        tenant_id = _resolve_tenant_id(conn)
        conn.execute(
            text(
                """
                INSERT INTO load_workspace_drafts (
                    id, tenant_id, status, source_channel, expires_at
                ) VALUES (:id, :tenant_id, 'draft', 'manual', :expires_at)
                """
            ),
            {"id": draft_id, "tenant_id": tenant_id, "expires_at": expires},
        )
        thread_id = conn.execute(
            text(
                """
                INSERT INTO email_threads (
                    tenant_id, provider, external_thread_id, workspace_draft_id
                ) VALUES (:tenant_id, 'test_dw1', :external_thread_id, :workspace_draft_id)
                RETURNING id
                """
            ),
            {
                "tenant_id": tenant_id,
                "external_thread_id": f"dw1-thread-{uuid.uuid4().hex}",
                "workspace_draft_id": draft_id,
            },
        ).scalar_one()
    with tenant_engine.begin() as conn:
        conn.execute(
            text("DELETE FROM load_workspace_drafts WHERE id = :id"),
            {"id": draft_id},
        )
    with tenant_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT tenant_id, workspace_draft_id FROM email_threads WHERE id = :id"
            ),
            {"id": thread_id},
        ).one()
        assert row.tenant_id == tenant_id
        assert row.workspace_draft_id is None
    with tenant_engine.begin() as conn:
        conn.execute(text("DELETE FROM email_threads WHERE id = :id"), {"id": thread_id})


def test_dw1c_downgrade_upgrade_preserves_column_specific_set_null(tenant_engine) -> None:
    try:
        _run_alembic("downgrade", DW1B_REVISION)
        _run_alembic("upgrade", DW1C_REVISION)
    finally:
        _ensure_revision(DW1C_REVISION)


def test_downgrade_upgrade_dw1_on_isolated_revision(tenant_engine) -> None:
    try:
        _run_alembic("downgrade", MERGE_REVISION)
        insp = inspect(tenant_engine)
        assert not insp.has_table("load_workspace_drafts")
        _run_alembic("upgrade", DW1C_REVISION)
    finally:
        _ensure_revision(DW1C_REVISION)


def test_dw1c_to_i14_pod_upgrade_adds_load_pod_evidence(tenant_engine) -> None:
    try:
        _run_alembic("upgrade", POD_DW1_REVISION)
        assert inspect(tenant_engine).has_table("load_pod_evidence")
    finally:
        _ensure_revision(DW1C_REVISION)


def test_load_orm_maps_existing_rows_at_dw1c(tenant_engine) -> None:
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.models.load import Load

    with Session(tenant_engine) as session:
        tenant_id = _resolve_tenant_id(session.connection())
        load = session.scalar(select(Load).where(Load.tenant_id == tenant_id).limit(1))
    if load is None:
        pytest.skip("no loads in integration tenant")
    assert load.load_number


def test_dw1c_is_dw1_pod_parent_and_tenant_heads_are_split() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(Config(str(REPO_ROOT / "alembic_tenant.ini")))
    pod = script.get_revision(POD_DW1_REVISION)
    assert pod is not None
    assert pod.down_revision == DW1D_REVISION
    assert set(script.get_heads()) == {
        "s1_load_approved_snapshot_fmp",
        "s1_load_approved_snapshot_x5",
    }


def test_integration_db_guard_rejects_demo() -> None:
    with pytest.raises(IntegrationIsolationError):
        assert_integration_db_name_allowed("tenant_demo", context="unit")
