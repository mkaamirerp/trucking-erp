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
| `pdf_storage_key` | `TEXT` NULL | **Per-draft** object key (§4); never shared SHA path without refcount. |
| `pdf_sha256` | `CHAR(64)` NULL | Hex SHA-256 of current PDF bytes. |
| `pdf_filename` | `TEXT` NULL | Original filename for display. |
| `pdf_size_bytes` | `BIGINT` NULL | |
| `accepted_parse_json` | `JSONB` NULL | Last operator-accepted parse snapshot (subset of `LoadDocumentParseResponse`). |
| `accepted_parse_schema_version` | `VARCHAR(64)` NULL | Parser/schema pin at acceptance. |
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

- **`draft_schema_version`** integer; bump when field contract changes.
- **Loose validation on save** (types, max lengths, allowed keys); reject unknown critical keys only at schema max version.
- **Strict validation at promote** — same business rules as Mark Ready **plus** full commercial field contract for create.
- **Single mapping path:** persist shape aligned with `LoadDocumentParseResponse` / `applyLoadDocumentParseResponse` hydration (no second ad-hoc mapper).
- Include optional `provenance`: `last_parse_job_id`, `email_attachment_id`, `parser_version` (metadata only).

### 1.3 Table: `load_commercial_evidence` (new, at promotion)

Immutable record after promotion (§4). Not TTL’d.

| Column | Type | Notes |
|--------|------|--------|
| `id` | `BIGSERIAL` | |
| `tenant_id` | `INTEGER` NOT NULL | |
| `load_id` | `INTEGER` NOT NULL | FK `loads`; UNIQUE `(tenant_id, load_id, evidence_kind)` if one RC per load. |
| `evidence_kind` | `VARCHAR(32)` | e.g. `rate_confirmation_pdf`. |
| `file_sha256` | `CHAR(64)` NOT NULL | |
| `storage_key` | `TEXT` NOT NULL | **Permanent** key (copy or re-key at promote — §4). |
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
| Replace PDF | `PUT /{draft_id}/pdf` | New bytes → new per-draft storage key; update sha256; optional re-parse trigger (parser unchanged). |
| Discard | `POST /{draft_id}/discard` | Terminal `discarded`; schedule storage delete (§4). |
| Promote | `POST /{draft_id}/promote` | Terminal `promoted`; creates Load **`ready`** (§5). |

**Not in scope for workspace:** Trip assignment, mark-ready on `loads` for new flow (promote subsumes). Legacy `POST /loads/{id}/mark-ready` remains for **existing** `loads.status=draft` rows until retired.

---

## 3. State machine and locking

### 3.1 States

```
                    ┌─────────────┐
                    │   draft     │  (active workspace)
                    └──────┬──────┘
           discard         │         promote (start)
              │            │              │
              v            │              v
       ┌────────────┐      │       ┌─────────────┐
       │ discarded  │      │       │ promoting   │  (short-lived)
       └────────────┘      │       └──────┬──────┘
              │            │              │
     expiry job            │         success │ failure
              │            │              v
              v            │       ┌─────────────┐
       ┌────────────┐      │       │  promoted   │  (terminal)
       │  expired   │      │       └─────────────┘
       └────────────┘      │
                            └── (no transition from terminal states)
```

- **`draft`:** editable; subject to TTL.
- **`promoting`:** promote in flight; **reject** save, discard, second promote, expiry delete of PDF until resolved.
- **`promoted` / `discarded` / `expired`:** terminal; read-only except admin audit.

### 3.2 Locking

All mutating handlers and the expiry worker:

```sql
SELECT ... FROM load_workspace_drafts
WHERE tenant_id = :t AND id = :id
FOR UPDATE;
```

| Operation | Lock | Conflict behavior |
|-----------|------|-------------------|
| **Save** | `FOR UPDATE`; status must be `draft` | 409 if `promoting` or terminal; 409 CAS if `concurrency_version` mismatch. |
| **Promote** | `FOR UPDATE`; `draft` → `promoting` in same txn | Second promote with same idempotency key → 200 + same `load_id`. Different key while `promoting` → 409. |
| **Discard** | `FOR UPDATE`; status `draft` only | 409 if promoting/promoted. |
| **Expiry job** | `FOR UPDATE SKIP LOCKED` batch | Skip `promoting`; only `draft` past `expires_at`. |

### 3.3 Promote vs expiry race

Critical case: expiry job vs promote.

1. Promote takes lock, sets `promoting`, extends `expires_at` optionally or ignores expiry while `promoting`.
2. Expiry job selects only `status = 'draft' AND expires_at < now()`.
3. On promote failure, revert `promoting` → `draft` or → `discarded` with error audit (implementation choice: prefer **revert to draft** if load create failed transiently).

### 3.4 Storage vs DB atomicity

- DB transaction **cannot** include object store.
- **Promote:** (1) lock draft → `promoting`; (2) validate; (3) insert `loads` + stops + evidence + links; (4) **record permanent `storage_key`** on evidence (copy bytes to `load_evidence/...` or mark key as promoted — no delete from draft bucket until txn commits); (5) `promoted` + `promoted_load_id`; (6) commit; (7) async delete draft-stage object (best-effort).
- **Failure after load insert:** idempotency key returns existing load; do not orphan duplicate loads.

---

## 4. PDF retention

### 4.1 Per-draft storage key

Pattern (example):

`load_workspace_drafts/tenant_{tenant_id}/draft_{draft_id}/{uuid}.pdf`

**Do not** reuse Load Lab’s `load_lab_uploads/tenant_{id}/{sha256}/` for mutable draft lifecycle (shared deletion risk).

### 4.2 SHA-256

- Compute on upload/replace; store on draft row.
- At promotion, copy to evidence path e.g. `load_commercial_evidence/tenant_{tenant_id}/load_{load_id}/{sha256}.pdf` (dedupe safe at **load** level, not draft).

### 4.3 After promotion

- Evidence row holds permanent key; **no TTL**.
- Draft row may clear `pdf_storage_key` after successful promote or leave for audit lineage (implementation: null draft key after copy verified).

### 4.4 Discard / expiry cleanup

- Delete object **only** when no `load_commercial_evidence.storage_key` references it and refcount = 0.
- Refcount table optional: `(tenant_id, storage_key, ref_count)` incremented on draft create/replace, decremented on discard/expiry/promote-after-copy.

### 4.5 Recovery

- If DB says `discarded` but object remains, sweeper deletes orphan keys older than grace period.
- If promote committed but copy failed, draft stays `promoting` or rolls back — **no `promoted_load_id`** until evidence insert succeeds (or evidence insert mandatory in same txn with key pointing to already-copied object).

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

### 5.3 Idempotency

- Header: `Idempotency-Key` (or body field) stored in `promotion_idempotency_key`.
- Retry with same key: return **same** `LoadResponse` + 200.
- Unique `(tenant_id, promotion_idempotency_key)` and `(tenant_id, promoted_load_id)`.

### 5.4 Email and QR link transfer (same DB transaction as load create)

Under **`FOR UPDATE`** on draft and relevant thread:

- Set `email_threads.linked_load_id` = new `loads.id` (was null or pointed to deprecated intake load — **intake must not create load** going forward).
- Update `email_intake_qr_extractions.linked_load_id` for rows tied to `email_thread_id` / attachment lineage.
- Issue 5 lesson: FK `ON DELETE SET NULL` on loads does not replace need for **ordered locking** when re-linking.

Optional: `email_thread.workspace_draft_id` until promote (schema addition TBD).

### 5.5 Duplicate prevention

- Business: duplicate RC checks (`find_duplicate_linked_load_for_thread_pdf_content`) run **before** promote or flag `review_required` on draft_json.
- Technical: idempotency key + unique promotion constraints.

---

## 6. Email intake

### 6.1 Stop creating unwanted commercial drafts

Replace `create_draft_load_from_review_thread` **load insert** with:

1. Create **`load_workspace_draft`** (`source_channel=email_intake`, `email_thread_id`).
2. Attach PDF from thread/attachment into per-draft storage (or reference attachment fetch + copy).
3. Set thread state **linked to workspace draft** (new column or `intake_bucket` + draft id) — **not** `linked_load_id` until promote.

### 6.2 Preserve history

- **Do not delete** email messages, attachments, or review `detail_json`.
- QR extractions remain on attachment; link to draft until promote moves `linked_load_id`.

### 6.3 Workflow

```
Thread in review → Create workspace draft → Operator edits in Load Workspace (draft id route)
→ Promote → official Load ready + thread.linked_load_id
```

**Route sketch:** `/loads/workspace/{draftId}` or query param — product TBD; must not use `/loads/{loadId}` until promoted.

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

New commercial loads (post-promote) are **never physically deleted** (owner + Issue 5 guard).

### 8.1 `POST /loads/{id}/cancel` (future)

- Body: `reason` (required), `expected_concurrency_version`.
- Set `loads.status = cancelled`; record `cancelled_at`, `cancelled_by`, `cancel_reason` (columns TBD).
- Audit event mandatory.

### 8.2 Restrictions

- **Trip:** cancel does not auto-cancel in-progress trips without explicit product rules (MASTER §2).
- **Payroll:** pay-generating services **must** exclude `cancelled` loads from new accruals (service-layer, not UI).
- **Posted history:** immutable; no delete of `pay_run_items`.
- **TONU / approved cancellation pay:** explicit `PayEntry` (or equivalent) with approval flag — never inferred from status alone.

Workspace **discard** is not Load cancel — no `loads` row.

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

### 9.2 Transition

- **No changing existing `loads.id`.**
- Options per bucket: leave as-is; operator promote via legacy mark-ready; operator cancel (once built); manual migration to “legacy draft” flag — **no bulk physical delete**.
- New workspace flow: **new rows** should not add to bucket A via `/loads/new` or intake.

---

## 10. Implementation checkpoints

Each checkpoint: **independent commit**, tests, **STOP for ChatGPT review**, no merge to `main` without owner.

| # | Segment | Deliverables | Required tests |
|---|---------|--------------|----------------|
| 1 | Schema + models (draft + evidence) | Alembic tenant migration | Migration smoke; model tenant isolation |
| 2 | Storage adapter + per-draft keys | Service + refcount or copy-on-promote | Unit: delete does not cross drafts |
| 3 | Draft CRUD APIs | Router + auth | Integration: create/save/CAS/disc/list |
| 4 | PDF upload/replace | PUT pdf | Integration: sha256, replace, parse hook optional |
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
- `app/services/load_lab.py` — PDF persistence (do not share deletion semantics)
- `POST /loads/parse-document` — hydration only, no PDF persist

---

*End of design specification.*
