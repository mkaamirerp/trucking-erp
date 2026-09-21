# Fuel Provider-Native Investigation Checkpoint — 2026-09-20

**Status:** PAUSED — investigation/design checkpoint only.  
**No Fuel code, migration, database, or deployment change is authorized by this file.**

Authoritative architecture remains:

- `docs/FUEL_CARD_MODULE_DESIGN.md`
- `docs/FUEL_CARD_IMPLEMENTATION_PLAN.md`
- `docs/FUEL_GOLD_MANIFEST.md`

This checkpoint records where the investigation stopped so work can resume without re-deriving the direction.

---

# 1. Direction now locked

Current supported/test provider foundation:

```text
1. BVD
2. Nationwide
```

No generic "upload any fuel statement and let AI figure it out" production path.

For every supported provider, TruckERP must know and version the exact customer-facing interface/profile.

```text
approved provider + approved interface/profile
        -> process

unsupported provider / unknown layout / unknown profile
        -> review or reject
```

The underlying processing rail (EFS / WEX / Comdata / Fleet One / etc.) may be useful lineage metadata but is not the integration boundary and does not grant access to a white-label provider's customer data.

If a provider exposes a usable authorized production API to the fleet, use that API as the production source. If not, use the explicitly approved digital PDF / CSV / structured export for that provider.

Current evidenced paths:

```text
BVD        -> digital PDF
Nationwide -> digital PDF
```

---

# 2. Main architecture conclusion from investigation

The current Fuel feature implementation is largely **canonical-first**.

Current conceptual path:

```text
provider source row
        -> classify
        -> FuelTransaction OR FuelSourceControl
```

Target path:

```text
SUPPORTED PROVIDER REGISTRY
        ↓
IMMUTABLE SOURCE DOCUMENT / API PAYLOAD
        ↓
VERSIONED PARSE RUN
        ↓
SOURCE BLOCKS / GROUPS
        ↓
PROVIDER-NATIVE RECORDS
        ↓
APPEND-ONLY REVIEW / CORRECTION OVERLAY
        ↓
-------------------------------
LATER CONTROLLED PHASES
-------------------------------
        ↓
TRUCKERP CANONICAL RECORDS
        ↓
RECONCILIATION + RESOLUTION GATES
        ↓
FINANCIAL RESPONSIBILITY / O/O PRICING
        ↓
SETTLEMENT / POSTING
```

The missing layer is the provider-native evidence boundary between the source document and the canonical financial tables.

---

# 3. Current feature-branch findings

Fuel work is checkpointed on branch:

```text
feat/fuel-card
```

Known checkpoint commit from the investigation:

```text
dd454804b34bea28c0831816091338fc112d3863
feat(fuel): checkpoint fuel card module segments 0A-9
```

Important findings:

## 3.1 `FuelSourceBatch` currently mixes source identity and parser interpretation

The same object currently holds provider/source metadata, storage reference/hash, profile/parser version, review state and lifecycle status.

Target design separates:

```text
fuel_source_document
        = immutable evidence identity

fuel_parse_run
        = one interpretation of that evidence using one profile/parser version
```

The same immutable PDF must be able to have multiple explicit parse runs later without rewriting the original source.

## 3.2 Canonical fields are populated too early

The current `FuelTransaction` model contains normalized/canonical fields such as quantity, unit price, tax, normalized currency and other financial-facing fields directly at ingestion time.

Those records should move downstream of reviewed native evidence.

## 3.3 Provider profile currently maps native labels directly into canonical field names

The current provider profile contains useful layout anchors, row recognition and provider/version evidence, but still performs aliases such as provider-native labels into canonical field names.

The profile should instead become a **native source structure manifest** first:

```text
provider PDF/API
        -> native structure manifest
        -> exact source labels / exact source blocks / exact source row types
```

Canonical meaning comes later.

## 3.4 BVD card context must not be treated as a transaction column

For BVD, `Transactions for card` is group/inherited context.

It is not one of the exact transaction-table columns.

Target structure:

```text
CARD_TRANSACTION_GROUP
    context: card = 4237111
        ↓
    TRANSACTION_TABLE
        ↓
    child records inherit/reference group context
```

## 3.5 Existing Review UI shell is reusable

The existing review screen already has the useful shell:

```text
LEFT  = original source PDF
RIGHT = extracted/reviewed data
```

It also already has review progress, correction reason and a Process boundary.

The problem is that the right side is currently driven by a hardcoded canonical display-field list.

Target:

```text
backend provider profile/view model
        ↓
provider-specific dynamic review renderer
```

BVD and Nationwide may therefore show completely different native columns while still using the same review engine.

## 3.6 Existing review correction concept is useful but must move earlier

The append-only correction/audit idea should be retained.

However, corrections should apply to provider-native evidence before canonical financial records are generated.

A native correction should identify the exact field deterministically, for example:

```text
record_id
field_ordinal
source_label_snapshot
native_raw
reviewed_raw
reason
```

Native evidence itself is never overwritten.

## 3.7 Existing financial segments are not automatically discarded

The investigation conclusion is **not** to throw away Segments 3-9.

Potentially reusable later:

- provider connection / RBAC framework;
- tenant-scoped patterns;
- money helpers;
- historical resolution framework;
- O/O pricing framework;
- reconciliation framework;
- audit concepts;
- review queue shell;
- PDF viewer;
- existing regression tests that remain semantically valid.

They move behind a stronger native-evidence boundary.

---

# 4. BVD-first native evidence design checkpoint

BVD is the reference implementation.

Target source structure:

```text
DOCUMENT
│
├── INVOICE_HEADER
│
├── CLIENT_INFO
│
├── CARD_TRANSACTION_GROUP
│     context:
│     Transactions for card = <card>
│
│     └── TRANSACTION_TABLE
│           ├── TRANSACTION
│           ├── SUBTOTAL
│           ├── TRANSACTION
│           └── SUBTOTAL
│
├── PAGE1_SUMMARY_CONTROL
│
├── GRAND_TOTALS
│
└── LEGEND
```

The exact BVD transaction-table contract is the provider's exact 21 native columns, in source order:

```text
Auth Code
Driver Name
Unit #
Date
Site #
Site Name
Site City
Prov/ST
Prod
QTY
Retail
Billed
Pre Tax AMT
HST
GST
PST
QST
Disc Rate
Disc AMT
Final AMT
CUR
```

Do not rename these into canonical accounting meanings during native extraction.

Native raw values remain strings.

Recommended native field representation is an ordered JSONB array rather than a JSON object so TruckERP can preserve:

```text
original column order
duplicate source labels
exact raw strings
per-value source evidence
```

Native field state should distinguish at minimum:

```text
PRESENT
BLANK
MISSING
UNREADABLE
```

A visibly blank source cell is not the same as a parser failure.

---

# 5. Native-evidence schema direction

Conceptual tables/roles to freeze before implementation:

```text
fuel_source_documents
fuel_parse_runs
fuel_native_blocks
fuel_native_records
fuel_native_review_events
```

Exact names may follow existing repository convention.

## 5.1 `fuel_source_documents`

Represents immutable evidence:

```text
id
tenant_id
source_type
storage_key
original_filename
mime_type
file_size_bytes
sha256
created_at
```

## 5.2 `fuel_parse_runs`

Represents one versioned interpretation:

```text
id
tenant_id
document_id
provider_code
profile_version
profile_manifest_sha256
parser_contract_version
status
layout_status
problem_summary_json
created_by
created_at
```

## 5.3 `fuel_native_blocks`

Represents document/group structure such as Client info, card group, Grand Totals or Legend.

Important candidate fields:

```text
id
tenant_id
parse_run_id
parent_block_id
block_type
seq
page_start
page_end
fields jsonb
raw_text
evidence jsonb
confidence
requires_review
```

## 5.4 `fuel_native_records`

Represents rows/records inside native blocks.

Important candidate fields:

```text
id
tenant_id
parse_run_id
block_id
structure_type
seq
page
fields jsonb
inherited_context jsonb
raw_text
evidence jsonb
confidence
requires_review
```

## 5.5 `fuel_native_review_events`

Append-only review overlay. Candidate actions:

```text
CONFIRM
FIELD_CORRECTION
RECLASSIFY
REJECT
```

Provider-native evidence itself remains immutable.

---

# 6. Parser / AI contract checkpoint

AI or deterministic parsing may assist only inside an approved provider profile.

Bad contract:

```text
Read this fuel statement and figure it out.
```

Allowed contract:

```text
This is approved BVD profile v1.
Find these known source structures.
Classify each block/row.
Return these exact approved BVD source labels in source order.
Preserve raw strings.
Return page/evidence.
Do not invent missing values.
Do not make financial/accounting interpretations.
```

Backend validation must mechanically verify the returned source structure before insertion.

AI/parser output never decides truck ownership, driver/payee authority, O/O pricing, settlement eligibility or posting.

---

# 7. Provider catalog correction to make later

Current catalog logic must be tightened to match evidence.

For now:

```text
BVD
    PDF_UPLOAD -> APPROVED

Nationwide
    PDF_UPLOAD -> APPROVED
```

Do not advertise structured/API methods as supported until the exact customer-facing interface or real source fixture is captured and approved.

This is particularly important because the current BVD catalog description itself notes that no evidenced structured BVD/T-Chek export sample exists.

---

# 8. Critical runtime investigation before any Fuel migration change

Before changing Fuel migrations, determine whether any Fuel tenant migrations from `feat/fuel-card` were ever applied to a real tenant database.

Decision gate:

```text
IF NEVER APPLIED
    -> redesign Fuel migrations cleanly before merge

IF ALREADY APPLIED
    -> do not rewrite migration history
    -> add forward/additive migrations
    -> preserve existing data
```

GitHub alone cannot answer this. It must be verified against the actual tenant database/migration state.

---

# 9. EC2/worktree safety checkpoint from 2026-09-20

Observed server state at pause:

## `~/trucking_erp`

This worktree is **not safe to reset, pull through divergence, or clean blindly**.

Observed state:

```text
HEAD detached from 7abdc283
many modified/deleted files
many untracked files
```

It contains active/uncommitted Load, DL, onboarding, frontend, docs and test work.

Do not discard or overwrite it while resuming Fuel investigation.

## `~/trucking_erp-prod-main`

Observed state before pull:

```text
branch: main
working tree: clean
behind origin/main by 3 commits
```

Then it was safely fast-forwarded:

```text
91bd80d5..ab3e426c
```

Only the three Fuel documentation files changed in that pull:

```text
docs/FUEL_CARD_IMPLEMENTATION_PLAN.md
docs/FUEL_CARD_MODULE_DESIGN.md
docs/FUEL_GOLD_MANIFEST.md
```

This clean `prod-main` worktree is separate from the dirty detached `~/trucking_erp` worktree.

Do not use the dirty detached worktree as a substitute for production-main state.

---

# 10. Resume point

When work resumes, do **not** begin coding immediately.

Resume in this order:

```text
1. Inventory current feat/fuel-card implementation
   -> KEEP / MODIFY / REPLACE / DEFER

2. Check real tenant DB migration state
   -> determine whether Fuel migrations were ever applied

3. Freeze exact BVD native manifest
   -> blocks, 21 transaction columns, card-group inheritance,
      page-1 controls, Grand Totals, Legend

4. Freeze native Postgres evidence schema
   -> document, parse run, block, record, review event

5. Freeze BVD extraction JSON contract + validator

6. Freeze BVD dynamic review UI contract

7. Only then implement the first narrow segment
```

First implementation segment should be limited to:

```text
Build only the native BVD evidence foundation.

Do not canonicalize.
Do not reconcile.
Do not price O/O.
Do not settle.
Do not deploy until the segment tests pass and the result is reviewed.
```

---

# 11. Pause declaration

Work is intentionally paused at the **investigation/design checkpoint**.

No further Fuel code or database action should be inferred from this document.
