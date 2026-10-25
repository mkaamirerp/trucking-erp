# EQ01 — Equipment attachment tenant migration targets (schema checkpoint)

**Status:** Code proposed on `gpt-review`; migration **NOT AUTHORIZED**. There is no
physical-state writer, hook/drop API, or deployment in this checkpoint. Do not
promote schema completion into an equipment carry-over acceptance claim.

## Two mutually exclusive tenant lineages

The EQ01 repository migration heads are:

| Migration | Parent | Purpose |
|---|---|---|
| `eq01_equipment_attachments_fmp` | `ln01_load_number_periods_fmp` | FMP/DW-1 tenant branch |
| `eq01_equipment_attachments_x5` | `ln01_load_number_periods_x5` | x5/POD-x5 tenant branch |

Both revisions invoke **the same shared DDL**, creating
`driver_equipment_defaults` and `equipment_current_attachments`. They also
add `UNIQUE(tenant_id,id)` to `drivers` and `trailers`, so that tenant-scoped
composite FKs are valid. Truck's equivalent uniqueness already exists.

A database must **never** execute both EQ01 revisions. The resulting rows start
empty: no inferred driver/truck, trailer hooks, default-truck backfill, duty
data, or physical events are created. Existing `audit_events` is reused for
future atomic audited writes.

## How to choose an explicit target

These are **planning references only**, not authorization to migrate.

| Current tenant `alembic_version` | Potential target | Expected plan |
|---|---|---|
| `ln01_load_number_periods_fmp` (reported `tenant_demo`) | `eq01_equipment_attachments_fmp` | EQ01 FMP only |
| `fmp02_fmp_tenant_scope` | `eq01_equipment_attachments_fmp` | LN01 FMP → EQ01 FMP |
| `ln01_load_number_periods_x5` | `eq01_equipment_attachments_x5` | EQ01 x5 only |
| `i14_load_pod_evidence_x5` | `eq01_equipment_attachments_x5` | LN01 x5 → EQ01 x5 |
| `x5y6z7a8b9c0` | `eq01_equipment_attachments_x5` | POD x5 → LN01 x5 → EQ01 x5 |
| `eq01_equipment_attachments_fmp` | Same | No-op |
| `eq01_equipment_attachments_x5` | Same | No-op |
| `i14_load_pod_evidence` / `dw1d_...` | **STOP** | Do not infer FMP eligibility from DW-1 alone |

**Prohibited:** x5 target on an FMP tenant, FMP target on x5, either
sibling on a tenant already at the other sibling, `upgrade head` /
`upgrade heads` on the split graph, or applying EQ01 to an unknown lineage.
Do not reconcile the two branches by running both revisions.

## Required verification before any future approval

1. Read-only confirm the **current database name** and actual
   `alembic_version` on the target tenant, and the commit/DDL inside
   the running `truckerp-api` container. A host checkout alone is not enough.
2. Validate `alembic -c alembic_tenant.ini heads`: exactly the EQ01 sibling
   pair and no unexpected third head.
3. Run `tests/test_eq01_migration_graph.py`, existing LN01/POD graph
   tests, EQ01 schema tests, and related People/Fleet/Fuel tests.
4. Review pending revisions with `scripts/tenant_revision_plan.py`, require
   the one-step FMP plan for demo, and run the existing **read-only**
   `scripts/tenant_migrate_preflight.sh` in its authoritative container.
5. Inspect possible preexisting conflicting table/constraint names, database
   privileges, table-lock timing, and rollback impacts.
6. Obtain **separate owner approval to run a pinned migration on a disposable
   tenant first**, observe tenant-isolated FK and unique-claim failures, then
   ask for demo migration approval. Neither approval grants production deploy.

The operator path, **after separately authorized**, remains:
`bash scripts/tenant_upgrade_revision.sh <explicit-eq01-revision>` inside the
API container. `scripts/tenant_upgrade_head.sh` must continue to refuse
the two-head graph. No migrations are performed by this document.

**Rollback caution:** the EQ01 downgrade drops equipment tables; once
physical equipment records exist, a destructive downgrade is not an
acceptable production rollback plan. Prefer application rollback with
schema retained until reviewed.

See `docs/load_trip/MASTER.md`, `docs/load_trip/POD_MIGRATION_TARGETS.md`,
`AGENTS.md` and `.cursor/rules/owner-product-rules.mdc`.
