# Proposed updates to `MASTER.md` (NOT APPLIED)

**Purpose:** Owner review before editing the canonical master.  
**Source:** Phase 2 design [`DRAFT_WORKSPACE_SPEC.md`](./DRAFT_WORKSPACE_SPEC.md), owner addendum `586ee10`.

---

## 1. Work order table — new / revised rows

| Order | ID | Work item | Proposed status | Notes |
|------:|----|-----------|-----------------|-------|
| NEW | DW-1 | Load workspace draft schema + storage | ⬜ NOT IMPLEMENTED | `load_workspace_drafts`, evidence table, retention class (no copy on promote) |
| NEW | DW-2 | Draft CRUD + promote APIs | ⬜ NOT IMPLEMENTED | See `draft_workspace_api.yaml` |
| NEW | DW-3 | Email intake → workspace (stop intake `loads` insert) | ⬜ NOT IMPLEMENTED | Replaces junk commercial rows at source |
| NEW | DW-4 | Promote creates Load `ready` + immutable evidence | ⬜ NOT IMPLEMENTED | Shared mark-ready validator |
| NEW | DW-5 | Load cancel + payroll accrual block | ⬜ NOT IMPLEMENTED | Replaces hard-delete product goal |
| REV | I12 | TripLoad requires Load `ready` | ⬜ NOT IMPLEMENTED | Gate `_insert_trip_load_row`; inventory legacy draft memberships |
| REV | I5 | Hard DELETE unsafe | ✅ CODE COMPLETE / MERGED TO MAIN — NOT DEPLOYED | Interim 409 `LOAD_PHYSICAL_DELETE_TEMPORARILY_DISABLED` on `main` (`f738339`); **shelve** permanent delete design; cancel is product path |
| REV | I1 | New-write Load.status boundary | ⚠ UPDATE TEXT | **New commercial rows** via promote = `ready` only; `draft` on `loads` = **legacy** until classified |

**Exact next executable item (proposed):** After owner approves this delta + spec — checkpoint **DW-1** (schema only), STOP for review.

---

## 2. New section (after owner decision `586ee10` block)

Insert or merge with existing **Owner decision — temporary Draft workspace** content:

### Load workspace draft vs `loads.status=draft`

| Concept | Meaning |
|---------|---------|
| **Workspace draft** | `load_workspace_drafts.id` (UUID); temporary; TTL; discard allowed; never in Trip/Payroll/AR. |
| **Legacy DB draft** | Existing `loads` row with `status=draft`; classified per spec §9; promote via mark-ready or cancel when available. |
| **Official Load** | Row in `loads` after promotion **`ready`** (new path) or legacy mark-ready; **never physically deleted**; cancel only. |

### Promotion UX (locked recommendation)

- Incomplete work stays in **workspace**.
- **Promote** = mark-ready validation + create Load **`ready`** in one DB transaction + evidence row referencing **same** storage key (`commercial_permanent` retention; no PDF copy in txn).
- Do **not** create new `loads.status=draft` rows from `/loads/new` or intake once DW-3 ships.

---

## 3. §2 Load ownership — target statuses (clarification)

Add footnote to **Target new-write `Load.status`** table:

> After workspace draft ships, **new** commercial records should appear as **`ready`** or **`cancelled`** only. **`draft`** on `loads` remains for historical rows and transitional legacy creates until intake/manual paths are migrated.

---

## 4. Parser / hydration (pointer only)

Add under parser-related work items (I6–I22) or appendix:

- Workspace parse continues to use `POST /loads/parse-document` (no parser change).
- Accepted parse stored on draft (`accepted_parse_json`) and frozen on `load_commercial_evidence` at promote; invalidated on PDF replace.
- GET draft PDF for left-pane review; keys never exposed in JSON.
- Load Lab remains non-promote; do not share SHA-based deletion with workspace drafts.

---

## 5. Issue 5 / DELETE (reconcile)

Replace or annotate row I5:

- **Interim:** API returns 409 `LOAD_PHYSICAL_DELETE_TEMPORARILY_DISABLED` — **merged to `main`, not deployed** (verify after `reload_api.sh`).
- **Product:** Physical DELETE removed from roadmap for official loads; workspace discard is separate API.
- **Payroll/delete race analysis:** shelved for delete; **payroll reference contract** remains independent workstream.

---

## 5b. Legacy `loads.status=draft` policy (proposed MASTER note)

- **No bulk delete**, **no auto-promotion**, **no `loads.id` changes** for legacy rows.
- Classify read-only per `DRAFT_WORKSPACE_SPEC.md` §9 before any transition policy.

---

## 6. `docs/load_trip/README.md` (minor)

Add link:

```markdown
- Design (not implemented): [`DRAFT_WORKSPACE_SPEC.md`](./DRAFT_WORKSPACE_SPEC.md)
```

---

## 7. Authority rule

No change to “sole authority” rule. This delta is a **proposal** until owner merges into `MASTER.md` and updates work-order statuses with evidence.

---

*Do not edit `MASTER.md` until owner approves.*
