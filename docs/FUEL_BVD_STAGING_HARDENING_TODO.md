# BVD import staging — hardening TODO (follow-up)

**Status:** TODO only — do **not** implement during initial staging rollout unless a item blocks the approved Upload → Review → Process / Close flow.

**Approved staging architecture (locked):** table-based temp tables (`fuel_bvd_import_stage`, `fuel_bvd_stage_row`, `fuel_bvd_stage_field_correction`); `stage_id == permanent import_id` after Process; temp files under `fuel_bvd_stage/stage/{stage_id}/`; Process is the only permanent commit boundary.

**Locked data model (do not change):**

- Permanent `fuel_bvd` = **RAW** parser extraction only.
- Reviewed owner corrections = `fuel_bvd_field_correction` (append-only history; latest wins for effective value).
- Operational value = latest correction if present, else raw `fuel_bvd` column.
- **Never** write reviewed/effective values onto raw `fuel_bvd` source columns.

---

## HIGH priority

1. **Correction revert** — Support chains like DF → S → DF; latest correction wins; preserve full append-only history (stage + permanent promotion).

2. **Malformed correction payload** — Missing/invalid row id or field name → clean HTTP 400 (not 500). `reviewed_value=None` must not become the string `"None"`.

3. **Stage-create storage orphan** — If stage PDF is stored but DB commit fails, purge the temporary file.

4. **Cleanup transaction/session safety** — Stage cleanup failure must not leave `AsyncSession` poisoned; avoid helper `commit()` accidentally committing unrelated caller work (`_delete_stage_records` today commits internally).

5. **Process retry after cleanup failure** — If permanent `SOURCE_REVIEWED` already exists for `stage_id`, return existing summary and finish cleanup; do not surface duplicate conflict against the same `import_id`. *(Minimal idempotency hook may exist in `process_stage_to_permanent`; full retry/cleanup semantics belong here.)*

6. **Temp cleanup retry** — If permanent commit succeeds but stage-file cleanup fails, retain enough metadata to retry cleanup safely/idempotently.

7. **Active-stage TTL refresh** — Reusing an active stage (duplicate upload) should extend `expires_at` (24h from reuse).

8. **Automatic expired-stage cleanup** — 24h expiry must eventually purge stage DB rows + temp files without relying only on the next upload calling `purge_expired_stages` (background job / scheduled task).

---

## MEDIUM priority

9. **Active-stage duplicate lookup efficiency** — SQL-filter exact SHA where possible; deterministic newest-stage reuse when multiple matches.

10. **Defensive dedupe of permanent invoice matches** — Collapse `invoice_number` matches by `import_id` before `evaluate_bvd_pdf_duplicate`.

11. **Normalize storage read/write failures** — Map storage errors to useful API responses (upload, document GET, Process promotion).

12. **Remove unused imports / redundant code** — Staging module and import path cleanup pass.

---

## Reference

- Staging service: `app/services/fuel_bvd_stage.py`
- Migration: `alembic_tenant/versions/f8c9d0e1f2a3_fuel_bvd_import_staging.py`
- Parent checklist: `TODO.md` (Fuel section)
