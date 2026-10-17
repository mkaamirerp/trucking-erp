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

## RBAC — Casbin permission engine

**Status:** TODO — engine selected for the start of RBAC work; implementation not started.

**Decision (2026-10-14):** Start with Casbin (Python/PyCasbin) as TruckERP's backend permission engine. Keep the existing TruckERP user-management UI, authentication, and tenant memberships; extend TruckERP with a tenant-admin Roles & Access page rather than adopting Casdoor or Keycloak.

Initial scope: database-backed role permissions; tenant-scoped member role assignments; a shared permission-check interface for protected backend operations; fixed starter roles and a read-only permission view; audited role changes; last-admin protection; explicit role-assignment permissions; immediate enforcement of role changes and policy refresh across workers. Custom tenant roles can follow later.

Before implementation, inspect current authentication, access levels, membership tables, callers, and tenant scoping. Define the permission catalog and migration from FULL_ACCESS/READ_ONLY, and follow AGENTS.md approval and regression gates for shared contracts. Keep record-level tenant/ownership scoping and financial workflow validation in TruckERP. Test cross-tenant denial, role changes, privilege escalation, and last-admin protection.
