# Disposable verification — owner approval packet

**Status:** Coded in repo; **not executed or deployed** on production EC2.  
**Git tree:** `/home/admin/trucking_erp` (reviewable change; commit when owner approves).

This packet satisfies the mandatory safety correction request: report **exact files**, **infrastructure**, **costs**, and **isolation proof** before any run.

---

## 1. Proposed files (this change)

| Path | Role |
|------|------|
| `app/core/verification_host_guard.py` | Fail-closed host/URL/bypass checks |
| `scripts/verification_host_preflight.py` | CLI preflight (exit **78** on deny) |
| `scripts/disposable_tenant_bootstrap.py` | Tenant DB: `CREATE` + Alembic **or** sanitized artifact restore |
| `scripts/disposable_platform_bootstrap.py` | Platform DB for auth certification waves (pinned platform revision) |
| `scripts/disposable_platform_seed.py` | Active `pytest` tenant, admin user, membership, Casbin prospective policy load |
| `app/core/verification_subprocess_env.py` | Sanitized child env for psql/alembic/pytest |
| `.github/workflows/verification-disposable.yml` | CI: isolated Postgres service, preflight + safety unit tests only |
| `scripts/disposable_verification_runner.py` | Wave orchestrator: preflight → bootstrap → pytest + JUnit + manifest |
| `scripts/demo_clone_runner.py` | **Live execute disabled**; preflight + no live `tenant_demo` dump when re-enabled path attempted |
| `tests/support/disposable_verification_auth.py` | Certification auth checklist (no `TEST_BYPASS_AUTH`) |
| `tests/test_verification_host_guard.py` | Guard unit tests |
| `tests/test_load_workspace_draft_api.py` | FK-safe teardown for `test_promote_creates_commercial_evidence_when_pdf_ready` |
| `docs/verification/OWNER_APPROVAL_PACKET.md` | This document |

**Follow-up (before full I5 certification run):** refactor `test_load_cancel_issue5.py` fixtures off `TEST_BYPASS_AUTH`, sanitized artifact build pipeline, network SG/terraform on disposable EC2.

---

## 2. Infrastructure requirements

### Disposable verification host (required)

- **Not** EC2 instance `i-0126f0dc65891ca63` (hard deny in guard).
- File **`/etc/truckerp/verification-host-class`** containing exactly `disposable` (root-owned `0444`) **or** non-production EC2 instance id not in denylist.
- **No** bind mount of `trucking_erp_postgres_data` or production SSM-rendered secrets.
- Dedicated Postgres (suggested: small EC2 + Docker `postgres:15` on `verification-postgres` container, or GitHub Actions service container).

### Credentials (verification-only)

| Variable | Purpose |
|----------|---------|
| `TRUCKERP_VERIFICATION_POSTGRES_ADMIN_URL` | `postgresql://verify:***@<disposable-host>:5432/postgres` only |
| `TRUCKERP_VERIFICATION_TENANT_REVISION` | Pinned tenant Alembic id (default: `dw1d_load_commercial_evidence_retention_varchar32`) |
| `TRUCKERP_VERIFICATION_TENANT_ARTIFACT` | Optional offline `.dump` / `.sql` (no live prod connection) |
| `DATABASE_URL` | Disposable platform DB (auth waves only) |

**Forbidden on verification host:** `/truckerp/prod/*` SSM, `/run/secrets/truckerp.env` from prod, URLs pointing at `truckerp-postgres` / `172.29.0.4` / `tenant_demo` / `trucking_erp`.

### Network

- Security group / firewall: **no** route to production Postgres port (5432 on prod VPC / `truckerp_net`).
- Verification Postgres reachable only from verification runner.

### Execution entrypoint (after approval)

```bash
export TRUCKERP_VERIFICATION_POSTGRES_ADMIN_URL='postgresql://verify:***@<disposable-host>:5432/postgres'
python scripts/verification_host_preflight.py   # must print OK and exit 0
python scripts/disposable_verification_runner.py --artifact-dir /artifacts/f1-verify/<run_id>
```

---

## 3. Cost estimate (order of magnitude)

| Item | Monthly (USD) |
|------|----------------|
| `t3.small` or `t4g.small` verification EC2 (on-demand, part-time) | ~$12–18 if run intermittently; ~$15–25 if always on |
| EBS 20–30 GB for disposable Postgres | ~$2–4 |
| Egress for artifact upload (JUnit/logs) | &lt;$1 per run |
| **No** additional prod RDS cost if prod dump is not used |

Running verification in **GitHub Actions** (`ubuntu-latest` + service postgres) avoids a permanent EC2; cost ≈ CI minutes only.

---

## 4. Isolation proof (pre-run checklist)

Owner or operator signs each item **before** first disposable run:

1. `python scripts/verification_host_preflight.py` → exit **0**, output `VERIFICATION_PREFLIGHT_OK`.
2. `curl` IMDS instance-id (if AWS) → **not** `i-0126f0dc65891ca63`.
3. `docker inspect` (if used): no container using volume `trucking_erp_postgres_data`.
4. `env` redacted manifest: no `truckerp-postgres`, `tenant_demo`, `172.29.0.4` in DB URLs.
5. `collect_verification_denial_reasons()` empty on runner host (unit tests + preflight).
6. Attempt `DEMO_CLONE_EXECUTE=1 demo_clone_runner` on prod instance → **must fail** (preflight / disabled live execute).
7. Post-run: `manifest.json` + `junit-*.xml` per wave; failed wave blocks subsequent waves.

---

## 5. Wave behavior and evidence

| Wave ID | Tests | Auth |
|---------|-------|------|
| `wave1-f1-core` | F1 unit + `test_load_workspace_draft_api.py` | Service (`TRUCKERP_VERIFICATION_AUTH_MODE=service`) |
| `wave3-i5-cancel` | `test_load_cancel_issue5.py` | Certification (`TEST_BYPASS_AUTH` forbidden) |

Each wave writes:

- `junit-<wave>.xml`
- `pytest-<wave>.log` (verbose)
- `manifest.json` (git SHA, revision, exit codes, environment manifest)
- `bootstrap.json` (tenant DB name, redacted admin URL)

---

## 6. Corrections delivered (requirements 5–6)

- **Teardown:** `test_promote_creates_commercial_evidence_when_pdf_ready` clears `load_pod_evidence`, nulls `promoted_load_id` on draft, deletes draft before load; FKs unchanged.
- **Auth fixtures:** `disposable_verification_auth.py` + `disposable_platform_bootstrap.py` document Casbin/JWT path; **seed automation** is explicit follow-up before I5 certification can pass.

---

## 7. Explicit non-actions (this task)

- No production deploy, migration, or Docker changes on prod EC2.
- No verification execution on prod EC2 (guard denies `i-0126f0dc65891ca63`).
- No F1 business-logic changes outside test teardown ordering.

---

## 8. Owner approval requested

Approve **one** of:

- [ ] Provision disposable verification EC2 + Postgres per §2  
- [ ] Use GitHub Actions disposable Postgres workflow (follow-up PR)  
- [ ] Provide sanitized tenant artifact storage location for `TRUCKERP_VERIFICATION_TENANT_ARTIFACT`

**Until approved:** do not run `disposable_verification_runner.py` on any host.
