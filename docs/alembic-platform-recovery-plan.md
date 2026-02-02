# Platform Alembic chain recovery plan (5b013e5ac73d missing)

**Use subagent alembic-surgeon only.** Do not modify migration file content (do not change `down_revision`). Correct fix: restore missing revision file(s) from git history.

---

## Findings

1. **Who references 5b013e5ac73d**
   - **Platform** (`alembic.ini` → `script_location = alembic`):  
     `alembic/versions/c8a3d0b9c777_add_tenants_and_rbac.py` has `down_revision = "5b013e5ac73d"`.
   - Tenant track is fine: `alembic_tenant/versions/5b013e5ac73d_phase_9_7_driver_documents_soft_.py` exists.

2. **Does `alembic/versions/*5b013e5ac73d*.py` exist?**  
   **No.** There is no file in `alembic/versions/` whose name contains `5b013e5ac73d`. Glob `**/alembic/**/*5b013e5ac73d*` returns 0 files in the platform tree.

3. **Why it’s missing**  
   Commit **d755b06e** / **2e94cf93** (“fix(alembic): move tenant migrations to tenant track and fix revision chains”) **removed** 19 migration files from the platform track, including:
   - `alembic/versions/5b013e5ac73d_phase_9_7_driver_documents_soft_.py`
   - and the rest of the chain back to `a59de96e634e_create_drivers_table.py`.  
   `c8a3d0b9c777_add_tenants_and_rbac.py` was **kept** in platform and still points at `5b013e5ac73d`, so the reference is broken.

4. **Backup directory**  
   `alembic_tenant/versions.BAK.20260202_064225/` contains `5b013e5ac73d_phase_9_7_driver_documents_soft_.py` (and others), but that is the **tenant** backup. Platform uses `alembic/versions/`, so the platform missing file must be restored from **git**, not from that BAK.

5. **Full chain that must exist for platform**  
   For `alembic -c alembic.ini heads` to resolve without KeyError, every revision in the chain below `c8a3d0b9c777` must be present. That chain (from git parent of the fix commit, `d755b06e^`) is:

   - `c8a3d0b9c777` → `5b013e5ac73d` → `2f5725edf9c4` → `9d4695445bae` → `7de1d90c39eb` → `55da366e2878` → `476789399da2` → `a59de96e634e` (root)

   So the **exact filenames** that are missing in platform and must be restored (all from `d755b06e^`) are:

   | Revision     | Exact filename |
   |-------------|----------------|
   | 5b013e5ac73d | `5b013e5ac73d_phase_9_7_driver_documents_soft_.py` |
   | 2f5725edf9c4 | `2f5725edf9c4_add_soft_deactivate_fields_to_driver_.py` |
   | 9d4695445bae | `9d4695445bae_add_driver_documents_tables.py` |
   | 7de1d90c39eb | `7de1d90c39eb_add_driver_phones.py` |
   | 55da366e2878 | `55da366e2878_driver_phones_constraints_and_indexes.py` |
   | 476789399da2 | `476789399da2_driver_phones_constraints_and_indexes.py` |
   | a59de96e634e | `a59de96e634e_create_drivers_table.py` |

   Restoring only the first file fixes the KeyError for `5b013e5ac73d` but then Alembic will raise KeyError for `2f5725edf9c4`, and so on. So **all 7** files above must be restored for `alembic -c alembic.ini heads` to run without KeyError.

---

## Plan (commands)

Restore the 7 missing revision files from the commit **before** the fix (parent of the commit that removed them). Use that parent so we do **not** overwrite any of the platform files that were re-added later (e.g. `3c0f3f9c8cbe`, `c1e2c9f9cf2a`, `c1e2c9f9cf2b`, `c1e2c9f9cf2c`).

From repo root:

```bash
# Restore missing platform revisions (one shot)
git checkout d755b06e^ -- \
  alembic/versions/5b013e5ac73d_phase_9_7_driver_documents_soft_.py \
  alembic/versions/2f5725edf9c4_add_soft_deactivate_fields_to_driver_.py \
  alembic/versions/9d4695445bae_add_driver_documents_tables.py \
  alembic/versions/7de1d90c39eb_add_driver_phones.py \
  alembic/versions/55da366e2878_driver_phones_constraints_and_indexes.py \
  alembic/versions/476789399da2_driver_phones_constraints_and_indexes.py \
  alembic/versions/a59de96e634e_create_drivers_table.py
```

If you prefer to restore only until the next error (minimal step-by-step), run:

```bash
git checkout d755b06e^ -- alembic/versions/5b013e5ac73d_phase_9_7_driver_documents_soft_.py
alembic -c alembic.ini heads
# If KeyError 2f5725edf9c4:
git checkout d755b06e^ -- alembic/versions/2f5725edf9c4_add_soft_deactivate_fields_to_driver_.py
alembic -c alembic.ini heads
# … repeat for 9d4695445bae, 7de1d90c39eb, 55da366e2878, 476789399da2, a59de96e634e until heads succeeds.
```

---

## Verification command

After restoring the 7 files (from repo root, with your venv active or using its alembic):

```bash
alembic -c alembic.ini heads
```

Example with venv: `./venv/bin/alembic -c alembic.ini heads` or `source .venv/bin/activate && alembic -c alembic.ini heads`.

- **Success:** No KeyError; one or more head revision IDs are printed.
- **Note:** You may see **multiple heads** (e.g. `c1e2c9f9cf2c` and `0009_provision_hardening`). That is a separate concern (merge migration); the “missing revision 5b013e5ac73d” breakage is fixed when this command runs without KeyError.

---

## Safety lock

- **Do not** “fix” this by editing `down_revision` in any migration unless the correct previous revision chain has been proven (e.g. by restoring from git and verifying).
- **Do not** edit migration file content; **do not** stamp or run upgrades as part of this recovery.
- Correct fix: **restore the missing revision file(s) from git history** (as above).
