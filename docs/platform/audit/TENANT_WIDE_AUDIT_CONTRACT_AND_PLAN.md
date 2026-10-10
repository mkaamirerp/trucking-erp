## Tenant-wide Audit Contract (Production Path) + Current State + Implementation Plan

This document captures the **real audit contract** (what we want), then maps it against **what exists in this repo today**, what is **blocking**, and a **phased plan** to implement it safely.

---

## 1) The contract (recommended architecture)

### 1. One shared audit table (tenant-level)

Create a tenant-level append-only table like **`audit_events`**.

**Core fields**

- `id`
- `tenant_id`
- `event_at`
- `actor_type` (examples: `user`, `system`, `api`, `webhook`, `job`)
- `actor_user_id` (nullable)
- `actor_label` (nullable snapshot)
- `module` (examples: `people`, `onboarding`, `loads`, `dispatch`, `fleet`, `brokers`)
- `entity_type` (examples: `person`, `person_application`, `load`, `truck`, `trailer`, `broker`, `settlement`)
- `entity_id`
- `action` (examples: `created`, `updated`, `approved`, `assigned`, `dispatched`, `status_changed`, `document_uploaded`)
- `subaction` (nullable)
- `request_id` (nullable)
- `correlation_id` (nullable)
- `source` (examples: `ui`, `api`, `background_job`, `webhook`, `import`, `system_rule`)
- `reason_code` (nullable)
- `reason_note` (nullable)
- `snapshot_before` (jsonb, nullable)
- `snapshot_after` (jsonb, nullable)
- `changed_fields` (jsonb, nullable)
- `context_json` (jsonb, nullable)
- `visibility` (examples: `normal`, `sensitive`, `finance_sensitive`, `admin_sensitive`)
- `created_at`

### 2. Append-only only

Never update audit rows except maybe internal redaction metadata in rare admin-only cases.

- No deletes in normal flow.
- No overwrite.
- No mutable history.
- If a correction is needed, write another audit event.

### 3. Two levels of payload

Do not dump giant raw objects every time unless needed.

Use:

- Lightweight default: `changed_fields` (small before/after map for touched fields only)

Example:

```json
{
  "rate": { "before": 2500, "after": 2750 },
  "status": { "before": "assigned", "after": "dispatched" }
}
```

- Full snapshot only for critical moments: `snapshot_before` / `snapshot_after` for:
  - approvals
  - onboarding completion
  - settlement lock
  - payroll batch lock
  - dispatch creation
  - merge operations
  - privileged corrections

### 4. One audit writer service

Do not let every router invent its own audit format.

Create one shared service like:

- `write_audit_event(...)`

All modules call that. Inputs should be normalized:

- `module`
- `entity_type`
- `entity_id`
- `action`
- `actor`
- `source`
- `before`
- `after`
- `changed_fields`
- `reason_code`
- `context`

This is how we prevent drift.

### 5. Entity timeline model

Every major record page should be able to load:

- its own timeline by `entity_type` + `entity_id`
- related timeline optionally by `correlation_id`

Later:

- one global Audit page can search across all modules

### 6. Correlation IDs are important

One user action may touch multiple records. Example: approving a driver application may create:

- `person`
- `person_role`
- `driver_profile`
- operational `drivers` row
- audit writes on application and person

All those events should share one `correlation_id` so we can reconstruct one business action across modules.

### 7. Sensitive visibility levels

Not every audit row should be equally visible.

Add `visibility` levels:

- `normal`
- `sensitive`
- `admin_sensitive`
- `finance_sensitive`

UI should filter based on RBAC.

### 8. Redaction rules

Audit must not become a leak.

Some fields should never be stored raw in audit diffs:

- SSN
- bank account
- tokens
- passwords
- secrets
- (maybe) full DOB depending on policy

Use field-level redaction helpers (last4, masked values, or a simple “changed” flag).

### 9. Event taxonomy

Use stable action names now so future modules stay consistent.

Examples:

- Common: `created`, `updated`, `deleted_soft`, `status_changed`, `linked`, `unlinked`, `activated`, `deactivated`
- Onboarding: `application_submitted`, `review_started`, `review_corrected`, `approved`, `rejected`, `onboarding_completed`, `documents_requested`, `document_uploaded`, `document_accepted`
- Loads: `load_created`, `load_updated`, `load_status_changed`, `load_assigned`, `load_dispatched`, `trip_created`, `document_snapshot_confirmed`, `broker_resolved`, `duplicate_linked`
- Dispatch: `dispatch_assignment_changed`, `trip_number_generated`, `driver_swapped`, `truck_swapped`, `trailer_swapped`
- Brokers: `broker_created`, `broker_updated`, `broker_contact_added`, `broker_match_resolved`, `global_broker_promoted`, `global_broker_merged`
- Finance: `settlement_draft_created`, `settlement_finalized`, `settlement_paid`, `payroll_batch_locked`

### 10. UI design

Two surfaces:

**A) Embedded timeline** (per module page)

- timestamp
- actor
- action label
- short summary
- expandable diff

**B) Central Audit workspace** (tenant-wide search)

- module
- entity type
- actor
- date range
- action
- correlation id
- sensitivity level
- free-text

### 11. Loads right now

To finish the current load audit placeholder properly, do not make a fake timeline.

Implement the shared audit table/service first, then wire load events into it.

Minimum load events to start:

- `load_created`
- `load_updated`
- `load_status_changed`
- `load_assigned`
- `load_dispatched`
- `document_snapshot_confirmed`
- `customs_broker_changed`
- `note_added`
- `duplicate_linked`
- `broker_match_review_required`

Then the load audit panel becomes just:

- query `audit_events` for `entity_type="load"` and `entity_id=load.id`

### 12. Best implementation order

- **Phase 1**: shared audit schema + writer service
- **Phase 2**: wire People + PersonApplication + Loads first
- **Phase 3**: embedded timeline UI on People / Onboarding review / Load workspace
- **Phase 4**: central Audit workspace
- **Phase 5**: expand to Dispatch, Fleet, Brokers, Settlements, Payroll, Admin settings

### 13. Guardrails

- No module-specific audit table unless absolutely necessary
- No custom event format per router
- No mutable audit history
- No storing secrets/raw sensitive values
- Always include actor/source/correlation where possible
- Prefer structured `reason_code` over free text
- Use one shared renderer for diffs in UI

---

## 2) What’s already in this repo today (audit-related inventory)

This repo already has **multiple audit-ish mechanisms**, but they are **not yet** the “one shared audit_events contract”.

### A) Tenant audit table exists: `tenant_audit_logs` (tenant DB)

- Table: `tenant_audit_logs` (migration: `alembic_tenant/versions/a867a473deb7_add_tenant_audit_logs_table.py`)
- Model: `app/models/tenant_audit.py`
- Shape today (high level):
  - `tenant_id`, `actor_user_id`
  - `action`, `object_type`, `object_id`
  - `details_json` (unstructured)
  - `ip`, `user_agent`
  - `created_at`

### B) People workspace “correction history” uses `tenant_audit_logs`

- Backend: `app/services/people_workspace.py` writes best-effort rows via `write_people_patch_audit(...)`
- Endpoint: `GET /api/v1/people/{id}/audit-log` (people workspace router) reads these rows
- Frontend: `apps/web/src/pages/PeopleWorkspacePage.tsx` displays **Correction history**

This is good as an MVP, but it is **not** the contract (missing module/entity taxonomy, correlation IDs, visibility, and normalized diff fields).

### C) Platform scope has a separate audit table (not tenant-wide)

- `global_booking_broker_audit_events` in platform DB (`app/models/global_booking_broker.py`)
- UI drawer: `apps/web/src/pages/PlatformGlobalBookingBrokersPage.tsx`

This is a **module-specific table** with a minimal schema. It’s useful, but it is *not* aligned with the tenant-wide audit_events contract.

### D) A request ID already exists in middleware

Tenant middleware generates/propagates `X-Request-ID` and stores it on `request.state.request_id` (`app/middleware/tenant_context.py`).

This is a strong foundation for `request_id` and for deriving default `correlation_id`.

### E) “Load audit timeline” UI placeholder exists

- Load workspace has an “Audit timeline coming soon” placeholder (`apps/web/src/pages/LoadWorkspacePage.tsx`).

---

## 3) What’s blocking the real contract (gap analysis)

### Blocking gap 1: No single shared tenant-wide table that matches the contract

We have `tenant_audit_logs`, but it does not provide:

- `module`, `entity_type`, `entity_id` (contract wants normalized timeline keys)
- `event_at` distinct from `created_at`
- `actor_type`, `actor_label`, `source`
- `request_id`, `correlation_id`
- `visibility`
- structured `changed_fields` vs full snapshots

### Blocking gap 2: Writer is not centralized across modules

People has a local helper (`write_people_patch_audit`) that writes to `tenant_audit_logs`, but it is not a shared system-wide writer with:

- normalized inputs
- redaction enforcement
- default correlation/request sourcing
- consistent action taxonomy enforcement

### Blocking gap 3: Redaction and visibility are not first-class

Today, `details_json` can accidentally include sensitive data if a caller passes it.

Contract requires:

- a redaction helper (field allow/deny lists + masking)
- visibility labels enforced by writers and filtered by readers

### Blocking gap 4: Correlation story is missing

Even though `request_id` exists in middleware, it is not being propagated into audit rows in a standardized way, and we do not have a stable `correlation_id` concept used across multi-entity actions.

### Blocking gap 5: UI lacks a shared timeline renderer + shared query model

People uses a bespoke audit entry schema; platform brokers uses another; loads has a placeholder.

Contract wants:

- shared audit row shape
- shared diff renderer
- page-embedded timeline + central audit workspace

---

## 4) Plan to implement (phased, minimal-risk)

### Phase 1 — Shared schema + shared writer service (foundation)

Deliverables:

- Tenant migration: create `audit_events` table (append-only), indexed for:
  - `(tenant_id, entity_type, entity_id, event_at desc)`
  - `(tenant_id, correlation_id, event_at desc)`
  - `(tenant_id, module, event_at desc)`
  - `(tenant_id, actor_user_id, event_at desc)` (optional)
- Model: `AuditEvent` (tenant DB)
- Service: `write_audit_event(...)` that:
  - accepts normalized inputs (`module`, `entity_type`, `entity_id`, `action`, etc.)
  - auto-fills `request_id` from request context when available
  - defaults `correlation_id` to `request_id` when caller doesn’t provide one
  - enforces redaction policy and sets `visibility`
  - supports “light diff” (`changed_fields`) and “snapshot” (`snapshot_before/after`)
- Reader API (minimal): `GET /api/v1/audit/events?entity_type=...&entity_id=...&limit=...`

Guardrails:

- Do not delete/overwrite audit rows.
- Fail-open for audit writes only if explicitly desired (People currently does “best effort; never raises”).

### Phase 2 — Wire first consumers: People + PersonApplication + Loads

Deliverables:

- People corrections: replace/augment `tenant_audit_logs` writes with `audit_events` writes.
  - Keep existing People endpoint stable, or version it, but standardize underlying storage and output.
- PersonApplication: write audit events for:
  - application submitted
  - review edits (role, status transitions)
  - approve/reject
  - onboarding completed (if/when implemented)
- Loads: implement the minimum load event set listed in the contract.

### Phase 3 — Embedded timeline UI (shared component)

Deliverables:

- A shared UI component (timeline + expandable diff renderer) that can render `audit_events`.
- Embedded panels on:
  - People workspace page
  - Onboarding admin detail page
  - Load workspace page (replace “coming soon”)

### Phase 4 — Central Audit workspace

Deliverables:

- UI page: search/filter across tenant by:
  - module, entity type, actor, date range, action, correlation id, visibility
- API endpoint supporting search with paging.

### Phase 5 — Expand across modules

Add audit events to Dispatch, Fleet, Brokers, Settlements, Payroll, Admin settings using the same writer + taxonomy.

---

## 5) Practical next step recommendation (what to do next)

Next design/build should be:

> **Tenant-wide Audit module architecture** with **Loads as the first consumer**, not a one-off “Load audit timeline feature”.

That is the future-safe path that prevents drift.

---

## 6) Concrete `audit_events` schema + writer contract (next-step spec)

This section is the **implementation-ready spec** for the next step: define **exact columns**, **indexes/constraints**, and a strict **writer contract**. It also defines a safe **migration strategy** from existing `tenant_audit_logs`.

### 6.1 Canonical tenant table: `audit_events`

**DDL intent**

- Lives in **tenant DB** (same place as `tenant_audit_logs` today).
- **Append-only**: no updates, no deletes, no “fixing history”; corrections are new rows.
- Supports two payload sizes:
  - **light** diff: `changed_fields`
  - **heavy** snapshots: `snapshot_before`/`snapshot_after` only for critical events

**Columns**

- `id` **bigint** primary key (autoincrement)
- `tenant_id` **int** not null
- `event_at` **timestamptz** not null  
  - semantic timestamp (when the business event occurred); default = `now()`
- `actor_type` **varchar(16)** not null  
  - allowed set: `user`, `system`, `api`, `webhook`, `job`, `import`
- `actor_user_id` **bigint** nullable  
  - for `actor_type=user` (or when a user is the actor)
- `actor_label` **varchar(128)** nullable  
  - snapshot label for display (e.g. “System”, “Webhook: Samsara”, “Job: nightly_reconcile”)
- `module` **varchar(32)** not null  
  - allowed set starts small: `people`, `onboarding`, `loads`, `dispatch`, `fleet`, `brokers`, `finance`, `admin`
- `entity_type` **varchar(64)** not null  
  - examples: `person`, `person_application`, `load`, `truck`, `trailer`, `broker`, `settlement`
- `entity_id` **varchar(128)** not null  
  - string to support bigint IDs and composite keys if needed later
- `entity_label` **varchar(256)** nullable  
  - optional display snapshot to reduce joins in UI/search (e.g. load number, person full name, broker display name)
- `action` **varchar(64)** not null  
  - stable taxonomy string (see §9 examples)
- `subaction` **varchar(64)** nullable  
  - optional refinement (e.g. `field_corrected`, `status_changed:assigned->dispatched` is **not** recommended; keep that in `changed_fields`)
- `request_id` **varchar(64)** nullable  
  - `X-Request-ID` (middleware already issues this)
- `correlation_id` **varchar(64)** nullable  
  - used to tie multiple events to one business action; default to `request_id` if not provided
- `source` **varchar(32)** not null  
  - allowed set: `ui`, `api`, `background_job`, `webhook`, `import`, `system_rule`
- `reason_code` **varchar(64)** nullable  
  - structured reason (preferred over free text)
- `reason_note` **text** nullable  
  - optional human note; must not contain secrets
- `visibility` **varchar(32)** not null  
  - allowed set: `normal`, `sensitive`, `admin_sensitive`, `finance_sensitive`
- `changed_fields` **jsonb** nullable  
  - default payload; see §6.2 for exact shape
- `snapshot_before` **jsonb** nullable
- `snapshot_after` **jsonb** nullable
- `context_json` **jsonb** nullable  
  - safe extra context (screen, feature flag, actor impersonation, etc.)
- `created_at` **timestamptz** not null default `now()`  
  - insertion time (operational)

**Canonical ordering**

- Canonical sort order for timelines/search is: **`event_at desc, id desc`**
- `id` is the tie-breaker; **never rely on timestamp alone**

**Constraints**

- `check` constraints:
  - `actor_type` in allowed set
  - `source` in allowed set
  - `visibility` in allowed set
  - `entity_id <> ''`, `entity_type <> ''`, `module <> ''`, `action <> ''`
- Optional (recommended) check:
  - `jsonb_typeof(changed_fields) = 'object'` when not null

**Indexes (minimum set)**

- `ix_audit_events_tenant_entity_time`: `(tenant_id, entity_type, entity_id, event_at desc, id desc)`
- `ix_audit_events_tenant_correlation_time`: `(tenant_id, correlation_id, event_at desc, id desc)` where `correlation_id is not null`
- `ix_audit_events_tenant_module_time`: `(tenant_id, module, event_at desc, id desc)`
- `ix_audit_events_tenant_actor_time`: `(tenant_id, actor_user_id, event_at desc, id desc)` where `actor_user_id is not null`
- Optional for central search later:
  - `(tenant_id, action, event_at desc, id desc)`
  - GIN index on `changed_fields` if we prove it’s needed (avoid premature indexing)

**Why varchar sizes**

- `varchar(64)` for action/correlation/request is aligned with existing patterns (`TenantAuditLog.action` is 64 today).
- `entity_id` as `varchar(128)` keeps cross-entity uniformity and avoids type coupling.

### 6.2 Normalized payload shapes (required)

**`changed_fields` shape (required when using diff mode)**

- Type: JSON object mapping field name → `{ before, after, redacted?: true }`
- Example:

```json
{
  "status": { "before": "assigned", "after": "dispatched" },
  "rate": { "before": 2500, "after": 2750 }
}
```

**Redaction marker**

When a value is sensitive, store:

```json
{
  "ssn": { "before": null, "after": null, "redacted": true }
}
```

or masked values only if policy allows (e.g. last4).

**Snapshots**

`snapshot_before` / `snapshot_after` may store larger objects but must pass the same redaction rules.

### 6.3 Writer contract: `write_audit_event(...)`

**Purpose**

One canonical service function to create an append-only audit row. Routers/services must not invent custom formats.

**Inputs (normalized)**

Required:

- `tenant_id: int`
- `module: str`
- `entity_type: str`
- `entity_id: str | int`
- `action: str`
- `source: str`
- `visibility: str` (default `normal`)
- `entity_label: str | None` (optional display snapshot; recommended when cheap)

Actor:

- `actor_type: str` (default `user` when `actor_user_id` provided, else `system`)
- `actor_user_id: int | None`
- `actor_label: str | None`

Correlation:

- `request_id: str | None` (if in HTTP request context, pulled automatically)
- `correlation_id: str | None` (default to `request_id` when absent)

Payload:

- `changed_fields: dict[str, {before: Any, after: Any}] | None`
- `snapshot_before: dict | None`
- `snapshot_after: dict | None`
- `context: dict | None`
- `reason_code: str | None`
- `reason_note: str | None`

Timing:

- `event_at: datetime | None` (default now)

**Rules (must be enforced by the writer)**

- **Append-only** insert; no updates/deletes.
- **Payload presence rule (hard)**:
  - at least one of: `changed_fields`, `snapshot_before`, `snapshot_after`, `context_json` must be present
- **Payload combination rule (allowed)**:
  - `changed_fields` may be written together with snapshots (common for “checkpoint” events where both a compact diff and a full redacted snapshot matter)
- **Redaction always applied** to `changed_fields` and snapshots before insert.
- **Visibility**:
  - default `normal`
  - writer may **upgrade** visibility based on field names present (e.g. pay/SSN) but must never downgrade
- **Correlation defaults**:
  - `request_id` pulled from `request.state.request_id` when available
  - `correlation_id = correlation_id or request_id`
- **Ordering guidance**:
  - readers must order by `event_at desc, id desc`
  - writers may set `event_at` explicitly for backfills/imports; otherwise default `now()`
- **Action taxonomy**:
  - allow a whitelist per module (enforced gradually)
  - in early phase, log + allow unknown actions to avoid blocking rollout; later tighten

**Return**

- `AuditEvent` row (or `id`) on success.
- For best-effort mode: returns `None` on failure (and logs exception).

**Failure mode policy**

Two explicit modes:

- **best_effort=True** (default for UX paths): never raise; logs; does not block the business action
- **best_effort=False** (admin/finance critical paths if desired): raise so we don’t silently lose audit

### 6.4 Redaction policy (minimum)

Maintain a denylist of field names (case-insensitive, substring match where appropriate):

- `password`, `password_hash`
- `token`, `secret`, `api_key`
- `ssn`
- `bank_account`, `routing_number`

For denylisted fields:

- store `{before:null, after:null, redacted:true}` (or masked last4 if allowed)

Also: cap large string lengths in audit payload (prevent megabyte rows).

### 6.5 Read contract (minimum endpoints)

Minimal timeline read:

- `GET /api/v1/audit/events/by-entity?entity_type=...&entity_id=...&limit=...`
  - returns newest-first, includes `changed_fields` and metadata

Optional correlation view:

- `GET /api/v1/audit/events/by-correlation?correlation_id=...&limit=...`

Visibility filtering:

- server enforces RBAC and filters rows by `visibility` for the caller.

---

## 7) Migration strategy from existing `tenant_audit_logs`

Goal: move from `tenant_audit_logs` (unstructured, people-only today) to `audit_events` without losing history or breaking the People UI.

### 7.1 Strategy summary (safe, reversible)

1. **Add `audit_events`** (new table + model + writer service).
2. **Dual-write** for the first consumer (People corrections):
   - keep writing `tenant_audit_logs` (existing behavior)
   - also write `audit_events` with normalized payload
3. **Read-path cutover**:
   - update People audit endpoint to read from `audit_events` first (or behind a flag)
   - keep legacy read as fallback while we validate
4. **Backfill legacy rows**:
   - convert `tenant_audit_logs` → `audit_events` for historical continuity
5. **Freeze legacy**:
   - stop writing `tenant_audit_logs` for new events once `audit_events` is proven
6. **Keep legacy table** for a long time (or drop much later with an explicit deprecation/migration window).

### 7.2 Mapping: `tenant_audit_logs` → `audit_events`

For each `tenant_audit_logs` row:

- `tenant_id` → `tenant_id`
- `created_at` → `event_at` (and `created_at`)
- `actor_user_id` → `actor_user_id`
- `actor_type`:
  - `user` if `actor_user_id` not null else `system`
- `module`:
  - derive from `object_type`:
    - `person` → `people`
    - else default `admin` (until we have better mapping)
- `entity_type`:
  - `object_type` (string), normalized (e.g. `person`)
- `entity_id`:
  - `object_id` (string)
- `action`:
  - `action`
- `source`:
  - default `api` (unless context says otherwise; legacy table doesn’t carry it)
- `visibility`:
  - default `normal` (unless action matches a known sensitive pattern)
- `changed_fields`:
  - if legacy `details_json` contains `snapshot` and `changed_keys` (People writer does):
    - convert `snapshot` dict to `changed_fields` entries:
      - each key: `{before: null, after: value}` (legacy does not store before)
  - else store legacy `details_json` into `context_json.legacy_details_json`
- `context_json`:
  - include `{ legacy: { ip, user_agent, details_json } }`

### 7.3 Backfill mechanics

- Backfill is an **idempotent** script/job that reads `tenant_audit_logs` in ascending `id` and inserts into `audit_events`.
- Dedup key options:
  - store `context_json.legacy_source = { table: 'tenant_audit_logs', id: <id> }` and unique-index that
  - or use `(tenant_id, module, entity_type, entity_id, action, event_at, actor_user_id)` as a weak dedup (not preferred)

Recommended: add a column or enforced unique expression on `context_json->legacy_source->id` is hard in SQL; simplest is a dedicated nullable column:

- `legacy_tenant_audit_log_id bigint null unique`

If we add this, migration/backfill is clean and provable.

### 7.4 Cutover acceptance checks

- For a known person, old endpoint and new endpoint return consistent counts and newest events.
- For a known correction save, `audit_events` contains:
  - `module='people'`, `entity_type='person'`, `entity_id=<id>`
  - `action='people_core_patch'` (or new taxonomy name)
  - `request_id` set, `correlation_id` set
  - redaction rules applied


