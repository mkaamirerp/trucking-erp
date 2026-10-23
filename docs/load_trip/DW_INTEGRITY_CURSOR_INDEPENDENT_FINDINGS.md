# DW + Load/Dispatch Integrity — Cursor Independent Findings

**Status:** READ-ONLY INVESTIGATION — **NOT** implementation approval  
**Prepared:** 2026-10-18 (host-local evidence)  
**Commissioned by:** Owner remediation contract (2026-10-17)  
**Authority:** `docs/load_trip/MASTER.md` on the **pinned review SHA** (see §1)

---

## 1. Exact SHAs, trees, and runtime evidence

### 1.1 Git refs (worktree `/home/admin/trucking_erp`)

| Ref | SHA | Notes |
|-----|-----|--------|
| **HEAD** (`gpt-review`) | `e3e7634e8bee7af4025ee3b5ec5ebec4828f4e79` | Ahead of `main`; includes I8 `load_commercial_money` + non-finite guards |
| **main** (local/remote) | `7241d83a39f4caf2ae8cae3cd1de735343ed8202` | Contract-pinned inspection SHA |
| **origin/gpt-review** | `e3e7634` | Matches HEAD at investigation time |
| **Historical baseline** | `964708ee` (2026-05-12) | Chronology only |
| **Reported isolated Integrity release** | `6919ec0323742345a84968ae4f5cc9f26b930d69` | From MASTER; **not** equal to `main` or `gpt-review` HEAD |
| **Integrity freeze base** | `7fbd69c2eec3fee384676886cd8c675fe7773933` | 0A writer freeze on mainline |

**Commands (recorded):**

```text
git rev-parse HEAD main gpt-review origin/main origin/gpt-review
→ e3e7634…, 7241d83…, e3e7634…, 7241d83…, e3e7634…
```

### 1.2 Working tree (dirty — must be preserved before any one-shot edit)

| State | Paths |
|-------|--------|
| Modified | `TODO.md`, `app/services/load_document_parse_rate_con.py`, `app/services/load_parser_openai_handoff_v2.py`, `docs/auth/README.md`, `docs/load_parser/README.md`, `tests/test_load_document_parse_guarded.py` |
| Untracked (sample) | `.cursor/rules/existing-module-no-new-file-without-report.mdc`, `docs/architecture/`, `parser-casbin-wip-pre-merge-20261017-233708/`, parser/scripts/tests WIP, PDF fixtures |

**No backup tag/bundle was created in this investigation** (owner must authorize per contract §4).

### 1.3 `main` vs `gpt-review` (load-relevant delta)

```text
git diff --stat 7241d83..e3e7634 -- app/services/loads.py app/utils/load_commercial_money.py
 app/services/loads.py              | 367 ++++++++++++++++++++++++++++++++-----
 app/utils/load_commercial_money.py |  69 +++++++  (new on branch, not on main)
```

Notable commits on `7241d83..HEAD` touching `loads.py`: `b5b9371` (I9 atomic audit), `7a5a820` (I5 TripLoad on cancel), merge `738743f`, earlier I2/I9/I26/I5 chain.

`app/services/load_workspace_draft_promotion.py`: **no diff** `7241d83..e3e7634` (identical on both SHAs for this file).

### 1.4 DW file inventory (SHA-specific)

**On `7241d83` (`main`):** 9 DW-related app paths + 2 alembic revisions (`dw1f…` foundation, `dw1d…` retention varchar32). **No** `app/services/load_workspace_draft_storage.py`.

**On `e3e7634` (HEAD):** above plus **untracked-on-main** `app/services/load_workspace_draft_storage.py` (DW-2 storage foundation; present in working tree, not in `7241d83` tree).

Contract note: `load_workspace_draft_storage.py` was correctly absent on pinned `main`; it exists on current branch working tree.

### 1.5 Production / runtime (this host — independent checks)

| Signal | Value | Interpretation |
|--------|--------|----------------|
| `tenant_demo` Alembic | `x5y6z7a8b9c0` | Pre–DW-1 / pre–`dw1d` per MASTER; **not** disposable-clone target `dw1d_load_commercial_evidence_retention_varchar32` |
| `platform_tenants` (demo) | slug `demo` → `tenant_demo` | Unchanged by Phase-1 DB orphan cleanup |
| Running `truckerp-api` image | `trucking_erp-truckerp-api:latest` → image id `sha256:81576f3b…` | **Same image id** as `casbin-f9c9067`; **different** from `integrity-6919ec0-20261015` (`sha256:1c601922…`) |
| Container `/app` | No `.git` | Cannot `git rev-parse` inside container |
| `loads.py` in **running** container | I9-style `create_load` (audit then **one** `commit`) | **Disagrees** with `6919ec0` / `7241d83` `create_load` (commit **before** audit) |
| `docker exec … python -c "from app.services import loads"` | `ImportError: LOAD_COMMERCIALLY_CANCELLED` from `trip_dispatch` | Suggests **image/code vs constants mismatch** on running container; treat live behavior as **unverified** until health/import audit passes |

**Conclusion F3:** Three-way drift is real: **`main` 7241d83**, **`gpt-review` e3e7634**, **reported 6919ec0**, and **running API file content** do not form one proven release artifact. MASTER’s warning stands; this investigation **strengthens** it.

---

## 2. Agy / Integrity issue → code causality matrix (evidence-based)

Source register: historical `docs/LOAD_INTEGRITY_AUDIT_AND_REMEDIATION_PLAN.md` (SUPERSEDED; issue IDs preserved). Status from **`docs/load_trip/MASTER.md`** work-order table.

| ID | Original defect (Agy/historical) | Owner file(s) | First fixing commit(s) on mainline (sample) | New files added for fix? | Current owner (e3e7634) | Tests / reproduction |
|----|----------------------------------|---------------|---------------------------------------------|--------------------------|-------------------------|----------------------|
| 0A | Legacy ops status / assignment on Load create-PATCH | `loads.py`, UI freeze | `7fbd69c` / review `26621fe` | No | `_guard_create_payload`, router freeze | `tests/test_load_writer_freeze_issue0a.py` |
| I1 | Fake execution via Load.status on create | `loads.py`, `schemas/load.py` | With 0A guards | No | `_guard_create_payload` | 0A tests |
| I2 | Full stop replace destroys history | `loads.py` `update_load` / stop sync | `e97813d`, `d0d758d`, `cebdced` | No | `_sync_load_stops_commercial` path | I2-focused tests in load integrity suite |
| I3 | Mark ready bypass | `loads.py`, routers | `f5bbf5d` / `d791296` on gpt-review | No | `mark_load_ready`, PATCH guard | mark-ready tests |
| I5 | Hard DELETE / cancel policy | `loads.py`, routers | `72520e0`, `d7d222e`, `7a5a820` | No | `cancel_load`, DELETE block | cancel / TripLoad tests |
| I9 | Incomplete / non-atomic audit | `loads.py` | `b5b9371` (gpt-review); hooks earlier `e97813d` | **No** for I9 | `_write_load_audit` `best_effort=False` on critical paths | `tests/test_load_audit_events_unittest.py` |
| I26 | Money PATCH vs audit atomicity | `loads.py` | `ede7ba8` / `f30452b` chain | No | `update_load` money + audit | `tests/test_load_money_audit_atomicity_issue26.py` |
| DW-1 | N/A (product: draft before Load) | `load_workspace_draft_*.py` | `3499036`, `299b06b`, `387b732`, `7241d83` (dw1d) | **Yes — new DW module files** (by design) | promotion in `load_workspace_draft_promotion.py` | `tests/test_load_workspace_draft_api.py`, `tests/test_load_workspace_draft_schema_dw1.py` |
| I8 | Float at API boundary | schemas, parser, mapper | `0448545`, `e3e7634` on **gpt-review only** | **`app/utils/load_commercial_money.py`** | shared coerce | `tests/test_load_commercial_money_issue8.py` |
| I14 | Custody/POD/stops execution | trip/load services | `6ac67fa`…`2f60200` (per MASTER) | Multiple trip/load files | not DW promotion | trip/load integration tests |

**“Why new file?” documentation:**

- **DW-1 files:** Introduced as a **new product surface** (draft container), not as a one-line bugfix; commits `3499036` et al. **documented** in MASTER appendix.
- **`load_commercial_money.py`:** Shared Decimal/coerce across schemas/parser/mapper — **architectural choice on gpt-review**; conflicts with “no new helper without report” policy added later; **NOT on `main` 7241d83**.
- **Many Agy fixes:** In-place in `loads.py` — **not** proliferated.

**NOT DOCUMENTED in git messages:** precise Antigravity issue IDs for every sub-fix; rely on historical audit doc + MASTER table.

---

## 3. DW / Load writer graph (create + mutate)

Legend: **W** = write, **R** = read/hydrate only, **TX** = transaction notes.

| Entrypoint | Path | W/R | TX / audit |
|------------|------|-----|------------|
| POST `/loads` | `routers/loads.py` → `loads.create_load` | **W** Load + stops | **gpt-review / running container:** flush → audit (`best_effort=False`) → **one** `commit`. **main 7241d83 / 6919ec0:** `commit` → audit (`best_effort` default true) → second `commit` |
| PATCH `/loads/{id}` | `loads.update_load` | **W** | I9/I26: audit in same TX as mutation (gpt-review) |
| POST mark-ready / cancel | `loads.mark_load_ready`, `cancel_load` | **W** | Audited (gpt-review) |
| DW CRUD | `load_workspace_draft.py`, lifecycle, document | **W** draft JSON/PDF metadata | Per-route commits in service layer |
| POST `…/promote` | `load_workspace_draft_promotion.promote_workspace_draft` | **W** Load, stops, evidence, draft row | Single TX: insert load → evidence → draft promoted → audit → **commit** (promotion owns commit) |
| Parse document (workspace) | `load_document_parse_orchestrator` | **R** (no Load row) | N/A |
| Parse on draft | `load_workspace_draft_document` | **W** draft only | No Load |
| Email intake create | `email_threads.py` ~L229 | **W** Load (minimal fields) | **Separate path:** no `_guard_create_payload`, **no** `_write_load_audit` |
| Seed script | `seed_demo_operational_loads.py` | **W** via `create_load` | Uses service |
| TripLoad membership | `trips.py`, `dispatch_trips.py` | **W** TripLoad | Trip module; ready-gates per I12 |
| Legacy dispatch board | frozen | blocked | 0A |

**Tenant enforcement:** All listed services use `tenant_id` on queries scoped to `get_tenant_db` routes; promotion uses `with_for_update` on draft by `(tenant_id, id)`.

---

## 4. F1 proof — duplicate Load+stops creation

### 4.1 Side-by-side ( `7241d83` / HEAD — promotion file identical )

| Step | `loads.create_load` | `_insert_load_from_create` (promotion) |
|------|---------------------|----------------------------------------|
| `_guard_create_payload` | Yes | Yes |
| Broker / contact / customs checks | Yes | Yes |
| `load_number` default `DRAFT-{uuid}` | Yes | Yes |
| `_ensure_unique_load_number` | Yes | Yes |
| `_load_data_from_payload`, `status=draft` | Yes | Yes |
| ORM `Load(...)` | No `promotion_origin_workspace_draft_id` | Sets `promotion_origin_workspace_draft_id` |
| Stop loop / attr filter / sequence | Yes | Yes (no per-stop `flush` in promotion) |
| Stop audit `load_stops_changed` | **Yes** on API create (gpt-review) | **No** — only `load_created` on promote |
| Create audit payload | actor, request_id, `changed_fields` | `actor_user_id=None`, `source=workspace_draft_promotion`, `changed_fields=None` |
| Commit owner | `create_load` commits | Caller `promote_workspace_draft` commits |

**Quantified:** ~45 lines of **parallel business logic** in two functions in two files; **plus** shared imports from `loads.py` for guards/helpers (not a third copy, but **dual maintenance** of the insertion loop).

**Mechanical “call `create_load` from DW”:** **REJECT** without refactor — `create_load` commits internally and emits API-oriented audit; promotion needs pre-commit draft/evidence/idempotency and must not double-commit.

**Contract alignment:** **AGREE** with F1 (duplicate path, not proven live bug). **AGREE** proposed direction: transaction-neutral internal primitive in **`loads.py`**, no new util module by default.

### 4.2 Intentional divergences (must preserve in one-shot)

1. `promotion_origin_workspace_draft_id`
2. Audit shape (promotion source, optional stop audit on promote)
3. Commit boundary (promotion wraps draft + evidence + load)
4. API create stop-level audit diff vs promotion single checkpoint

---

## 5. F5 — audit vs commit ordering

### 5.1 By SHA / runtime

| Tree | `create_load` order | Orphan Load if audit fails? |
|------|---------------------|-----------------------------|
| `6919ec0`, `7241d83` | `commit` → `_write_load_audit` (best_effort default **True**) → `commit` | **Yes** — Load persisted without audit; audit failure may be swallowed |
| `e3e7634`, **running container `/app`** | audit (`best_effort=False`) → `commit` | **No** for audit failure before commit — TX rolls back |
| `promote_workspace_draft` (all above) | audit before `commit` | Rollback on audit failure (strict) |

**Disagreement with contract wording:** F5 as stated matches **`main`/6919ec0**; it is **partially obsolete** for **gpt-review HEAD** and **current running `loads.py`** for the **API create** path. **Still open:** email intake path has **no audit**; **no dedicated test** found that forces `load_created` audit failure during `create_load` (I26 tests focus on `load_updated` / money PATCH).

### 5.2 Recommended proof before one-shot (isolated DB only)

- Add/run fault injection: fail `_write_load_audit` on `load_created` and assert **zero** `loads` row (gpt-review expectation).
- On a **6919ec0-class** tree, same test should document orphan behavior if ever rolling back release.

---

## 6. Cross-contract audit (summary)

| Contract | Assessment |
|----------|------------|
| Load commercial truth | Create paths force `draft`; ready via `mark_load_ready` on integrated branch |
| Trip execution | No new Trip on create/promote — **OK** |
| TripLoad / active_trip_id | Not written on create/promote — **OK** |
| Custody / stop execution | Promotion creates commercial stops only; execution fields not in DW mapper commercial attrs — **OK** |
| I26 money audit | gpt-review `loads.py` — money PATCH atomicity tested; **separate** from F1 |
| RBAC | DW promote uses `require_pilot_capability("loads.records", "create")`; draft CRUD uses `get_current_user` — **asymmetric** (documented DW-1 choice) |
| Tenant isolation | FK tests in `test_load_workspace_draft_schema_dw1.py`; services pass `tenant_id` |

---

## 7. DW data / migrations

| Revision | Purpose |
|----------|---------|
| `dw1f2a3b4c5d6_load_workspace_draft_foundation` | Draft + evidence tables, `promotion_origin_workspace_draft_id` on loads |
| `dw1d_load_commercial_evidence_retention_varchar32` | Retention class column width fix (`7241d83`) |

**Production `tenant_demo`:** `x5y6z7a8b9c0` — **DW migrations not applied** on live demo tenant (per MASTER + live query). **Do not** run tenant upgrade on `tenant_demo` without owner approval. Isolated clones use `demo_clone_runner` → `dw1d…`.

---

## 8. Test map

| Area | Existing | Missing / weak |
|------|----------|----------------|
| API `create_load` | `test_load_audit_events_unittest.py`, I26 suite uses create as setup | **create_load audit failure rollback** explicit test |
| DW promote | `test_load_workspace_draft_api.py` (idempotency, evidence, expiry) | Fault inject: audit fail mid-promotion; broker invalid on mapped JSON |
| F1 parity | Implicit via separate suites | **Single matrix** asserting same rejection for invalid broker on both entrypoints |
| Email intake Load | — | No audit; no parity with commercial create guards |
| Old schema | clone `--baseline-only` | ORM may reference columns absent on baseline (MASTER notes `promotion_origin_workspace_draft_id` drift) |
| Concurrency | draft version conflict tests | Double promote covered |

---

## 9. Verdict on suggested changes (approval-gated)

| Change | Verdict | Proof / notes |
|--------|---------|----------------|
| Extract shared Load+stops insert in `loads.py` | **REQUIRED** (if owner approves one-shot) | F1 duplication; mechanical merge only after TX/audit contract designed |
| New `app/utils/load_commercial_money.py` | **OPTIONAL / separate track** | I8 on gpt-review only; **reject** bundling into F1 one-shot without owner I8 decision |
| Collapse DW files | **REJECT** | F2 — distinct roles; MASTER accepts module split |
| Call `create_load` from promotion | **REJECT** | Commit + audit mismatch (§4) |
| Fix F5 on main via I9 merge | **REQUIRED** for integrity closure | Already on gpt-review + running `loads.py`; **not** on `7241d83` |
| Unify promotion + API stop audit | **OPTIONAL** | Product/audit policy — owner choice |
| Email intake alignment | **OPTIONAL** | Third writer; out of narrow F1 scope unless owner expands |
| `load_workspace_draft_storage.py` on branch | **STOP** | Not on `main`; DW-2 — separate approval |

---

## 10. Owner STOP register

1. **Which SHA is the one-shot base?** `7241d83` (main) vs `e3e7634` (gpt-review) vs redeployed production — **must pin one**.
2. **Immutable backup / tag** — not done; required before edits.
3. **Production deploy vs code-complete gpt-review** — running image ≠ `integrity-6919ec0`; import error on fresh `loads` import in container.
4. **Tenant migration** — `tenant_demo` at `x5y6z7a8b9c0`; DW promote **cannot** be live-validated on demo until owner approves migration target.
5. **I5 cancel policy, I8 Decimal, I14 live POD, 0B/0C** — MASTER marks open; **exclude** from F1 one-shot unless explicitly in scope.
6. **New production files** — default **forbidden** (`existing-module-no-new-file-without-report.mdc`).
7. **Dirty worktree** — parser/Casbin WIP; preserve before any checkout for one-shot.
8. **Opus reconciled spec** — pending; Cursor findings are **untrusted input** for Opus per contract.

---

## 11. Disagreements with owner contract (explicit)

| Contract claim | Cursor finding |
|----------------|----------------|
| F5 always “commit then audit” on `create_load` | **True on `7241d83` / `6919ec0`**. **False** on `e3e7634` and **running** `/app/app/services/loads.py`. |
| `load_workspace_draft_storage.py` not on main | **Confirmed** absent at `7241d83`; **present** on current branch tree. |
| Running production = 6919ec0 | **Not substantiated** — `latest` API image ≠ `integrity-6919ec0` tag; file content matches I9 create path. |

---

## 12. Proposed minimal one-shot (spec only — NOT APPROVED)

**If** owner pins **`e3e7634`** (or merges I9 to main first) **and** backup exists:

1. Add **private** async helper in `loads.py`, e.g. `_insert_load_and_stops_from_create(...)`, parameters: `db`, `tenant_id`, `payload`, optional `promotion_origin_workspace_draft_id`, flags for stop audit emission.
2. `create_load` → helper → existing audit hooks → `commit`.
3. `_insert_load_from_create` in promotion → **delete body**, call helper → promotion continues evidence/draft/audit/commit.
4. Tests: F1 parity negatives + create audit fault + existing DW promote suite unchanged behavior.
5. **No** new files; **no** migration; **no** deploy.

**Rollback:** reset branch to immutable tag; no production DB touch.

---

*End of Cursor independent report. No application code was modified for this deliverable.*
