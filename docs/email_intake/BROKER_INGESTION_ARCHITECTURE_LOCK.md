# Broker ingestion — architecture lock

**Status:** locked. Changes require explicit architecture review.

**Scope:** broker ingestion, broker resolution, load broker snapshot behavior only. Final rules only—no brainstorming.

---

## Purpose

Define non-negotiable architecture for **booking broker** resolution across **global reference**, **tenant workspace**, and **load snapshots**; pipeline ordering; confidence and conflicts; idempotency and dedupe; review; snapshot lifecycle and provenance.

---

## Locked Architecture

### Three layers (unchanged)

| Layer | Role | Tenant visibility |
|--------|------|-------------------|
| **Global reference** | Platform-owned canonical matching keys (identifiers, domains, known-from addresses, MC/DOT normalization). **Classification / dedupe / day-one matching.** | **Read-only** to tenants. |
| **Tenant workspace** | Operational brokers graph: `brokers` + contacts, domains, aliases, known senders; overrides, notes, status. | Tenant RBAC. |
| **Load snapshot** | **Historical truth** on the load (broker identity and linked fields). **Not** the resolver source for new messages. | Immutable after confirmation (see **Snapshot Rules**). |

**Rule:** New messages resolve from **tenant workspace first (where applicable)**, then **global reference** for day-one; snapshots are **written** from that outcome when policy allows—never read back as the sole authority for a *new* inbound message.

### Global promotion

- **Owner:** platform operations (platform DB role).
- **Queue:** changes to global reference enter **promotion**; only **approved** rows are canonical for production intake.
- Tenants **do not** edit global reference; optional **suggest** paths still flow through queue.

---

## Resolver Order

1. **Raw intake log** persisted **before** interpretation/reconciliation (see **Idempotency / Duplicate Handling**).
2. **Idempotency gate:** if this provider message / content hash was already processed per locked policy, **do not** silently create a second draft load—**discard safely** or **attach/update** the existing intake/draft deterministically (audited).
3. **Attachment hash:** compute **SHA-256** per attachment; skip redundant heavy extraction on same hash where policy allows; hash is **dedupe/retry control only**, not a business substitute.
4. **Booking broker resolution (tenant path first):** **known sender (exact)** → **domain** → **normalized alias** (locked tenant pipeline). If no tenant hit, **global reference** must still allow **day-one** match (single decisive candidate per confidence rules).
5. **Supplemental signals:** QR rows, PDF/body parses—**correlation / audit only**; they **do not** replace step 4 unless **hard conflict** rules govern the outcome.
6. **Blocked tenant broker:** if the match is a tenant broker **blocked / disallowed** by tenant policy → **no silent** auto-attach or auto-create → **review** with reason code `BLOCKED_BROKER`.
7. **Workspace materialization:** apply **Auto-Create Policy** when global → tenant row is required.
8. **Multi-load:** one email/PDF may yield **multiple** draft loads when extraction confidently finds distinct loads; each draft **retains lineage** (same source message/thread/attachment ids).
9. **Load linkage:** attach `broker_id` and populate **snapshot fields** including **match provenance** (see **Snapshot Rules**).
10. **Partial failure:** a stage failure **must not** always abort the whole intake; stages may emit **warnings**; record may continue with **`review_required`** (or equivalent). *Example:* broker matched at tier B but phone extraction failed.

**Field traceability:** for phone, email, domain, broker name/alias candidate, MC/DOT—persist **raw extracted** and **normalized** values where extraction runs; both are required for debug and audit (not optional “nice to have”).

---

## Confidence / Conflict Rules

### Signal strength (deterministic, no ML)

Contributing signals, **strongest first:**

1. **Known sender** (exact normalized From) — tier **A**.
2. **Domain** match on From with **at most one** active owner (tenant or global-backed path) — tier **B**.
3. **Strict alias** / normalized display match per locked normalization — tier **C**.
4. **Global key** (MC/DOT/normalized legal) with no tenant conflict — tier **D**.

**Weakest:** unanchored **fuzzy / loose name** match — **never** auto-creates a tenant broker, **never** auto-attaches to a load; may only contribute **review** suggestions.

**Conflicts that block auto-resolution:**

- Two+ active tenant brokers share same **domain** or **known sender** (auto-path **blocked**; fix master data).
- **Global vs tenant workspace** disagree on the same From/domain with no reconciliation rule → **block** auto-link; stable error/reason codes.
- **Supplemental (QR/PDF)** contradicts step-4 resolution → **no silent merge**; **hold** or **review**; **never** overwrite **frozen** snapshot.
- **Customs broker** stays **out** of this pipe.

**Ties:** same tier, multiple brokers → **no auto-pick** → **review** + deterministic **tie** reason code.

### Negative cache / blocklist

- **Narrow**, **reviewable** list of **sender/domain patterns** (e.g. generic no-reply) that **skip** repeated matching attempts.
- **Must not** hide likely-valid load traffic without **explicit policy** and audit visibility.
- Purpose: reduce noise and wasted retries only.

---

## Auto-Create Policy

- **Empty workspace / day-one:** global reference **alone** must support intake when tenant graph is empty (single candidate per confidence rules).
- **Default:** on tier **A** or **B** when global resolves one canonical broker **not** in workspace → **auto-create** tenant `brokers` row (mirror global; link `global_id` if modeled).
- **Opt-out:** tenant flag “no auto-create from global” → **suggest-only** until human creates broker.
- **Tier C/D:** no auto-create without confirmed policy / human—see **Confidence / Conflict Rules**.
- **Metadata on system-created rows (behavioral lock):**  
  - `created_by_system = true` (or equivalent).  
  - `origin = global_reference_match` (or equivalent).  
  - `needs_review` set per tier/policy (**true** for C/D and whenever auto-create is marginal).

---

## Review Rules

### Reason codes (non-exhaustive; stable strings for API/logs)

| Code | Use |
|------|-----|
| `WRONG_BROKER_MATCHED` | Human indicates resolver picked wrong broker. |
| `DUPLICATE_SUSPECTED` | Same broker + same commercial reference within recent window (see **Idempotency / Duplicate Handling**). |
| `BLOCKED_BROKER` | Match hit tenant-blocked broker. |
| `NOT_A_LOAD` | Inbound classified as non-load. |
| `INSUFFICIENT_CONFIDENCE` | Below auto threshold or tier D without corroboration. |
| `CONFLICTING_SIGNALS` | Header-derived vs supplemental (or global vs tenant) clash. |
| `SNAPSHOT_CORRECTION` | Draft/review correction of broker snapshot fields. |

**Queue discipline:** transitions (enqueue, claim, resolve) are **auditable** (who/when/outcome).

**SLA:** items exceeding configured **review SLA** must **escalate** or **surface prominently** (no fancy realtime UI required—alerts/dashboard/report is sufficient).

---

## Snapshot Rules

### Lifecycle

- **Draft / review:** snapshot fields **editable** with normal load edit audit.
- **Confirmed / locked:** snapshot **frozen**; tenant broker edits **do not** backfill confirmed loads.

### Provenance (required on snapshot / linked intake record)

- **`match_method`** (enum-style): e.g. `exact_known_sender`, `exact_domain`, `exact_alias`, `exact_mc`, `exact_dot`, `global_reference_key`, `fuzzy_name_suggestion_only`, `manual_override`, `qr_supporting_signal` (supplemental **never** alone implies `exact_*` without tier A–D path).
- **`match_confidence`:** tier **A / B / C / D** or numeric mapping **fixed in product config** (deterministic).
- **Optional `match_explanation` / structured provenance** for debugging.

### Retention / link survival

- Snapshot remains **historical truth** for retention period regardless of later **archive / merge / block / delete** of tenant broker or broken live `broker_id`.
- Live FK may become null or stale; **snapshot text/ids copied at write time** must remain **intact**.

### Post-freeze correction (exceptional)

- **Narrow escape hatch:** privileged correction **after** freeze **only** with **full audit**; **not** normal workflow.

### Duplicate load suspicion

- If **same broker** + **same commercial reference** (load ref / tracking / order # per policy) recurs inside a **defined recent window** → **flag** duplicate suspect; **do not** silently create multiple operational loads.
- Route to **review** or **explicit merge/confirm** per policy.
- Implementation may use nullable **`is_duplicate_of_load_id`** (or equivalent) for lineage.

---

## Idempotency / Duplicate Handling

### Raw intake (pre-interpretation) log

Before interpretation/reconciliation, persist a **raw intake** record including where available:

- Provider/raw message identifiers  
- **Full headers**  
- **Subject**  
- Sender/recipient **envelope**  
- Body **text/html**  
- **Received** timestamp  
- **Attachment** metadata (name, mime, size, **SHA-256**)

**Purpose:** debug, replay, reprocessing, audit.

### Message-level idempotency

- Before heavy processing, check whether the **same provider message id** and/or **content hash** was processed within policy window.
- **Duplicates:** never silently create a **second** draft load; either **safe discard** (audited) or **idempotent attach/update** to the same intake/draft per **deterministic** policy.

### Attachment hashing

- **SHA-256** per attachment **mandatory**.
- Duplicate hash → **skip** redundant extraction where appropriate; hash does **not** replace business matching decisions.

---

## Operational Ownership

- **Global reference + promotion queue:** platform operations.
- **Tenant workspace:** tenant admins per RBAC.
- **Review SLA / escalation:** tenant ops / product-defined owner + surfacing mechanism above.

---

## Out of Scope

- ML merge / probabilistic dedupe across tenants.
- **Fuzzy-name-only** auto resolution or auto-create.
- **Customs broker** in this booking-broker pipeline.
- Tenant **editing** of global reference.
- Fancy **realtime** conflict UI.
- Multi-admin approval workflows for snapshot override (unless added elsewhere)—override remains **rare, privileged, audited**.

---

## New additions in this revision

- Raw intake logging **before** interpretation (identifiers, headers, subject, envelope, bodies, timestamp, attachment metadata + hash).
- Message-level **idempotency** and **no silent duplicate drafts**.
- **SHA-256** per attachment; dedupe for reprocessing; hash not a business decision.
- **Raw + normalized** persistence for extracted phone, email, domain, name/alias, MC/DOT.
- **Negative cache / blocklist** rules (narrow, reviewable, policy-gated).
- Concrete **signal ordering**, **fuzzy name never auto-attaches/creates**, **ties → review**, explicit **conflict blocks**.
- **Blocked tenant broker** → review + reason code `BLOCKED_BROKER`.
- **Auto-created broker metadata:** `created_by_system`, `origin = global_reference_match`, `needs_review` by tier.
- **Duplicate load suspicion** (broker + commercial ref + window; optional `is_duplicate_of_load_id`).
- **Multi-load** split from one email/PDF with shared lineage.
- **Partial failure** → warnings, optional `review_required`, non-total abort.
- **Review reason codes** table + **auditable** actions + **SLA escalation** requirement.
- Snapshot **match_method**, **match_confidence**, optional **explanation/provenance**.
- **Retention:** snapshot survives broker archive/merge/block; live link may die, snapshot does not.
- **Post-freeze snapshot override:** privileged + **fully audited**, exceptional only.

---

## Revision history

| Date | Change |
|------|--------|
| 2026-04-04 | Initial lock. |
| 2026-04-05 | Restructured sections; added logging, idempotency, hashing, provenance, review codes, SLA, duplicates, multi-load, partial failure, blocked broker, negative cache, snapshot retention & override. |
