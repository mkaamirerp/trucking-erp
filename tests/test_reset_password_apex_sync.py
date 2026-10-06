"""Apex vs workspace password reset: platform/tenant sync without partial credential commits."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services.tenant_auth_dual_write import (
    apply_apex_password_reset_sync_mapped_tenants,
    apply_password_and_session_version_platform_primary,
    apply_password_and_session_version_tenant_primary,
    tenant_auth_maps_for_platform_user,
)


class CredRow:
    def __init__(
        self,
        *,
        id="user-1",
        password_hash="old-hash",
        session_version=5,
        password_reset_token_hash="reset-hash",
        password_reset_expires_at="exp",
    ):
        self.id = id
        self.password_hash = password_hash
        self.session_version = session_version
        self.password_reset_token_hash = password_reset_token_hash
        self.password_reset_expires_at = password_reset_expires_at


def _snap(row: CredRow) -> dict:
    return {
        "password_hash": row.password_hash,
        "session_version": row.session_version,
        "password_reset_token_hash": row.password_reset_token_hash,
        "password_reset_expires_at": row.password_reset_expires_at,
    }


def _restore(row: CredRow, snap: dict) -> None:
    row.password_hash = snap["password_hash"]
    row.session_version = snap["session_version"]
    row.password_reset_token_hash = snap["password_reset_token_hash"]
    row.password_reset_expires_at = snap["password_reset_expires_at"]


class FakeTenantDb:
    def __init__(
        self,
        tu: CredRow | None,
        *,
        fail_commit: bool = False,
        fail_flush: bool = False,
        fail_on_commit_number: int | None = None,
        fail_commit_message: str = "tenant commit failed",
    ):
        self.tu = tu
        self.fail_commit = fail_commit
        self.fail_flush = fail_flush
        self.fail_on_commit_number = fail_on_commit_number
        self.fail_commit_message = fail_commit_message
        self.last_committed = _snap(tu) if tu is not None else None
        self.commit_count = 0
        self.rollback_count = 0
        self.committed_history: list[dict] = []

    async def scalar(self, stmt):  # noqa: ARG002
        return self.tu

    async def flush(self):
        if self.fail_flush:
            raise RuntimeError("tenant flush failed")

    async def commit(self):
        next_n = self.commit_count + 1
        if self.fail_commit or (
            self.fail_on_commit_number is not None and next_n == self.fail_on_commit_number
        ):
            raise RuntimeError(self.fail_commit_message)
        if self.tu is not None:
            self.last_committed = _snap(self.tu)
            self.committed_history.append(dict(self.last_committed))
        self.commit_count += 1

    async def rollback(self):
        self.rollback_count += 1
        if self.tu is not None and self.last_committed is not None:
            _restore(self.tu, self.last_committed)


class FakePlatformDb:
    """Platform session that keeps committed credential state separate from in-memory mutation."""

    def __init__(
        self,
        maps: list[tuple[int, int, str]],
        platform_user: CredRow,
        *,
        fail_commit: bool = False,
    ):
        inner = _platform_db_for_maps(maps)
        self.execute = inner.execute
        self.get = inner.get
        self.refresh = AsyncMock()
        self.user = platform_user
        self.fail_commit = fail_commit
        self.last_committed = _snap(platform_user)
        self.commit_count = 0
        self.rollback_count = 0
        self.committed_history: list[dict] = []

    async def commit(self):
        if self.fail_commit:
            raise RuntimeError("platform commit failed")
        self.last_committed = _snap(self.user)
        self.committed_history.append(dict(self.last_committed))
        self.commit_count += 1

    async def rollback(self):
        self.rollback_count += 1
        _restore(self.user, self.last_committed)


def _platform_db_for_maps(maps: list[tuple[int, int, str]]):
    """maps: (tenant_id, tenant_user_id, tenant_auth_mode)."""
    rows = []
    modes = {}
    for tid, tuid, mode in maps:
        m = MagicMock()
        m.tenant_id = tid
        m.tenant_user_id = tuid
        rows.append(m)
        modes[tid] = SimpleNamespace(tenant_auth_mode=mode)
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    platform_db = MagicMock()
    platform_db.execute = AsyncMock(return_value=result)
    platform_db.get = AsyncMock(side_effect=lambda _model, key: modes[int(key)])
    platform_db.commit = AsyncMock()
    platform_db.refresh = AsyncMock()
    platform_db.rollback = AsyncMock()
    return platform_db


def _open_fn(
    dbs: dict[int, FakeTenantDb],
    *,
    fail_connect_for: int | None = None,
    closed: list[int] | None = None,
):
    async def fake_open(tenant_id: int):
        if fail_connect_for is not None and int(tenant_id) == int(fail_connect_for):
            raise RuntimeError("tenant db connection failed")
        try:
            yield dbs[int(tenant_id)]
        finally:
            if closed is not None:
                closed.append(int(tenant_id))

    return fake_open


@pytest.mark.asyncio
async def test_platform_auth_workspace_reset_does_not_mirror_to_tenant():
    platform_user = CredRow(session_version=3)
    platform_db = MagicMock()
    platform_db.commit = AsyncMock()
    platform_db.refresh = AsyncMock()
    tenant_db = MagicMock()
    tenant_db.scalar = AsyncMock()
    tenant_db.commit = AsyncMock()

    await apply_password_and_session_version_platform_primary(
        platform_db=platform_db,
        tenant_db=tenant_db,
        tenant_id=11,
        platform_user=platform_user,
        tenant_auth_mode="platform",
        new_password_plain="newpassword12",
        bump_session=True,
    )
    assert platform_user.session_version == 4
    assert platform_user.password_reset_token_hash is None
    tenant_db.scalar.assert_not_awaited()
    tenant_db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_tenant_auth_workspace_reset_mirrors_session_version():
    tu = CredRow(id=42, session_version=2, password_hash="old")
    tenant_db = MagicMock()
    tenant_db.commit = AsyncMock()
    tenant_db.refresh = AsyncMock()
    platform_db = MagicMock()
    pmap = MagicMock()
    pmap.platform_user_id = "user-1"
    platform_db.scalar = AsyncMock(return_value=pmap)
    puser = CredRow(session_version=2)
    platform_db.get = AsyncMock(return_value=puser)
    platform_db.commit = AsyncMock()

    await apply_password_and_session_version_tenant_primary(
        platform_db=platform_db,
        tenant_db=tenant_db,
        tenant_id=7,
        tenant_user=tu,
        new_password_plain="newpassword12",
        bump_session=True,
    )
    assert tu.session_version == 3
    assert puser.session_version == 3
    assert tu.password_hash == puser.password_hash


@pytest.mark.asyncio
async def test_apex_reset_all_tenant_db_updates_succeed():
    platform_user = CredRow(session_version=5)
    platform_before = _snap(platform_user)
    platform_db = _platform_db_for_maps([(10, 101, "tenant"), (20, 202, "tenant"), (30, 303, "platform")])
    tu_a = CredRow(id=101, password_hash="old-a", session_version=1)
    tu_b = CredRow(id=202, password_hash="old-b", session_version=1)
    dbs = {10: FakeTenantDb(tu_a), 20: FakeTenantDb(tu_b)}
    closed: list[int] = []

    with patch("app.services.tenant_auth_dual_write.hash_password", return_value="new-hash"):
        mirrored = await apply_apex_password_reset_sync_mapped_tenants(
            platform_db=platform_db,
            platform_user=platform_user,
            new_password_plain="newpassword12",
            open_tenant_session=_open_fn(dbs, closed=closed),
        )

    assert mirrored == [10, 20]
    assert platform_user.password_hash == "new-hash"
    assert platform_user.session_version == 6
    assert platform_user.password_reset_token_hash is None
    assert tu_a.password_hash == "new-hash"
    assert tu_b.password_hash == "new-hash"
    assert tu_a.session_version == tu_b.session_version == 6
    assert dbs[10].last_committed["password_hash"] == "new-hash"
    assert dbs[20].last_committed["password_hash"] == "new-hash"
    platform_db.commit.assert_awaited()
    assert platform_before["password_reset_token_hash"] == "reset-hash"
    assert closed == [10, 20]


@pytest.mark.asyncio
async def test_apex_reset_first_tenant_db_fails_leaves_platform_token_usable():
    platform_user = CredRow(session_version=5)
    platform_db = _platform_db_for_maps([(10, 101, "tenant"), (20, 202, "tenant")])
    tu_b = CredRow(id=202, password_hash="old-b")
    dbs = {20: FakeTenantDb(tu_b)}

    with patch("app.services.tenant_auth_dual_write.hash_password", return_value="new-hash"):
        with pytest.raises(RuntimeError, match="tenant db connection failed"):
            await apply_apex_password_reset_sync_mapped_tenants(
                platform_db=platform_db,
                platform_user=platform_user,
                new_password_plain="newpassword12",
                open_tenant_session=_open_fn(dbs, fail_connect_for=10),
            )

    assert platform_user.password_hash == "old-hash"
    assert platform_user.session_version == 5
    assert platform_user.password_reset_token_hash == "reset-hash"
    assert tu_b.password_hash == "old-b"
    platform_db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_apex_reset_tenant_a_commits_tenant_b_fails_compensates_a():
    platform_user = CredRow(session_version=5)
    platform_db = _platform_db_for_maps([(10, 101, "tenant"), (20, 202, "tenant")])
    tu_a = CredRow(id=101, password_hash="old-a", session_version=2)
    tu_b = CredRow(id=202, password_hash="old-b", session_version=2)
    dbs = {10: FakeTenantDb(tu_a), 20: FakeTenantDb(tu_b, fail_commit=True)}
    closed: list[int] = []

    with patch("app.services.tenant_auth_dual_write.hash_password", return_value="new-hash"):
        with pytest.raises(RuntimeError, match="tenant commit failed"):
            await apply_apex_password_reset_sync_mapped_tenants(
                platform_db=platform_db,
                platform_user=platform_user,
                new_password_plain="newpassword12",
                open_tenant_session=_open_fn(dbs, closed=closed),
            )

    assert platform_user.password_hash == "old-hash"
    assert platform_user.session_version == 5
    assert platform_user.password_reset_token_hash == "reset-hash"
    assert tu_a.password_hash == "old-a"
    assert tu_a.session_version == 2
    assert tu_b.password_hash == "old-b"
    assert dbs[10].last_committed["password_hash"] == "old-a"
    assert dbs[20].last_committed["password_hash"] == "old-b"
    platform_db.commit.assert_not_awaited()
    assert closed == [10, 20]


@pytest.mark.asyncio
async def test_apex_reset_missing_mapped_tenant_user_does_not_commit_platform():
    platform_user = CredRow()
    platform_db = _platform_db_for_maps([(10, 101, "tenant")])
    dbs = {10: FakeTenantDb(None)}

    with patch("app.services.tenant_auth_dual_write.hash_password", return_value="new-hash"):
        with pytest.raises(RuntimeError, match="dual_write_missing_tenant_user"):
            await apply_apex_password_reset_sync_mapped_tenants(
                platform_db=platform_db,
                platform_user=platform_user,
                new_password_plain="newpassword12",
                open_tenant_session=_open_fn(dbs),
            )

    assert platform_user.password_hash == "old-hash"
    assert platform_user.password_reset_token_hash == "reset-hash"
    platform_db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_apex_reset_failed_reset_token_remains_usable():
    platform_user = CredRow(password_reset_token_hash="still-valid")
    platform_db = _platform_db_for_maps([(10, 101, "tenant"), (20, 202, "tenant")])
    tu_a = CredRow(id=101, password_hash="old-a")
    tu_b = CredRow(id=202, password_hash="old-b")
    dbs = {10: FakeTenantDb(tu_a), 20: FakeTenantDb(tu_b, fail_commit=True)}

    with patch("app.services.tenant_auth_dual_write.hash_password", return_value="new-hash"):
        with pytest.raises(RuntimeError):
            await apply_apex_password_reset_sync_mapped_tenants(
                platform_db=platform_db,
                platform_user=platform_user,
                new_password_plain="newpassword12",
                open_tenant_session=_open_fn(dbs),
            )

    assert platform_user.password_reset_token_hash == "still-valid"
    assert platform_user.password_reset_expires_at == "exp"


@pytest.mark.asyncio
async def test_apex_reset_platform_commit_fails_after_tenant_commits_compensates_both():
    platform_user = CredRow(
        password_hash="old-hash",
        session_version=5,
        password_reset_token_hash="reset-hash",
        password_reset_expires_at="exp-platform",
    )
    platform_before = _snap(platform_user)
    maps = [(10, 101, "tenant"), (20, 202, "tenant")]
    platform_db = FakePlatformDb(maps, platform_user, fail_commit=True)
    old_a = dict(
        password_hash="old-a",
        session_version=2,
        password_reset_token_hash="tok-a",
        password_reset_expires_at="exp-a",
    )
    old_b = dict(
        password_hash="old-b",
        session_version=3,
        password_reset_token_hash="tok-b",
        password_reset_expires_at="exp-b",
    )
    tu_a = CredRow(id=101, **old_a)
    tu_b = CredRow(id=202, **old_b)
    dbs = {10: FakeTenantDb(tu_a), 20: FakeTenantDb(tu_b)}
    closed: list[int] = []

    with patch("app.services.tenant_auth_dual_write.hash_password", return_value="new-hash"):
        with pytest.raises(RuntimeError, match="platform commit failed"):
            await apply_apex_password_reset_sync_mapped_tenants(
                platform_db=platform_db,
                platform_user=platform_user,
                new_password_plain="newpassword12",
                open_tenant_session=_open_fn(dbs, closed=closed),
            )

    assert platform_db.commit_count == 0
    assert platform_db.rollback_count == 1
    assert platform_db.last_committed == platform_before
    assert _snap(platform_user) == platform_before
    assert platform_user.password_reset_token_hash == "reset-hash"

    assert _snap(tu_a) == old_a
    assert _snap(tu_b) == old_b
    assert dbs[10].last_committed == old_a
    assert dbs[20].last_committed == old_b
    assert dbs[10].commit_count == 2
    assert dbs[20].commit_count == 2
    assert dbs[10].committed_history[0]["password_hash"] == "new-hash"
    assert dbs[20].committed_history[0]["password_hash"] == "new-hash"
    assert dbs[10].committed_history[-1] == old_a
    assert dbs[20].committed_history[-1] == old_b
    assert closed == [10, 20]


@pytest.mark.asyncio
async def test_apex_reset_compensate_failure_leaves_tenant_a_drifted():
    """Residual risk: Tenant A committed new creds; B fails; A compensate commit also fails."""
    platform_user = CredRow(
        password_hash="old-hash",
        session_version=5,
        password_reset_token_hash="still-valid",
        password_reset_expires_at="exp",
    )
    platform_before = _snap(platform_user)
    platform_db = FakePlatformDb(
        [(10, 101, "tenant"), (20, 202, "tenant")],
        platform_user,
        fail_commit=False,
    )
    old_a = dict(
        password_hash="old-a",
        session_version=2,
        password_reset_token_hash="tok-a",
        password_reset_expires_at="exp-a",
    )
    tu_a = CredRow(id=101, **old_a)
    tu_b = CredRow(id=202, password_hash="old-b", session_version=2)
    dbs = {
        10: FakeTenantDb(
            tu_a,
            fail_on_commit_number=2,
            fail_commit_message="tenant compensate commit failed",
        ),
        20: FakeTenantDb(tu_b, fail_commit=True),
    }
    closed: list[int] = []

    with patch("app.services.tenant_auth_dual_write.hash_password", return_value="new-hash"):
        with pytest.raises(RuntimeError, match=r"apex_reset_compensate_failed.*10") as exc:
            await apply_apex_password_reset_sync_mapped_tenants(
                platform_db=platform_db,
                platform_user=platform_user,
                new_password_plain="newpassword12",
                open_tenant_session=_open_fn(dbs, closed=closed),
            )

    assert "apex_reset_compensate_failed" in str(exc.value)
    assert "10" in str(exc.value)
    assert platform_db.commit_count == 0
    assert platform_db.last_committed == platform_before
    assert _snap(platform_user) == platform_before
    assert platform_user.password_reset_token_hash == "still-valid"

    # In-memory restore ran before the failed compensate commit; committed DB did not.
    assert dbs[10].commit_count == 1
    assert dbs[10].committed_history == [
        {
            "password_hash": "new-hash",
            "session_version": 6,
            "password_reset_token_hash": None,
            "password_reset_expires_at": None,
        }
    ]
    assert dbs[10].last_committed["password_hash"] == "new-hash"
    assert dbs[10].last_committed["session_version"] == 6
    assert dbs[10].last_committed != old_a
    assert _snap(tu_a) == old_a  # in-memory restored; committed tenant DB still new
    assert tu_b.password_hash == "old-b"
    assert dbs[20].last_committed["password_hash"] == "old-b"
    assert closed == [10, 20]


@pytest.mark.asyncio
async def test_apex_reset_failure_does_not_leave_mixed_tenant_credentials():
    platform_user = CredRow()
    platform_db = _platform_db_for_maps([(10, 101, "tenant"), (20, 202, "tenant")])
    tu_a = CredRow(id=101, password_hash="old-a")
    tu_b = CredRow(id=202, password_hash="old-b")
    dbs = {10: FakeTenantDb(tu_a, fail_flush=True), 20: FakeTenantDb(tu_b)}

    with patch("app.services.tenant_auth_dual_write.hash_password", return_value="new-hash"):
        with pytest.raises(RuntimeError, match="tenant flush failed"):
            await apply_apex_password_reset_sync_mapped_tenants(
                platform_db=platform_db,
                platform_user=platform_user,
                new_password_plain="newpassword12",
                open_tenant_session=_open_fn(dbs),
            )

    hashes = {tu_a.password_hash, tu_b.password_hash}
    assert hashes == {"old-a", "old-b"}
    assert tu_a.password_hash != "new-hash"
    assert tu_b.password_hash != "new-hash"
    assert platform_user.password_hash == "old-hash"
    platform_db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_multi_workspace_maps_are_ordered_not_arbitrary():
    platform_db = MagicMock()
    late = MagicMock()
    late.tenant_id = 50
    late.tenant_user_id = 2
    early = MagicMock()
    early.tenant_id = 40
    early.tenant_user_id = 1
    result = MagicMock()
    result.scalars.return_value.all.return_value = [early, late]
    platform_db.execute = AsyncMock(return_value=result)
    platform_db.get = AsyncMock(return_value=SimpleNamespace(tenant_auth_mode="tenant"))
    targets = await tenant_auth_maps_for_platform_user(platform_db, "user-1")
    assert targets == [(40, 1), (50, 2)]


@pytest.mark.asyncio
async def test_reset_password_invalid_token_is_400():
    from fastapi import Request

    from app.routers.auth import ResetPasswordRequest, reset_password

    payload = ResetPasswordRequest(token="missing", new_password="newpassword12")
    request = MagicMock(spec=Request)
    request.state = SimpleNamespace(tenant_id=None)
    db = MagicMock()
    db.scalar = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc:
        await reset_password(payload, request, db)
    assert exc.value.status_code == 400
    assert "expired" in str(exc.value.detail).lower() or "invalid" in str(exc.value.detail).lower()
