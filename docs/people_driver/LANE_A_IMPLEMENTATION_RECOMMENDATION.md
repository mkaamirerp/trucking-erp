# Lane A Implementation Recommendation — Permanent Cleanup

> **Document type:** Planning / design — **not** the canonical production operator runbook.  
> **Tenant migrations (operators):** use `scripts/tenant_upgrade_head.sh` in `truckerp-api` with `ALEMBIC_TENANT_DATABASE_URL` set (see `docs/secrets.md`, `.cursor/rules/tenant-migrations.mdc`).  
> Raw `alembic -c alembic_tenant.ini …` below is **lab / test DB / autogenerate** — not the default prod upgrade path.

**Scope:** `users`, `user_roles`, `driver_phones_old`  
**Excluded:** `employees_legacy_20260305`, `tenants`, `drivers`  
**Status:** Design complete — DO NOT EXECUTE until approved.

---

## Phase A1 — Exact Source Identification

### 1. users and user_roles (c8a3d0b9c777)

**Migration:** `alembic_tenant/versions/c8a3d0b9c777_add_tenants_and_rbac.py`

| Element | Location | Purpose |
|---------|----------|---------|
| `ensure_users_table()` | L357–411 | Creates `users` if missing; adds scope/tenant_id if present |
| `ensure_users_table()` call | L431 | Invoked during upgrade |
| `user_roles` creation | L557–585 | Creates `user_roles` if missing |
| `audit_log` creation | L586–619 | Creates `audit_log` with FK `actor_user_id` → `users.id` |
| Users backfill | L683–684 | `UPDATE users SET scope/tenant_id` |
| Super-admin backfill | L686–691 | Inserts into `user_roles` |
| Users check constraint | L690–696 | `ck_users_scope_tenant_match`, `alter_column` on scope |

**Dependencies:** `audit_log` has FK to `users`. Must drop that FK before dropping `users`.  
**Are these table creates still necessary?** No. Auth uses platform DB (`platform_users`). Tenant DB `users`/`user_roles` are legacy, not used by application.

### 2. Strategy Options

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **(a) History untouched** | Add one cleanup migration only; leave c8a3d0b9c777 as-is | Zero risk to history; standard practice; one file change | Fresh builds still create then drop; wasteful; two-step |
| **(b) Edit c8a3d0b9c777** | Stop creating users/user_roles in c8a3d0b9c777; add cleanup migration | Clean fresh builds; single logical outcome; dev-stage fix | Edit of historical migration; must update downgrade |

**Recommendation: Option (b) — Edit c8a3d0b9c777 + add cleanup migration**

Rationale: Dev-stage system; user preference for clean future builds; low risk because (1) no prod DBs yet, (2) cleanup migration remains idempotent for both fresh and upgraded DBs.

### 3. driver_phones_old (7de1d90c39eb)

**Migration:** `alembic_tenant/versions/7de1d90c39eb_add_driver_phones.py`

- Created by **rename** (`driver_phones` → `driver_phones_old`) when upgrading from a DB that already had `driver_phones`.
- On fresh build: `476789399da2` creates `driver_phones` before `7de1d90c39eb`, so `7de1d90c39eb` always renames it → `driver_phones_old` is created on fresh builds too.
- **No historical edit** — the rename preserves data during migration; dropping is handled by cleanup migration only.

**Conclusion:** Add cleanup migration only; do not edit `7de1d90c39eb`.

---

## Phase A2 — Recommended Permanent Implementation

### Approach: Edit c8a3d0b9c777 + New Cleanup Migration

| Action | When | Effect |
|--------|------|--------|
| Edit c8a3d0b9c777 | Stop creating users/user_roles, remove users backfill, create audit_log without FK to users | Fresh DBs never get `users`/`user_roles` |
| Add cleanup migration | After e5f6a7b8c9d0 | Drops tables from already-upgraded DBs; idempotent for fresh DBs |

### Merge heads / stamps / downgrade

- **Merge heads:** Current head is `e5f6a7b8c9d0` (single head). New migration will have `down_revision = "e5f6a7b8c9d0"`. No merge needed.
- **Stamps:** Not affected.
- **Downgrade:** c8a3d0b9c777 downgrade must be updated to remove drops for `users` and `user_roles`; cleanup migration downgrade is `pass` (no recreate).

---

## Phase A3 — Concrete Deliverables

### 1. Exact files to edit

| File | Action |
|------|--------|
| `alembic_tenant/versions/c8a3d0b9c777_add_tenants_and_rbac.py` | Edit upgrade and downgrade |
| `alembic_tenant/versions/f1a2b3c4d5e6_drop_lane_a_legacy_tables.py` | **New file** |

### 2. Exact changes to c8a3d0b9c777

**Upgrade:**

1. **Remove** `ensure_users_table()` call (line 431).
2. **Remove** entire `user_roles` creation block (lines 557–585).
3. **Modify** `audit_log` creation: drop the `ForeignKeyConstraint` from `actor_user_id` to `users.id`. Keep `actor_user_id` as `sa.Integer(), nullable=True` only.
4. **Remove** users backfill block (lines 683–684): `UPDATE users SET scope...`, `UPDATE users SET tenant_id...`.
5. **Remove** super-admin backfill block (lines 686–691): the loop that inserts into `user_roles`.
6. **Remove** users check constraint and alter (lines 690–696): `ck_users_scope_tenant_match` and `op.alter_column("users", "scope", ...)`.
7. **Delete** the `ensure_users_table()` function (lines 357–411) — no longer used.

**Downgrade:**

1. **Remove** lines 711–716: all `op.drop_*` operations on `users` (check constraint, fk, index, columns).
2. **Remove** lines 729–731: `op.drop_index`, `op.drop_table("user_roles")`.

*(Rationale: If the upgraded migration no longer creates users/user_roles, downgrade must not attempt to drop them or it will fail on fresh DBs. For DBs that already ran the old upgrade, users would remain after downgrade—acceptable in dev; cleanup migration will drop them on next upgrade.)*

### 3. Exact new migration file

```python
"""Drop Lane A legacy tables (users, user_roles, driver_phones_old)

Revision ID: f1a2b3c4d5e6
Revises: e5f6a7b8c9d0
Create Date: 2026-03-15

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "f1a2b3c4d5e6"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1. Drop audit_log FK to users (must precede users drop)
    if insp.has_table("audit_log"):
        for fk in insp.get_foreign_keys("audit_log"):
            if fk.get("referred_table") == "users":
                op.drop_constraint(fk["name"], "audit_log", type_="foreignkey")
                break

    # 2. Drop tables (order: user_roles first, then users; driver_phones_old independent)
    op.execute(sa.text("DROP TABLE IF EXISTS user_roles CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS users CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS driver_phones_old CASCADE"))


def downgrade() -> None:
    # No downgrade — these tables are legacy; do not recreate
    pass
```

**Note:** Use `sa.text("DROP TABLE IF EXISTS ...")` for SQLAlchemy 2.x compatibility.

### 4. Verification commands

#### 4.1 Current tenant_demo upgrade

```bash
docker exec truckerp-api bash -lc 'set -a && . /run/secrets/truckerp.env && set +a && cd /app && bash scripts/tenant_upgrade_head.sh'
```

**Expected:** Migration runs; no errors.

**Proof (tables absent):**
```bash
docker exec truckerp-api bash -lc 'set -a && . /run/secrets/truckerp.env && set +a && psql "$TENANT_DATABASE_URL" -t -c "SELECT tablename FROM pg_tables WHERE schemaname='\''public'\'' AND tablename IN ('\''users'\'','\''user_roles'\'','\''driver_phones_old'\'');"'
```
→ 0 rows.

#### 4.2 Fresh empty tenant DB → upgrade head

**Lab / test matrix only** (empty `tenant_test`); not the routine operator prod procedure.

1. Create empty DB: `createdb tenant_test` (or equivalent).
2. Set `ALEMBIC_TENANT_DATABASE_URL` to that DB.
3. Run:
```bash
docker exec truckerp-api bash -lc 'set -a && . /run/secrets/truckerp.env && set +a && export ALEMBIC_TENANT_DATABASE_URL="postgresql+asyncpg://USER:PASS@HOST:PORT/tenant_test" && cd /app && alembic -c alembic_tenant.ini upgrade head'
```
4. Verify `users`, `user_roles`, `driver_phones_old` do not exist (same `psql` query as 4.1).

#### 4.3 Second upgrade run (no reappearance)

Re-run:
```bash
docker exec truckerp-api bash -lc 'set -a && . /run/secrets/truckerp.env && set +a && cd /app && bash scripts/tenant_upgrade_head.sh'
```

**Expected:** Idempotent; no errors; tables remain absent.

#### 4.4 Autogenerate drift check

**Non-operator / migration authoring:** autogenerate only.

```bash
docker exec truckerp-api bash -lc 'set -a && . /run/secrets/truckerp.env && set +a && cd /app && alembic -c alembic_tenant.ini revision --autogenerate -m "test_no_recreate"'
```

**Expected:** Autogenerate does **not** propose recreating `users`, `user_roles`, or `driver_phones_old`.

Delete the generated revision if it was only for testing.

---

## Summary

| Item | Decision |
|------|----------|
| Edit c8a3d0b9c777? | **Yes** — stop creating users/user_roles; create audit_log without FK to users |
| Edit 7de1d90c39eb? | **No** |
| Add cleanup migration? | **Yes** — drops users, user_roles, driver_phones_old; idempotent |
| Downgrade of cleanup? | `pass` — no recreation |
| Merge heads? | No — single head |
| Schema validation impact? | None — `users`/`user_roles` not in `required_tables` |
