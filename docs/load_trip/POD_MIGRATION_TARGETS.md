# I14 POD migration targets

The tenant graph has two approved heads until a later owner-approved merge:

- `i14_load_pod_evidence` — child of `dw1c_composite_fk_set_null_optional_columns`
- `i14_load_pod_evidence_x5` — child of `x5y6z7a8b9c0`

Both revisions create `load_pod_evidence`. A database must run only one of them.

`alembic upgrade head` is refused by `scripts/tenant_upgrade_head.sh` while both heads exist. New tenant provisioning uses `i14_load_pod_evidence_x5` (`tenant_alembic_target_rev`), which follows the x5 line and does not apply DW-1.

## Which revision to run

| Current `alembic_version` | Command | DW-1 |
|---|---|---|
| `x5y6z7a8b9c0` (production) | `bash scripts/tenant_upgrade_revision.sh i14_load_pod_evidence_x5` | No |
| `dw1c_composite_fk_set_null_optional_columns` | `bash scripts/tenant_upgrade_revision.sh i14_load_pod_evidence` | Already applied |
| `i14_load_pod_evidence` | Do not upgrade. Do not run `i14_load_pod_evidence_x5`. | Already applied |
| New empty database | Provisioning runs `upgrade i14_load_pod_evidence_x5` | No |

Run the revision script inside `truckerp-api` at `/app` with `ALEMBIC_TENANT_DATABASE_URL` set. It runs preflight, then refuses a plan that would execute both POD revisions.

Do not run production migrations from this document.
