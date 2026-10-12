# Load workspace draft — design specification (Phase 2)

**Status:** DESIGN CONTRACT ONLY — NOT IMPLEMENTED  
**Authority:** Subordinate to [`MASTER.md`](./MASTER.md). Owner addendum: GitHub commit `586ee10ddde7ec390baf27fecfb819f684ccbe6c` (`review/issue5-draft-boundary-20261012`).  
**API sketch:** [`draft_workspace_api.yaml`](./draft_workspace_api.yaml)  
**Proposed MASTER edits:** [`MASTER_DRAFT_WORKSPACE_PROPOSED_DELTA.md`](./MASTER_DRAFT_WORKSPACE_PROPOSED_DELTA.md) (do not merge until owner-approved)

---

## 0. Problem statement

Today, **manual parse results live in React state** until **Create Load** inserts a permanent `loads` row (`status=draft`). Email intake **creates `loads` rows immediately**. Under the Issue 5 interim DELETE guard, unwanted commercial rows **accumulate** with no cancel path. Trip membership does **not** require `ready` (MASTER I12 open).

This spec defines a **tenant-scoped workspace draft** (distinct from `loads.id`), **promotion** to an official Load created **`ready`**, **immutable evidence** at promotion, and **forward-only** trip eligibility — without implementing code in this phase.

---

## 1. Temporary draft — PostgreSQL schema

### 1.1 Table: `load_workspace_drafts`

Tenant DB only. **Not** a row in `loads`.

| Column | Type | Notes |
|--------|------|--------|
| `id` | `UUID` PK | Public draft identifier (distinct from `loads.id`). |
| `tenant_id` | `INTEGER` NOT NULL | Composite isolation with all tenant tables. |
| `concurrency_version` | `INTEGER` NOT NULL DEFAULT 1 | Optimistic concurrency on save/discard/promote. |
| `status` | `VARCHAR(32)` NOT NULL | State machine (§3). |
| `draft_schema_version` | `INTEGER` NOT NULL | Version of `draft_json` contract (§1.2). |
| `draft_json` | `JSONB` NOT NULL | Workspace fields; hydration-compatible with parse DTO. |
| `source_channel` | `VARCHAR(32)` NOT NULL | e.g. `manual`, `email_intake`, `load_lab_import` (future). |
| `created_by_platform_user_id` | `UUID` NULL | Creator; used for list/filter and audit. |
| `updated_by_platform_user_id` | `UUID` NULL | Last editor. |
| `email_thread_id` | `INTEGER` NULL | Optional FK `email_threads` (tenant-scoped); intake workflow. |
| `pdf_storage_key` | `TEXT` NULL | Opaque internal key; **never returned by APIs** (§4). |
| `pdf_retention_class` | `VARCHAR(16)` NOT NULL DEFAULT `workspace_ttl` | `workspace_ttl` until promote; then `commercial_permanent` (§4). |
| `pdf_sha256` | `CHAR(64)` NULL | Hex SHA-256 of current PDF bytes. |
| `pdf_filename` | `TEXT` NULL | Original filename for display. |
| `pdf_size_bytes` | `BIGINT` NULL | |
| `accepted_parse_json` | `JSONB` NULL | Last operator-accepted parse snapshot (subset of `LoadDocumentParseResponse`). |
| `accepted_parse_schema_version` | `VARCHAR(64)` NULL | Parser/schema pin at acceptance. |
| `accepted_parse_pdf_sha256` | `CHAR(64)` NULL | PDF bytes hash when parse was accepted; mismatch ⇒ parse stale (§1.2). |
| `expires_at` | `TIMESTAMPTZ` NOT NULL | TTL for workspace drafts (not used post-promotion). |
| `promoted_load_id` | `INTEGER` NULL | Set once on success; FK `loads(id)` RESTRICT or SET NULL per migration policy. |
| `promoted_at` | `TIMESTAMPTZ` NULL | |
| `promotion_idempotency_key` | `VARCHAR(128)` NULL | Client/server idempotency token (§5). |
| `discarded_at` | `TIMESTAMPTZ` NULL | |
| `discard_reason` | `TEXT` NULL | Optional operator note. |
| `created_at` | `TIMESTAMPTZ` NOT NULL | |
| `updated_at` | `TIMESTAMPTZ` NOT NULL | |

**Constraints (proposed):**

- `UNIQUE (tenant_id, id)` — standard composite pattern if `id` is surrogate elsewhere.
- `UNIQUE (tenant_id, promoted_load_id)` WHERE `promoted_load_id IS NOT NULL` — one load per promotion outcome.
- `UNIQUE (tenant_id, promotion_idempotency_key)` WHERE `promotion_idempotency_key IS NOT NULL` — duplicate promote returns same load.
- Check: `status` in allowed enum set.
- Check: terminal states (`promoted`, `discarded`, `expired`) immutable except audit columns.

**Indexes:**

- `(tenant_id, status, expires_at)` — expiry job.
- `(tenant_id, created_by_platform_user_id, updated_at DESC)` — resume/list.
- `(tenant_id, email_thread_id)` — intake lookup (partial: thread not null).

### 1.2 Versioned `draft_json`

- **`draft_schema_version`** integer; bump when field contract changes. Server rejects PATCH if client sends a **higher** version than supported (400 `DRAFT_SCHEMA_VERSION_UNSUPPORTED`).
- **PATCH semantics (locked):** **deep merge** at the top level of `draft_json` — omitted keys are preserved; `null` on a key **clears** that key if the schema allows null. **Not** full replacement of the document. Arrays (e.g. `stops`, `references`) follow explicit rules in schema v1: **replace entire array** when the key is present in PATCH; omit key to leave unchanged.
- **Loose validation on save** (types, max lengths, allowed keys).
- **Strict validation at promote** — shared Mark Ready validator **plus** full commercial create contract.
- **Single mapping path:** shape aligned with `LoadDocumentParseResponse` / workspace hydration (no second mapper).
- **Stale parse protection:**
  - On **PDF replace** (`PUT …/pdf`): set `accepted_parse_json = NULL`, clear `accepted_parse_pdf_sha256`, bump `concurrency_version`; client must re-parse or re-accept.
  - On PATCH touching **parse-sensitive fields** (broker ref, stops, rate, references — enumerated in schema): clear `accepted_parse_json` unless request includes `reconfirm_parse_acceptance: true` with matching `accepted_parse_pdf_sha256`.
  - Response includes `parse_acceptance_valid: boolean` (derived: accepted parse present and sha matches current `pdf_sha256`).

### 1.3 Table: `load_commercial_evidence` (new, at promotion)

Immutable record after promotion (§4). Not TTL’d.

| Column | Type | Notes |
|--------|------|--------|
| `id` | `BIGSERIAL` | |
| `tenant_id` | `INTEGER` NOT NULL | |
| `load_id` | `INTEGER` NOT NULL | FK `loads`; UNIQUE `(tenant_id, load_id, evidence_kind)` if one RC per load. |
| `evidence_kind` | `VARCHAR(32)` | e.g. `rate_confirmation_pdf`. |
| `file_sha256` | `CHAR(64)` NOT NULL | |
| `storage_key` | `TEXT` NOT NULL | **Same object key** as workspace draft at promote (§4); retention class permanent. |
| `retention_class` | `VARCHAR(16)` NOT NULL | Always `commercial_permanent`; excluded from TTL sweeper. |
| `filename` | `TEXT` | |
| `accepted_parse_json` | `JSONB` NOT NULL | Frozen at promotion. |
| `parse_schema_version` | `VARCHAR(64)` | |
| `workspace_draft_id` | `UUID` NULL | Lineage to workspace draft. |
| `promoted_by_platform_user_id` | `UUID` | |
| `promoted_at` | `TIMESTAMPTZ` NOT NULL | |

No UPDATE of `storage_key` / `accepted_parse_json` after insert (append-only corrections via new audit events, not row overwrite).

### 1.4 Ownership

- **Tenant:** all rows scoped by `tenant_id` + session tenant resolution (existing middleware).
- **User:** `created_by` / `updated_by` platform user UUID; RBAC same as Load workspace (tenant admin vs dispatcher — exact capability names TBD in implementation checkpoint).
- **No cookie persistence** for PDF or draft body (owner rule).

---

## 2. Draft APIs

Base path (sketch): `/api/v1/load-workspace-drafts`. See OpenAPI file.

| Operation | Method | Purpose |
|-----------|--------|---------|
| Create | `POST /` | Empty or from intake thread; optional initial PDF upload. |
| Save/update | `PATCH /{draft_id}` | `expected_concurrency_version` + partial `draft_json`; optional merge strategy documented. |
| List | `GET /` | Paginated; filter `status=active` (draft only), `mine`, `email_thread_id`. **Never** mixed into `GET /loads`. |
| Retrieve | `GET /{draft_id}` | Resume across devices. |
| Replace PDF | `PUT /{draft_id}/pdf` | `expected_concurrency_version` + file; new bytes → **new** per-draft storage key (§4); invalidates accepted parse. |
| PDF preview | `GET /{draft_id}/pdf` | Authenticated **stream/download** for left-pane review; **no** `storage_key` in response (§2.1). |
| Discard | `POST /{draft_id}/discard` | `expected_concurrency_version`; terminal `discarded`; storage cleanup (§4). |
| Promote | `POST /{draft_id}/promote` | `expected_concurrency_version` + `Idempotency-Key`; creates Load **`ready`** (§5). |

### 2.1 PDF preview (verification UX)

- **GET** `/load-workspace-drafts/{draft_id}/pdf` returns `application/pdf` (or 404 if no PDF).
- Authorization: same tenant + draft read capability as GET draft.
- **Never** expose internal `pdf_storage_key` or bucket paths in JSON or headers (use opaque draft id only).
- UI: **left = PDF stream**, **right = editable fields** (existing workspace form); unchanged parser rules for `POST /loads/parse-document`.

**Not in scope for workspace:** Trip assignment, mark-ready on `loads` for new flow (promote subsumes). Legacy `POST /loads/{id}/mark-ready` remains for **existing** `loads.status=draft` rows until retired.

---

## 3. State machine and locking

### 3.1 Allowed transitions (terminal states have **no** outbound edges)

| From | To | Trigger |
|------|-----|---------|
| `draft` | `discarded` | Discard (operator) |
| `draft` | `expired` | Expiry job (`expires_at` passed, status still `draft`) |
| `draft` | `promoting` | Promote started (DB commit of state change) |
| `promoting` | `promoted` | Promote success (load + evidence + links committed) |
| `promoting` | `draft` | Promote **failed** before load commit (transient error; audit `promote_failed`) |
| `promoting` | `discarded` | Promote **failed** with non-retryable validation (optional; or stay `draft` — product: prefer **`draft`**) |

**Terminal (immutable `status`):** `promoted`, `discarded`, `expired`.

```
  draft ──discard──► discarded (terminal)
    │
    ├──expiry job──► expired (terminal)
    │
    └──promote start──► promoting ──success──► promoted (terminal)
                              │
                              └──failure (no load row)──► draft
```

### 3.2 Locking

All mutating handlers and the expiry worker:

```sql
SELECT ... FROM load_workspace_drafts
WHERE tenant_id = :t AND id = :id
FOR UPDATE;
```

| Operation | Lock | `expected_concurrency_version` | 409 codes |
|-----------|------|-------------------------------|-----------|
| **PATCH save** | required; status = `draft` | required | `LOAD_WORKSPACE_DRAFT_VERSION_CONFLICT`, `LOAD_WORKSPACE_DRAFT_NOT_EDITABLE` |
| **PUT pdf** | required; status = `draft` | required | same |
| **Discard** | required; status = `draft` | required | same |
| **Promote** | required; `draft`→`promoting` then work | required | same + `LOAD_WORKSPACE_PROMOTE_IN_FLIGHT` |
| **Expiry job** | `FOR UPDATE SKIP LOCKED`; only `draft` + expired | n/a | n/a (never touches `promoting`) |

**409 response shape (all conflicts):** JSON `detail.code`, `detail.message`, optional `server_snapshot` (draft) or `promoted_load_id` when idempotent replay.

### 3.3 Promote vs expiry race

1. Expiry SELECT: `status = 'draft' AND expires_at < now()` only — **never** `promoting`.
2. Promote: lock row; if `draft`, set `promoting` and commit (or hold in txn until end — either way expiry cannot select row).
3. While `promoting`, expiry and discard are rejected (`NOT_EDITABLE`).
4. **Object retention:** before any TTL delete, check `pdf_retention_class = commercial_permanent` OR evidence row references `storage_key` — **skip delete**.

### 3.4 Crash recovery (no duplicate official Loads)

| Stuck state | Detection | Recovery |
|-------------|-----------|----------|
| `promoting` + `promoted_load_id` NULL, no load with `promotion_idempotency_key` | Startup / sweeper | Resume promote or roll back to `draft` if no load insert marker |
| `promoting` + `promoted_load_id` set | Partial commit | Set `promoted`; idempotent clients get 200 |
| `promoted` + duplicate idempotency retry | Unique constraints | Return existing load — **never** second insert |
| Load row exists, draft not `promoted` | Orphan guard | Complete draft→`promoted` link or compensating audit (manual ops only) |

**Invariant:** at most **one** `loads.id` per `load_workspace_drafts.id` via `UNIQUE (tenant_id, promoted_load_id)` and idempotency unique index.

### 3.5 Storage vs DB (promotion)

- Use **verified existing** object storage (`app.core.storage`: `resolve_storage_path` / configured `storage_provider` — same as Load Lab and fuel manual receipt bytes).
- **No PDF copy or move inside the DB transaction.** Bytes stay at the **same `storage_key`**.
- **Inside one DB transaction on promote:** insert `loads` (ready), stops, `load_commercial_evidence` (same `storage_key`, `retention_class=commercial_permanent`), flip draft `pdf_retention_class` to `commercial_permanent`, set `status=promoted`, `promoted_load_id`, email/QR links.
- **After commit:** TTL sweeper must ignore keys with `commercial_permanent`. Old keys from **PDF replace** on same draft are eligible for orphan cleanup only when no row references them.

---

## 4. PDF retention and storage safety

### 4.1 Object ownership model

| Concept | Rule |
|---------|------|
| **Key layout** | `load_workspace_drafts/tenant_{tenant_id}/draft_{draft_id}/{upload_uuid}.pdf` — **one active key per draft**; replace creates **new** key, marks previous key orphaned after commit. |
| **Ownership** | Tenant-scoped; draft row owns key while `workspace_ttl`. |
| **Retention class** | `workspace_ttl` (expiry/discard eligible) vs `commercial_permanent` (evidence + promoted draft; **never** TTL). |
| **Shared objects** | **Forbidden** across drafts (no Load-Lab-style `/{sha256}/` sharing for workspace lifecycle). |

### 4.2 SHA-256

- Stored on draft and copied to evidence at promote (same bytes, same hash).

### 4.3 PDF replace

1. `FOR UPDATE` draft; CAS; status `draft`.
2. Write **new** object via existing storage adapter; update `pdf_storage_key`, `pdf_sha256`, invalidate parse acceptance (§1.2).
3. Decrement registry for old key; async delete old object if unreferenced after grace period.

### 4.4 Discard / expiry cleanup

Delete object **only if**:

- `pdf_retention_class = workspace_ttl`, AND
- draft is `discarded` or `expired`, AND
- no `load_commercial_evidence.storage_key` equals this key, AND
- optional `storage_object_refs.ref_count = 0`.

**Promoted paths:** evidence + `commercial_permanent` ⇒ **never** enter TTL cleanup.

### 4.5 Orphan / crash safety

- Sweeper: keys in storage without DB reference after grace → delete (metrics + log).
- **Promote/expiry race:** retention class flip committed with evidence ⇒ expiry cannot delete.
- **Process crash mid-promote:** recovery table §3.4; object remains until explicit orphan policy.

---

## 5. Promotion contract

### 5.1 Validation

- Extract **`validate_load_ready_prerequisites(payload)`** from `mark_load_ready()` (broker, `broker_load_reference`, pickup + delivery/drop stops) — **single function** called by:
  - `POST /loads/{id}/mark-ready` (legacy DB drafts)
  - `POST /load-workspace-drafts/{id}/promote` (workspace)

Do not duplicate rules.

### 5.2 Create Load as `ready`

Promotion **must not** insert `status=draft`. Flow:

1. Validate draft_json strictly.
2. `create_load_from_promotion(...)` with `status=ready` (new code path; **not** generic `create_load` which forces draft).
3. Allocate `load_number` (same uniqueness rules as today).
4. Insert stops from draft_json.
5. Insert `load_commercial_evidence`.
6. Write audit: `workspace_draft_promoted`, `load_created`, field snapshot.

Issue 3: generic PATCH must still not set `ready`; only mark-ready and promote endpoints.

### 5.3 Idempotency and one Load per draft

| Scenario | Behavior |
|----------|----------|
| **Same `Idempotency-Key` retry** (network) | 200 + same `load` + `promoted_load_id`; no second insert. |
| **Different key retry** while `promoted` | 409 `LOAD_WORKSPACE_ALREADY_PROMOTED` + existing load id in body. |
| **Different key** while `draft` | 409 unless first key unused — only one successful promote per draft. |
| **Promote on `expired` / `discarded`** | 409 `LOAD_WORKSPACE_DRAFT_NOT_EDITABLE`. |
| **Promote while `promoting`** (other client) | 409 `LOAD_WORKSPACE_PROMOTE_IN_FLIGHT`. |
| **Failure after `promoting`, no load row** | Revert to `draft`; same idempotency key may retry. |
| **Failure after load insert** | Commit `promoted` + load; retries with same key return 200. |

**Guarantees:**

- `UNIQUE (tenant_id, id)` on drafts; `UNIQUE (tenant_id, promoted_load_id)` when not null.
- `UNIQUE (tenant_id, promotion_idempotency_key)` when not null.
- At most **one** official `loads` row per workspace draft id.

Header: **`Idempotency-Key`** required on promote (max 128 chars).

### 5.4 Email and QR link transfer (same DB transaction as load create)

**Before promote (intake redesign):**

- `email_threads.workspace_draft_id` → UUID (nullable); **`linked_load_id` NULL** until promote.
- `email_intake_qr_extractions.workspace_draft_id` optional FK; **`linked_load_id` NULL** until promote.
- Email messages, attachments, `detail_json`, guarded_parse — **unchanged** (evidence preserved).

**On promote** (lock draft `FOR UPDATE`, lock thread `FOR UPDATE` if `email_thread_id` set):

- Insert load (ready) + evidence; set `email_threads.linked_load_id`, clear `workspace_draft_id`.
- Update QR rows for thread/attachment lineage: set `linked_load_id`, clear `workspace_draft_id`.
- **No new commercial Load** on “create from thread” — only workspace draft until promote.

**Legacy intake loads:** existing `linked_load_id` rows are **not** auto-migrated; classification §9 only.

### 5.5 Duplicate prevention

- Business: duplicate RC checks (`find_duplicate_linked_load_for_thread_pdf_content`) run **before** promote or flag `review_required` on draft_json.
- Technical: idempotency key + unique promotion constraints.

---

## 6. Email intake

### 6.1 Stop creating unwanted commercial drafts

Replace `create_draft_load_from_review_thread` **load insert** with:

1. Create **`load_workspace_draft`** (`source_channel=email_intake`, `email_thread_id`).
2. Copy attachment bytes into **workspace** storage key via existing storage adapter (intake may **read** from `email_message_attachments` store; workspace owns its key — not shared SHA pool).
3. Set `email_threads.workspace_draft_id`; **`linked_load_id` stays NULL**.

### 6.2 Ownership rules

| Artifact | Before promote | After promote |
|----------|----------------|---------------|
| Thread | `workspace_draft_id` set | `linked_load_id` set; `workspace_draft_id` cleared |
| QR extractions | `workspace_draft_id` optional | `linked_load_id` set |
| Attachments / messages | Immutable history | Unchanged |
| Commercial Load | **Does not exist** | `ready` via promote only |

### 6.3 Workflow

```
Thread in review → Create workspace draft → Operator edits (draft route + GET …/pdf)
→ Promote → Load ready + thread.linked_load_id + permanent evidence (same storage key)
```

**Route sketch:** `/loads/workspace/{draftId}` — must not use `/loads/{loadId}` until promoted.

---

## 7. Trip eligibility

### 7.1 Ready-only (new membership)

In `_insert_trip_load_row` (and any still-reachable `dispatch_trips._upsert_trip_and_membership`):

- After locking load: `if load.status != 'ready':` → 409 `LOAD_NOT_READY_FOR_TRIP`.
- Workspace drafts have **no** `loads.id` — trip APIs unchanged for them (404 on fake id).

Closes MASTER **I12** for new writes.

### 7.2 Legacy writers

- `ensure_active_trip_for_freight_load`: **not** called from HTTP routers today; confirm via repo-wide search before release. If any script calls it, add same gate or deprecate.
- **Existing** `trip_loads` where load is `draft`: **do not auto-remove**. Report count per tenant; enforce forward-only.

### 7.3 Dispatch UI

No Kanban redesign (owner hold). Board already excludes `draft` loads from `list_loads_for_board`.

---

## 8. Cancellation

Official loads are **never physically deleted** (owner + Issue 5 interim guard on `main`). Workspace **discard** ≠ Load cancel.

### 8.1 `POST /loads/{id}/cancel` (future)

- Body: `reason` (required), `expected_concurrency_version`.
- Set `loads.status = cancelled`; `cancelled_at`, `cancelled_by`, `cancel_reason` (columns TBD).
- Mandatory audit event.

### 8.2 Restrictions by operational / financial state

| Load situation | Cancel allowed? | Trip / ops | Payroll / AR |
|----------------|-----------------|------------|--------------|
| **Ready, not on any Trip** | Yes (default) | N/A | Block **new** accruals from this load after cancel |
| **On planned Trip only** | Yes with warning | Do not auto-remove TripLoad; operator removes or cancels trip per Trip rules | Block new accruals |
| **On in-progress Trip** | **No** (409) unless approved exception | Must complete/recover/reassign per Trip playbook — not silent load cancel | No new accruals |
| **On completed Trip** | **No** for ordinary cancel | Historical trip record stands | No reversal |
| **Invoiced (AR posted)** | **No** | — | No automatic invoice void; separate AR workflow |
| **Paid / settled** (`pay_run_items` posted) | **No** | — | **No** deletion or auto-reversal of pay lines; preserve history |

**TONU / cancellation pay:** explicit approved payable (e.g. `PayEntry` with approval flag) — **never** inferred from `cancelled` status alone.

**No automatic reversal** of historical financial entries on cancel.

---

## 9. Existing `loads.status = draft` rows

### 9.1 Read-only classification (before policy)

Per tenant, bucket:

| Bucket | Criteria (indicative) |
|--------|------------------------|
| A — Empty / idle | No trip_loads; no payroll metadata `load_id`; no linked email thread; minimal stops/refs |
| B — Promotable | Would pass mark-ready validation today |
| C — Referenced | Any trip_load, payroll, email link, duplicate-of, custody |
| D — Intake-stuck | `review_required`, duplicate flags |

SQL inventory script (read-only) — run in container with owner approval; no bulk delete.

### 9.2 Transition (legacy policy — locked)

- **No changing existing `loads.id`.**
- **No bulk delete** of legacy `loads.status=draft` rows.
- **No auto-promotion** of legacy drafts into workspace or ready without operator action.
- Options per bucket: leave as-is; operator **mark-ready** (legacy); operator **cancel** (when built); manual review only.
- New workspace flow must not add junk via `/loads/new` or intake once DW-3 ships.

---

## 10. Implementation checkpoints

Each checkpoint: **independent commit**, tests, **STOP for ChatGPT review**, no merge to `main` without owner.

| # | Segment | Deliverables | Required tests |
|---|---------|--------------|----------------|
| 1 | Schema + models (draft + evidence) | Alembic tenant migration | Migration smoke; model tenant isolation |
| 2 | Storage adapter + retention class | Service + orphan sweeper (no copy on promote) | Unit: promote flips retention; TTL never deletes permanent |
| 3 | Draft CRUD APIs | Router + auth | Integration: create/save/CAS/disc/list |
| 4 | PDF upload/replace + GET preview | PUT pdf, GET pdf stream | Integration: sha256, CAS, parse invalidation, no key leak |
| 5 | Promote + validation extract | Shared validator with mark-ready | Promote → load `ready`; idempotency; evidence row |
| 6 | Email intake → workspace | Replace load insert | Thread linked to draft; no new load on create |
| 7 | I12 trip gate | `_insert_trip_load_row` | Draft load cannot join trip; ready can |
| 8 | Expiry job | Worker | Expiry vs promote race test (two sessions) |
| 9 | Cancel load | Service + API | No new payroll accrual; audit |
| 10 | Legacy draft inventory + UI routes | Read-only SQL + UI | No regression Issue 3/5 tests |

**Explicitly shelved:** permanent guarded hard-delete (Issue 5 product end state). Interim 409 remains until cancel ships.

**Parallel workstreams (not draft UI):** payroll DDL/reference contract; `create_planned_trip` lock-order fix.

---

## References (code today)

- `app/services/loads.py` — `create_load`, `mark_load_ready`, DELETE guard
- `app/services/email_threads.py` — `create_draft_load_from_review_thread`
- `app/services/trips.py` — `_insert_trip_load_row`, `create_planned_trip`
- `app/services/dispatch_trips.py` — `_upsert_trip_and_membership` (latent path)
- `app/models/fuel.py` — `FuelManualEntryStage` (staging pattern)
- `app/core/storage.py` — existing object persistence (`resolve_storage_path`, `storage_provider`)
- `app/services/load_lab.py` — separate PDF path (do not share workspace deletion semantics)
- `POST /loads/parse-document` — hydration only, no PDF persist

---

*End of design specification.*
