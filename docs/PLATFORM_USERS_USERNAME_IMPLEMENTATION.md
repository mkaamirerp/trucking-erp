# Platform Users Username Field — Implementation Summary

## Overview

Replaced the temporary bridge (username stored in `first_name` with `last_name = ''`) with a production-grade `username` field on `platform_users`.

## Uniqueness Rule

**Case-insensitive global uniqueness.**

- Unique index: `uq_platform_users_username_lower` on `LOWER(username)` WHERE `username IS NOT NULL`
- Multiple NULL usernames allowed (signup users may not have a username)
- Application-level check before insert for friendly 400 response

## Migration Details

**File:** `alembic_platform/versions/0025_platform_users_username.py`

**Revision:** `0025_platform_users_username` (depends on `0024_user_invites`)

**Upgrade steps:**
1. Add `username` column (nullable)
2. Create non-unique index `ix_platform_users_username` for lookups
3. Make `first_name` and `last_name` nullable
4. Backfill: for rows with `last_name` empty and non-empty `first_name`, copy `first_name` → `username`, clear `first_name`/`last_name`
5. Create unique index `uq_platform_users_username_lower` on `LOWER(username)` WHERE `username IS NOT NULL`

**Backfill heuristic:**
- Only rows with `TRIM(COALESCE(last_name, '')) = ''` and non-empty `first_name` are treated as invite-flow users
- Signup users (real first_name + last_name) are not touched

## Files Changed

| File | Change |
|------|--------|
| `alembic_platform/versions/0025_platform_users_username.py` | New migration |
| `app/models/platform.py` | Add `username`, make `first_name`/`last_name` nullable |
| `app/routers/tenant_admin.py` | Invite writes to `username`, list uses `username` with fallback |
| `app/routers/auth.py` | `/me` returns `username` |

## Verification Steps

### 1. Schema verification

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec -T truckerp-postgres psql -U postgres -d trucking_erp -c "\d platform_users"
```

Expect: `username` column (nullable), `first_name`/`last_name` nullable.

### 2. Unique index verification

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec -T truckerp-postgres psql -U postgres -d trucking_erp -c "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'platform_users';"
```

Expect: `uq_platform_users_username_lower` with `lower((username)::text)` and `WHERE (username IS NOT NULL)`.

### 3. New invite stores username

1. Log in as tenant admin (FULL_ACCESS).
2. Invite a user with username `alice` and email `alice@example.com`.
3. Query:

```sql
SELECT id, email, username, first_name, last_name FROM platform_users WHERE email = 'alice@example.com';
```

Expect: `username = 'alice'`, `first_name IS NULL`, `last_name IS NULL`.

### 4. first_name no longer used as username

- Invite flow creates `PlatformUser(username=..., first_name=None, last_name=None)`.
- List flow uses `pu.username or (first_name + last_name).strip() or email` for display.

### 5. Existing rows migrated correctly

- Invite-flow users: `first_name` → `username`, `first_name`/`last_name` cleared.
- Signup users: unchanged (`first_name`/`last_name` remain, `username` NULL).

### 6. Uniqueness enforcement

- Try inviting two users with `alice` and `Alice` (same case-insensitive username): second should fail with 400 "Username already taken" or DB unique violation.
