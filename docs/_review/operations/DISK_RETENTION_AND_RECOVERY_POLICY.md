# TruckERP disk retention and recovery policy

**Status:** operator policy (documentation only)

**Scope:** production EC2 root disk, Docker image/cache retention, Gold/Git rescue lifecycle, worktrees, volumes, logs, and host caches.

**This document does not authorize** Docker daemon changes, BuildKit GC configuration, cron, systemd, compose edits, or unattended prune jobs.

Cleanup is always **explicit, verified, and reversible until off-host copies exist**. Never use blind pruning at any utilization threshold.

---

## Recorded baseline (2026-09-16)

Point-in-time facts after the September 2026 disk incident and Dockerfile cache correction. Image IDs below are a **snapshot**, not a standing tag list.

| Item | Value |
|---|---|
| Root disk | 30G |
| Utilization | ~76% |
| Available | ~6.9G |
| API live image | `8ab41b501ece` |
| API live baked SHA | `b579a0bd` |
| API retention | live + 2 rollbacks |
| Immediate previous rollback | `rollback-b8de9796` → `e756877b6e5f` |
| Additional previous rollback | `rollback-60f4be02` → `6e1a0a04b3f6` |
| BuildKit (docker `system df` cache) | ~1.504GB |
| Docker log rotation | `max-size` 50m × `max-file` 3 |
| Production worktree | `/home/admin/trucking_erp-prod-main` |
| Canonical API reload | `/home/admin/trucking_erp-prod-main/scripts/reload_api.sh` |

---

## 1. Disk thresholds

Measure with `df -h /` and `df -B1 /`. Thresholds apply to **root filesystem use percent**. They trigger **inspection and planned action**, not automatic deletion.

| Use | Band | Operator action |
|---|---|---|
| **&lt;70%** | Normal | No extra cleanup. Monthly review still applies. |
| **70–79%** | Warning | Inspect growth: images, BuildKit, logs, worktrees, host caches. Identify the largest *unique* consumers. Do not prune. |
| **80–89%** | Critical | Cleanup **planning** required: list exact IDs/paths, expected unique-byte recovery, keep/retire lists. Execute only after approval of that list. |
| **≥90%** | Emergency | Stop nonessential builds. Perform **controlled** emergency cleanup from a written list (see checklist). Do not run `docker system prune` / `docker image prune -a`. |

At every band: recover **unique overlay/image-layer bytes**, not Docker virtual image size. Confirm no running/stopped container needs a candidate before deletion.

---

## 2. API image retention

### Steady state

Keep exactly:

1. **Current live** (`trucking_erp-truckerp-api:latest`)
2. **Immediate previous known-good** production (named rollback tag)
3. **One additional previous known-good** production (named rollback tag)

**Maximum in steady state:** live + 2 API rollback images.

Nginx rollback tags are a **separate** retention set. An API rollback name must never be used as a reason to delete a similarly named nginx image.

### During a production API deployment

Temporarily allow **live + 3 rollbacks**:

1. Tag current live as a new named rollback **before** replacing `:latest`.
2. Build / verify / deploy the new live image.
3. Verify new production is healthy.
4. **Then** explicitly retire the **oldest** API rollback (exact tag + exact image ID).
5. Return to live + 2.

### How to delete

- Delete **only** explicitly verified obsolete image/tag IDs (`docker rmi <repository>:<tag>` after inspect).
- If untagging leaves the image because another tag/digest remains, **stop**. Report the remaining reference. Do not force-delete.
- **Never** use broad `docker image prune -a` as the normal retention mechanism.

---

## 3. Deployment ordering

Canonical production API reload:

```bash
/home/admin/trucking_erp-prod-main/scripts/reload_api.sh
```

Do **not** `cd /home/admin/trucking_erp` and run `docker compose build truckerp-api` / `up -d truckerp-api` for production. That tree is not the production worktree.

Safe sequence:

1. **SOURCE DURABLE** — production worktree on `main`, intended SHA is committed and (when this host is the publisher) pushed; secrets remain SSM-only.
2. **Protect current live rollback** — tag the running live image before it is replaced.
3. **Build** — via the protected prod-main reload script (or an approved equivalent that uses the same worktree, compose project `trucking_erp`, and SHA bake).
4. **Offline image verification** — confirm baked `TRUCKERP_APP_GIT_SHA`, image ID, and import/smoke checks as appropriate **before** treating the new image as production.
5. **API-only recreate** — replace `truckerp-api` only (`--no-deps`); do not rebuild/recreate nginx, postgres, or certbot as a side effect of an API deploy.
6. **Health check** — container healthy; `/api/v1/health` (or current health contract) succeeds.
7. **Application verification** — the change that justified the deploy is present in the running image.
8. **Confirm rollback is available** — named previous-live tag still exists and is unused by the new container.
9. **Retire oldest rollback** — only after new production is verified healthy; explicit ID only.

**Cleanup must never happen before new production is verified healthy.** Disk pressure does not override this order.

---

## 4. BuildKit

### Current facts (not a daemon change)

- The API Dockerfile is structured so **Git SHA changes do not invalidate apt/pip layers**.
- The runtime **`/wheels` copy layer was eliminated**; wheels are consumed via a BuildKit bind mount at install time.
- A verified SHA-only rebuild **reused all dependency layers**.
- A useful BuildKit stack has historically measured around **~1.0GB**.
- Current BuildKit cache (2026-09-16 snapshot) is **~1.5GB**.

### Desired future retention

Keep useful dependency/wheel cache in approximately **1.0–1.5GB**.

### Not yet implemented

**A Docker daemon / BuildKit GC cap is not configured.** Do not assume `builder.gc` or a size policy is already in `daemon.json`.

Implementing BuildKit GC is a **future controlled task**. It requires verification against **Docker Engine 26.1.5 / Buildx 0.13.1** on this host (selective cache-ID delete is not a documented, safe operator path on this install). Until that work is approved and verified:

- Do not prune BuildKit as routine cleanup.
- Do not use age-only `until=24h` as the standing policy. Useful dependency and wheel cache is often **older** than disposable test-layer cache.

---

## 5. Gold artifacts

Gold / parser recovery artifacts belong **off EC2**, in the established S3 disaster-recovery prefix, with SHA256 manifest / checksum verification:

```text
s3://truckerp-015421055625-us-east-1-an/platform/disaster-recovery/
```

- Do **not** retain ~800MB Gold tar archives permanently on the EC2 root disk.
- **Secrets must never be included** in Gold uploads. Exclude `SECRETS_DO_NOT_UPLOAD` and any rendered env, SSM dumps, `.env`, or key material.
- After upload, verify checksums against the manifest **before** deleting the local copy.

---

## 6. Git rescue lifecycle

Required order:

1. **CREATE** the rescue copy (clear, dated path; not inside the production worktree).
2. **VERIFY** contents (what commits, what artifacts, what must never leave the host).
3. **Identify unreachable commits** that still matter.
4. **Create durable Git refs** for those commits.
5. **Push durable refs off-host** (GitHub or the established remote).
6. **Archive required artifacts off EC2** (S3 DR prefix, checksummed).
7. **Checksum verify** remote copies.
8. **DELETE the local rescue copy**.

Never leave multi-GB rescue directories indefinitely.
Never upload `SECRETS_DO_NOT_UPLOAD` or equivalent secret material.

---

## 7. Worktrees

| Tree | Role |
|---|---|
| `/home/admin/trucking_erp-prod-main` | **Canonical production worktree.** API image rebuilds and `reload_api.sh` run only from here. |
| Feature / recovery worktrees | Temporary. Remove after merge or archive. |
| `/home/admin/trucking_erp` (often detached) | **Must not** be used for production deployment. |

Rules:

- Never auto-delete a **dirty** worktree.
- Verify the branch/commit is **durable** (pushed ref or archived SHA) before removing a worktree.
- Remove completed temporary worktrees after merge/archive so they do not accumulate on the 30G root disk.

---

## 8. Docker volumes

**Protected — never include in generic cleanup:**

- PostgreSQL data (`trucking_erp_postgres_data` and any live postgres volume actually mounted by `truckerp-postgres`)
- Production application storage (`trucking_erp_trucking_erp_storage` and the live API storage mount)
- letsencrypt / certbot data (`trucking_erp_letsencrypt`, `trucking_erp_certbot_www`)

Unknown volumes must be audited **before** any deletion:

- which containers mount them (running and stopped)
- Compose project / name ownership
- contents (data vs empty leftover)

Compose leftover volumes from abandoned projects are audit candidates, not automatic deletes.

---

## 9. Logs

Existing Docker json-file rotation (production compose):

- `max-size`: **50m**
- `max-file`: **3**

Future container services should declare the same class of **explicit bounded logging**.

Large PostgreSQL or API logs are a **root-cause signal** (query storms, tight restart loops, misconfigured log level). Investigate; do not treat deletion as the fix. Host journal/log files outside Docker follow the same rule: identify the writer, then bound or fix, then consider removal of already-rotated leftovers.

---

## 10. Host caches

These are **audit candidates**, not automatic deletion. Require ownership and current-use checks first.

- Cursor server / cache
- Claude cache
- npm cache
- Playwright browsers / cache
- Python test / verification venvs on the host
- Abandoned worktrees

Host venv pytest is **verification tooling only**; it is not a second deployment. Do not delete a venv that operators still use for checks without confirming a replacement path.

---

## 11. Prohibited as routine operations

Do not run these as standing or “disk is high” habits:

- `docker system prune -a`
- `docker image prune -a` (and unscoped `docker image prune` / `docker system prune` as a substitute for named-ID retirement)
- Deleting the PostgreSQL volume
- Deleting the production storage volume
- Deleting letsencrypt / certbot data
- Deleting dirty worktrees
- Deleting rescue data before off-host verification and checksums
- Deleting rollback images **before** new live health verification
- BuildKit prune / age-only `until=24h` cache wipe
- Wildcard or dangling-image sweeps mixed with protected rollback tags

---

## 12. Incident note — September 2026

Root disk reached approximately **85%**.

Major contributors:

- Accumulated Docker images and build layers (including SHA-at-top cache busting that duplicated apt/pip layers per deploy)
- Git rescue / Gold artifacts left on the EC2 root disk
- Historical logs
- Host caches and extra worktrees

Controlled cleanup (explicit image IDs, rescue-dir delete only after S3 + GitHub archive verification, Dockerfile cache correction) reduced utilization **without** deleting production data, volumes, or live containers. Steady API retention was restored to live + 2 named rollbacks. BuildKit GC was **not** enabled as part of that work.

---

## 13. Operator checklists

### Before a production API build

- [ ] Working tree is `/home/admin/trucking_erp-prod-main` on `main`; intended SHA is durable.
- [ ] `df -h /` recorded; if ≥80%, have an explicit cleanup plan that runs **after** healthy deploy, not before (unless ≥90% emergency and new build cannot proceed).
- [ ] Current live image ID recorded; rollback tag will be applied **before** `:latest` is replaced.
- [ ] Confirm existing rollback count; expect temporary live + 3 during the cutover.
- [ ] Reload only via `/home/admin/trucking_erp-prod-main/scripts/reload_api.sh`.
- [ ] Do not prune, rmi rollbacks, or touch volumes/BuildKit as a “make space for the build” shortcut unless an approved emergency list exists.

### After a successful production API deploy

- [ ] New live image ID + baked `TRUCKERP_APP_GIT_SHA` recorded.
- [ ] Container healthy; application check passed.
- [ ] Immediate previous live exists as a named rollback tag.
- [ ] Oldest API rollback identified by **tag + full image ID**; confirm no container references it.
- [ ] Retire that one API rollback only; do not touch similarly named nginx tags.
- [ ] Confirm steady state is live + 2.
- [ ] Record `df -B1 /`, `df -h /`, `docker system df` (images vs BuildKit separately).

### Monthly disk review

- [ ] `df -h /` and `df -B1 /`.
- [ ] `docker system df` and `docker system df -v` (images: unique vs shared; BuildKit size).
- [ ] API tags = live + 2 rollbacks; nginx rollbacks inventoried separately.
- [ ] No Gold tarballs or rescue directories on root disk.
- [ ] Worktrees: only prod-main plus justified temporaries; no dirty-tree deletion.
- [ ] Volumes: protected postgres/storage/letsencrypt still present; unknowns listed, not deleted.
- [ ] Host caches listed if they are large; ownership checked; no automatic wipe.
- [ ] If 70–79%, document the growth driver. If 80–89%, write a named-ID cleanup plan.

### Emergency ≥90% response

- [ ] Stop nonessential builds and image tests.
- [ ] Do **not** run `docker system prune -a` or `docker image prune -a`.
- [ ] Snapshot `df -B1 /`, `docker system df -v`, `docker ps -a`, image tags/IDs.
- [ ] Prefer, in order, **proven unique** consumers: leftover test image tags, oldest API rollback **only if** live + 2 newer known-good remain and live is healthy, then audited host caches, then completed clean worktrees.
- [ ] Never delete postgres, production storage, letsencrypt, dirty worktrees, or unverified rescue data.
- [ ] Never delete the immediate previous API rollback while live is unproven or mid-deploy.
- [ ] After each explicit `rmi`/delete, remeasure `df` and stop when the host is back in the warning band with a follow-up plan.
