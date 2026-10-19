# TruckERP TODO

## AGY architecture audit + API runtime safety — implementation handoff (2026-10-17)

**Status:** AUDIT / PLAN SAVED; code changes, migrations, deployment and implementation commits remain **not started** in this documentation update. AGY quota was exhausted before its revised security plan could be executed.

**Implementation handoff / prioritized work register:** [docs/AGY_AUDIT_IMPLEMENTATION_HANDOFF.md](docs/AGY_AUDIT_IMPLEMENTATION_HANDOFF.md)  
**Original AGY audit (historical evidence):** [docs/module_onboarding_audit.md](docs/module_onboarding_audit.md) — [frozen publication](https://github.com/mkaamirerp/trucking-erp/blob/19822b3a9b95ab7f842b6112ce9d9149ab70ff9d/docs/module_onboarding_audit.md)

**Next ordered work (one bounded slice at a time):**
- [ ] **P0-A — Environment security gate:** Explicit environment-name allowlists; unknown names fail; strong JWT outside CI/test; safe password-reset/cookie fallbacks; `SSM_ENV=prod` identity and bypass checks **before platform migrations**; isolated subprocess tests. The AGY revised `api_boundary_runtime_safety_verification_plan.md` was a local plan artifact **not committed to docs/**; use the reconstructed handoff and revalidate exact diff.
- [ ] **P0-B — Read-only tenant schema/revision inventory:** Check all ACTIVE/READY tenants, actual approved Alembic targets, branch/head state, missing columns/tables and compatibility. **Do not run a fleet upgrade.** `app/scripts/tenant_fleet_upgrade_head.py` already exists, and `scripts/tenant_upgrade_head.sh` refuses multi-head `upgrade head`; do not create a duplicate or assume the audit's single-head model.
- [ ] **P0-C — Silent-green tenant safety CI:** Replace dead-path scanning with live-code coverage, explicit reviewed exceptions and negative tests that prove the gate fails on an actual violation.
- [ ] **P0-D — Schema/data propagation impact audit:** Map field ownership, relational consumers, alternate write paths, duplicated projections, and reconciliation requirements (begin People → Drivers → Dispatch/Payroll). Migration of schema **does not** automatically sync business values.
- [ ] **P1 — Provisioning READY validation, migration dry-run/backup/stop policy, Alembic metadata separation, real shared-core owner-approval gate, route/import tests.**
- [ ] **P2 / HOLD — Fuel cross-DB transaction consistency, multi-worker outbox/SSE, incremental frontend/Casbin navigation.** Do not automatically rewrite Payroll `drivers.id` FKs, bulk rename routes, delete legacy Alembic, or loosen mandatory security settings.

**STOP:** Preserve `AGENTS.md`, active Casbin and Load/Dispatch contracts. No code writes or migrations without separate owner approval. Update statuses only after evidence and regression results are recorded in the handoff.

---

## Load parser — side-by-side PDF evidence verification

**Status:** TODO — locked product requirement; implement after current GPT-5-mini / parser architecture validation.

**Design reference:** `docs/load_parser/TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md` — section **"Human verification / temporary PDF evidence review — LOCKED"**.

**Reason:** Visible source evidence is required because even a single wrong ZIP/postal code, address, appointment time, or operational reference can materially misroute or disrupt a shipment.

**Checklist:**

- [ ] Temporary two-pane review UI
- [ ] Left pane displays exact original uploaded PDF
- [ ] Right pane displays editable parsed TruckERP fields
- [ ] Preserve AI-original value when operator changes a parsed field
- [ ] Record operator correction / accepted value
- [ ] Support Save Draft from verified result
- [ ] Support Create Load from verified result
- [ ] Preserve/attach original PDF to resulting Load
- [ ] Close/remove temporary verification workspace after Save/Create
- [ ] Subsequent edits occur through normal Load page
- [ ] Original PDF remains accessible as Load evidence
- [ ] Define correction audit persistence/schema in implementation slice
- [ ] Regression test that parser output cannot silently overwrite an operator correction

Do **not** implement this UI in the current parser-architecture validation slice.

---

## Load parser — digital PDF OpenAI handoff (no duplicate page text)

**Status:** INCOMPLETE — not on `main`; do not treat as shipped.

**Intent:** For digital rate confirmations, OpenAI receives the original PDF bytes plus rules/schema; locally extracted page text stays in `raw_text` / mechanical validation but must **not** be duplicated into `document.pages` in the AI user message (see reconciliation backup `gpt_review_reconcile_20261019_0150Z` and prior `gpt-review` worktree WIP).

**Remaining before merge to `main`:** land `load_parser_openai_handoff_v2.py`, `load_document_parse_rate_con.py`, guarded + digital handoff tests; TQLRC regression; owner review. **Do not** label parser module Gold until batch results are reviewed.

---

## BVD import staging — hardening (post-rollout)

**Status:** TODO — follow-up only; do not side-track staging rollout.

**Checklist:** `docs/fuel/FUEL_BVD_STAGING_HARDENING_TODO.md`

Covers correction revert chains, malformed payloads, storage orphans, session-safe cleanup, Process retry after partial cleanup, TTL refresh, scheduled expiry purge, duplicate lookup efficiency, and related items.

---

## Fuel Card Adjustments — provider-authorized corrections

**Status:** TODO — future Fuel operationalization; do not pull into the current BVD source-review milestone.

**Design:** `docs/fuel/FUEL_CARD_ADJUSTMENTS.md`

**Implementation checklist:** `docs/fuel/FUEL_CARD_ADJUSTMENTS_TODO.md`

**Architecture reference:** `docs/fuel/FUEL_CARD_MODULE_DESIGN.md`

Core rule: a provider correction never overwrites the original provider transaction. TruckERP records a linked adjustment so the company can search a disputed invoice/transaction, capture the provider-authorized correction and evidence, and preserve the original → adjustment(s) → effective-cost audit chain.

Primary relationship:

```text
Fuel-card provider
        ↕
Fleet / company account
        ↕
TruckERP company financial history
```

This is not a driver-dispute or owner-operator-dispute workflow.

---

## Load parser — restore and verify principal load identifier label fallback

**Status:** TODO — do not implement blindly; verify against current rules/tests first.

**Context**

During EC2 worktree cleanup, an uncommitted change from the old `tmp/operational-references-slice` worktree was intentionally backed up before that worktree was removed. The working tree itself is gone, but the exact diff is preserved locally on EC2 at:

```text
~/truckerp_backups/ec2_cleanup_20260920/operational_working.diff
```

The affected function is:

```text
app/services/load_parser_mechanical_validation.py
_strip_load_reference_field_label(...)
```

### What current `main` does

Current `main` reads only:

```python
LOAD_RATE_CON_FIELD_RULES["rules"]["principal_load_identifier"].get(
    "strong_labels"
)
```

So label stripping currently depends only on `strong_labels`.

### What the backed-up uncommitted change did

The preserved diff changed the lookup to:

```python
ident = LOAD_RATE_CON_FIELD_RULES["rules"]["principal_load_identifier"]
raw_labels = ident.get("possible_labels_examples") or ident.get("strong_labels") or []
labels = [
    str(label).strip()
    for label in raw_labels
    if str(label).strip()
]
```

Important: the priority in the preserved change is:

```text
possible_labels_examples
    -> if empty/missing, fall back to strong_labels
```

It is **not** `strong_labels` first.

### Historical detail that caused confusion

The old operational worktree base was using `possible_labels_examples` only. The uncommitted change made that more defensive by falling back to `strong_labels`. Current `main`, however, now uses `strong_labels` only. Therefore there are three observed states:

```text
Old operational base:
    possible_labels_examples ONLY

Backed-up uncommitted change:
    possible_labels_examples FIRST
    -> strong_labels FALLBACK

Current main:
    strong_labels ONLY
```

Do not infer that the backed-up change should be pasted mechanically without checking the current rule contract and tests.

### Cursor task

1. Open `LOAD_RATE_CON_FIELD_RULES["rules"]["principal_load_identifier"]` and inspect the current meaning/content of:
   - `possible_labels_examples`
   - `strong_labels`
2. Inspect current tests around principal load/reference identifier discovery and `_strip_load_reference_field_label`.
3. Confirm whether the intended source-label stripping behavior is still:

```python
possible_labels_examples -> fallback to strong_labels
```

4. If yes, restore the backed-up behavior in `_strip_load_reference_field_label`.
5. Add/adjust regression tests that prove:
   - labels present in `possible_labels_examples` are stripped when followed by the allowed separator;
   - if `possible_labels_examples` is absent/empty, `strong_labels` still works;
   - glued identifiers such as `PO12345` remain untouched;
   - the change does not select a different load identifier; it only strips the leading discovery label;
   - existing rate-confirmation/load-parser fixtures still pass.
6. Run the focused load-parser tests first, then the relevant broader Load regression tests.
7. Show the exact diff and test results before committing.

### Recovery evidence

The exact preserved change can be inspected on EC2 with:

```bash
grep -n -A8 -B8 "possible_labels_examples" \
  ~/truckerp_backups/ec2_cleanup_20260920/operational_working.diff
```

Do not delete that backup until this TODO is resolved and committed to `main`.

---

## Load Parser — duplicate load / revised RC modal

**Status:** TODO — design only, not implemented.

**Design:** `docs/load_trip/MASTER.md`

On a tenant-scoped broker load number or optional barcode match, pause import and show **Possible Duplicate Load** with **Revised RC** (review differences, explicitly approve changes to existing load, preserve revision/audit history) or **Ignore** (no changes). Do not auto-reject or create a duplicate. Keep the original PDF + JSON AI parsing architecture unchanged.

---

## RBAC — Casbin authorization (`app/authz/`)

**Authority:** `docs/load_trip/MASTER.md` — *WORKSTREAM NOTE — Casbin/RBAC (paused, not superseded)*. Operational contracts: `app/authz/STARTUP_AND_ROLLBACK.md`, `app/authz/DECISION_REPORT.md`.

| Layer | Status on `main` (`3e3bdab`) |
|-------|------------------------------|
| **Implementation** | **Done (foundation + pilot code).** Casbin 1.41.0; Phase 0 loader/model/policies; capability catalog; shadow comparison; simulated decision matrix; route inventory; **default-off** Loads pilot (`CASBIN_LOAD_PILOT_ENFORCEMENT`, four `/api/v1/loads` routes). Primary landing commit: `c46490f`. |
| **Integration** | **Partial.** Pilot is wired but **off by default**; legacy role/entitlement gates remain authoritative for almost all routes. Full module enforcement and UI are not rolled out. |
| **Verification** | **Partial.** Substantial unit coverage on `main` (`tests/test_authz_phase0.py` … `test_authz_phase4c.py`, `test_authz_shadow.py`, `test_authz_matrix.py`, etc.). Live pilot-on regression and production-image proof are **open** (separate from Load Integrity F1). |
| **Future enhancements** | Tenant-admin Roles & Access UI; custom tenant roles; expand enforcement beyond Loads pilot; resolve pending cells in `DECISION_REPORT.md`; AGY P2-C frontend/navigation alignment — **product backlog**, not missing core implementation. |

**Remote branches (historical / integration candidates — do not auto-merge):**

- `origin/casbin-integration` — 16 commits not on `main` (e.g. Load audit-identity alignment, FastAPI pilot auth tests, `docs(authz)` contract notes). **Diverged below `main`** on Load/F1 (`loads.py` / router differ); needs owner replay onto current `main`, not a wholesale merge.
- `origin/casbin` — earlier Casbin line (14 commits not on `main`; largely superseded by the port in `c46490f`).
- `origin/casbin-prod-6919ec0` — isolated release `6919ec0` line + `f9c9067` production-schema Casbin candidate; not the current `main` integration target.

**Historical review markdown** (`docs/reviews/CASBIN_RBAC_*.md` in local WIP or backup) is **inspection evidence**, not a second implementation. Do not treat proposed permissions or matrix `pending` rows as “Casbin not built.”

---

## AUTH SECURITY HARDENING — PARKED

**Status:** **SECURITY AUDIT RECORDED — REMEDIATION DEFERRED** (not scheduled; not Auth Gold).

**Owning documentation:** `docs/auth/AUTH_SECURITY_REVIEW_BACKLOG.md` (findings A1–A8; **audit baseline:** § *Independent Security Review — Audit Baseline*, commit `ede7ba80d0154f39db5a4f23813b7eaceae99030`). **Architecture authority:** `docs/auth/LOGIN_IDENTITY_ARCHITECTURE_LOCK.md`.

**Rules:**

- Not currently scheduled for implementation.
- Requires **issue-by-issue owner approval** before any Auth code change.
- **Do not mix** with Load/Trip integrity remediation (0A–0D, Issue 26, parser slices, etc.).
- **Production verification pending** (cookies, reset URLs, EC2 effective config).

**Checklist (priority order — all unchecked):**

- [ ] **A1 (P1)** — Production cookie `Secure` / `SECURE_COOKIES` effective config; reset-token URL logging exposure
- [ ] **A2 (P1)** — Password-reset token consumption atomicity (concurrent reset; `session_version`)
- [ ] **A3 (P1)** — Credential sync / authority (tenant vs platform mirror) per identity lock
- [ ] **A4 (P2)** — Workspace reset routing / `tenant_id=null` on public allowlist path
- [ ] **A5 (P2)** — Logout vs JWT/refresh revocation policy
- [ ] **A6 (P2)** — bcrypt 72-byte truncation; compatibility-preserving fix
- [ ] **A7 (P3)** — JWT decode required claims (`exp`, `sub`, type, `sv`, tenant binding)
- [ ] **A8** — Invite acceptance may reactivate suspended users

---

## F1 — commercial Load insertion dedup (`a15e9ea` baseline)

**Status:** **F1 acceptance criteria met in dev (disposable clone); NOT deployed; Load Integrity Gold still open.** See `docs/load_trip/MASTER.md` F1 row.

**Evidence:** `/home/admin/backups/f1_finish_20261019T1030Z/` (matrix pass); `/home/admin/backups/f1_concurrent_dw_20261019T1047Z/` (`test_concurrent_promote_competing_idempotency_keys_one_load` + DW API 17/17).

**Payroll:** **NOT APPLICABLE** for F1 (module not implemented — no regression required).

**Finance:** **NOT APPLICABLE** for F1 — no shipped Finance code path depends on shared Load insertion (verify again when Finance posts from Loads).

**F1 complete vs Integrity Gold:** F1 covers §6 duplicate insertion + Opus §14 rows exercised in harness (DW/API/I26/I0A/I5/I12/I3/TripLoad/parser money unit). **Still outside F1:** production deploy, live JWT/Casbin certification, I14/custody/POD live acceptance, full-repo clone green, optional custody slice2 harness on disposable DB.
