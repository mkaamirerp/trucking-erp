# Admin Users Vertical Slice — Proof & Verification

## Approved temporary fields

**Form and list use:** username, email, phone, access_level (READ_ONLY | FULL_ACCESS).

**API mapping:**
- access_level READ_ONLY → platform role TENANT_MEMBER
- access_level FULL_ACCESS → platform role TENANT_ADMIN
- username → stored as first_name in platform_users

## Scope (locked)

- **Deactivation enforcement**: Kept (login, refresh, get_current_user enforce `PlatformUser.status` and `TenantMembership.status`).
- **Tenant-admin password reset**: Removed. Password management stays platform-side (`/api/v1/auth/forgot-password`).
- **Suspend/Reactivate**: Changes `TenantMembership.status` only. Does **not** modify `platform_users.status`.

## Access model

| Role         | Access level | Can list users | Can invite | Can suspend/reactivate |
|--------------|--------------|----------------|------------|-------------------------|
| TENANT_OWNER | FULL_ACCESS  | yes            | yes        | yes                     |
| TENANT_ADMIN | FULL_ACCESS  | yes            | yes        | yes                     |
| TENANT_MEMBER| READ_ONLY    | yes            | no (403)   | no                      |

## Required proof cases

### 1. FULL_ACCESS can invite/create

**Setup**: Log in as tenant admin (TENANT_ADMIN or TENANT_OWNER).

**Steps**:
- Go to `/admin/users`
- Invite form is enabled
- Submit invite (email, first_name, last_name)
- Expect: `200` and "Invite sent"

**API**:
```bash
# With valid admin session (access_token cookie)
curl -X POST "https://demo.truckerp.me/api/v1/admin/users/invite" \
  -H "Content-Type: application/json" \
  -H "Cookie: access_token=..." \
  -d '{"username":"New User","email":"new@example.com","phone":"+1234567890","access_level":"READ_ONLY"}'
```
Expect: `200 OK`.

### 2. READ_ONLY gets 403 on POST invite

**Setup**: Log in as tenant member (TENANT_MEMBER).

**Steps**:
- Go to `/admin/users`
- Invite form is disabled with "(Read-only: invite disabled)"
- Submit button is disabled
- If POST is forced (e.g. via devtools), expect `403` with:
  `"Full access required to invite users. Your role has read-only access."`

**API**:
```bash
# With TENANT_MEMBER session
curl -X POST "https://demo.truckerp.me/api/v1/admin/users/invite" \
  -H "Content-Type: application/json" \
  -d '{"username":"X Y","email":"x@example.com","access_level":"READ_ONLY"}'
```
Expect: `403 Forbidden`, body contains "Full access required to invite users".

### 3. UI hides/disables invite for READ_ONLY

**Setup**: Log in as TENANT_MEMBER.

**Verify**:
- Invite form inputs (username, email, phone, access level) are disabled
- Invite submit button is disabled
- Suspend/Reactivate buttons are hidden
- User list is visible (read-only)

### 3b. TENANT_MEMBER limited to /admin/users only

**Verify**: TENANT_MEMBER who accesses /admin (or /admin/company-profile, /admin/roles, etc.) is redirected to dashboard. Only /admin/users is reachable.

### 4. Suspend/Reactivate changes membership only

**Code verification** (no PlatformUser writes):

- `suspend_user`: updates `TenantMembership.status = "suspended"`
- `reactivate_user`: updates `TenantMembership.status = "active"`
- Neither touches `PlatformUser` or `platform_users.status`

**SQL audit** (optional):
```sql
-- Before suspend: check tenant_memberships.status
SELECT status FROM tenant_memberships WHERE user_id = '...' AND tenant_id = ...;

-- After suspend: status = 'suspended'
-- platform_users.status unchanged
SELECT status FROM platform_users WHERE id = '...';
```

## Test data

To test READ_ONLY, add a TENANT_MEMBER to the demo tenant:

1. Create a platform user (or use existing).
2. Add `platform_tenant_members` row with `role = 'TENANT_MEMBER'`.
3. Add `tenant_memberships` row with `status = 'active'`.
4. Log in as that user and verify read-only behavior.
