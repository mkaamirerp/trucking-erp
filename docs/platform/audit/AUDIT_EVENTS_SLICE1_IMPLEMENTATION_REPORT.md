## Slice 1 — Tenant-wide audit foundation (implementation report)

**Slice goal:** Land the **audit_events foundation only**: table + model + writer + redaction + unit tests. No module rollout yet (People/Loads wiring starts in Slice 2+).

---

## What shipped in repo (code + migration)

- **Tenant Alembic migration**: `alembic_tenant/versions/s1b2c3d4e5f6_audit_events_foundation.py`
  - Creates `audit_events` (append-only)
  - Adds check constraints for `actor_type`, `source`, `visibility`
  - Adds indexes for entity timeline + module timeline + actor + correlation
  - Adds `legacy_tenant_audit_log_id` with a partial unique index (idempotent backfill support)
  - Includes optional `entity_label`

- **Tenant model**: `app/models/tenant_audit_event.py` (`AuditEvent`)
  - Exported via `app/models/tenant/__init__.py`

- **Redaction helper**: `app/utils/audit_redaction.py`
  - Denylist-based redaction for `changed_fields` and shallow snapshot redaction (top-level keys)
  - Visibility upgrade to at least `sensitive` when redaction occurs

- **Writer service**: `app/services/audit_events.py`
  - `write_audit_event(...)` contract:
    - Validates allowed enums in code (`actor_type`, `source`, `visibility`)
    - Enforces payload presence: at least one of `changed_fields`, `snapshot_before`, `snapshot_after`, `context_json`
    - Allows **diff + snapshots together**
    - Defaults `correlation_id = request_id` when absent
    - Supports `best_effort=True/False`

- **Unit tests**: `tests/test_audit_events_writer.py`
  - Redaction behavior
  - Visibility upgrade behavior
  - Writer defaults and validation
  - best_effort vs strict failure behavior

---

## Notes / intended follow-on slices

- Slice 2: dual-write People correction history into `audit_events` (keep `tenant_audit_logs` intact)
- Slice 3: People read cutover with fallback
- Slice 4: idempotent backfill using `legacy_tenant_audit_log_id`
- Slice 5: Loads as first non-People consumer + replace load audit placeholder

