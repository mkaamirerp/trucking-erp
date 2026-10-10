# Broker / email intake — QR-derived references (design)

## Product rule

- QR-derived data **does not replace** parsed load/broker fields from rate cons or email body.
- It is **supplemental ingestion metadata**: first-class structured rows for matching and audit, not a second copy of load/broker truth.
- **Many QR rows per message or attachment** are allowed (distinct payloads).
- **Lineage** is always tenant → thread → message → optional attachment.
- QR remains a **separate matching signal** from the locked **booking broker** identity path (known senders, domains, aliases).
- **Customs broker** stays a separate concept; `linked_load_id` may point at a load that also has `customs_broker_id`, but QR rows are not customs artifacts.

## Purpose

Brokers (e.g. TQL-style rate cons) may embed **QR codes** carrying a compact token or URL. Later emails may reference the same shipment flow without repeating the full document. Intake should:

1. **Persist** decoded QR payload when extraction runs (PDF/image/body pipeline).
2. **Query** by lineage, raw/normalized value, or linked load for correlation and confidence — without scraping OCR blobs.

## Data model (`email_intake_qr_extractions`)

One row per **decoded QR instance** (multiple distinct QRs per attachment/message ⇒ multiple rows).

| Column | Role |
|--------|------|
| `tenant_id` | Tenant isolation |
| `thread_id` | Thread-scoped queries (`email_threads.id`) |
| `message_id` | Source message (`email_messages.id`, required) |
| `attachment_id` | Optional `email_message_attachments.id` when the QR came from a stored attachment; **NULL** if decoded from inline / body-only processing |
| `raw_value` | **Exact** decoded QR string — audit truth; **never overwritten** after insert |
| `normalized_value` | Optional normalized match key (trim, URL canonicalization, etc.); safe to use for fuzzy/deduped *lookups* when set |
| `extracted_from_source_type` | `pdf` \| `image_attachment` \| `email_body_image` \| `other` — where decoding ran |
| `page_number` | Optional **1-based** page when source is PDF; NULL for non-PDF or unknown (bounding box deferred) |
| `format_hint` | Optional: `unknown`, `url`, `plain`, product-specific labels later |
| `decoder_backend` | Optional: which extractor was used (audit/debug) |
| `parse_status` | e.g. `ok`, `partial`, `failed` |
| `confidence` | Optional numeric |
| `notes` | Operator/system notes |
| `linked_broker_id` | **Nullable** booking broker; often set **after** intake classification or human verification |
| `linked_load_id` | **Nullable** load; set when a load is created/linked — may be **later** than extraction |
| `created_at` / `updated_at` | Audit |

**Scope:** Intake / email / load-context metadata only — **not** a generic app-wide QR storage bucket.

## 1. Duplicate rule (exact dedupe)

Re-processing the **same** attachment or body must **not** insert duplicate rows for the **same** decoded string.

**Enforced in the database** (partial unique indexes):

- When `attachment_id IS NOT NULL`: **unique** `(tenant_id, attachment_id, raw_value)`.
- When `attachment_id IS NULL` (body/inline path): **unique** `(tenant_id, message_id, raw_value)`.

**Not deduped:** two different attachments with the same `raw_value`, or the same payload appearing on different messages — those are distinct rows (distinct lineage). Intake code should use `app.services.email_intake_qr_extractions.record_intake_qr_extraction` for **idempotent** inserts aligned with these rules.

**Parse-attempt model:** If we later need multiple attempts per lineage (e.g. failed then retry), store attempts in separate audit/logging tables — **not** by loosening exact dedupe on `raw_value` for the same attachment/message.

## 2. Source type (`extracted_from_source_type`)

Canonical set (see `EXTRACTED_FROM_SOURCE_TYPES` in code): `pdf`, `image_attachment`, `email_body_image`, `other`.

## 3. PDF location readiness

`page_number` is supported now. Bounding box / coordinates are intentionally **out of scope** until a later iteration.

## 4. Raw vs normalized

- **`raw_value`:** immutable decoded payload.
- **`normalized_value`:** optional; used as a match key when policy defines normalization. Index: `(tenant_id, normalized_value)` **where** `normalized_value IS NOT NULL`.

## 5. Linked broker / load timing

`linked_broker_id` and `linked_load_id` are **nullable** and may be **NULL at insert**. They can be populated in a **later** step (classification, load creation, human verification). Extraction persists facts; linking is workflow-specific.

## 6. Query contract (primary access paths)

Intended high-value queries:

| Pattern | Typical filter |
|--------|-----------------|
| By tenant + raw | `tenant_id`, `raw_value` (and optionally `normalized_value` when set) |
| By lineage | `tenant_id` + `thread_id` / `message_id` / `attachment_id` |
| By linked load | `tenant_id`, `linked_load_id` |

Helpers: `app/services/email_intake_qr_extractions.py` (`list_intake_qr_by_*`, `record_intake_qr_extraction`).

## Indexes (summary)

- `tenant_id`, `thread_id`, `message_id`
- `(tenant_id, attachment_id)`
- `(tenant_id, raw_value)`
- `(tenant_id, normalized_value)` partial (non-null)
- Partial **unique** indexes for dedupe (above)

## Ingestion precedence (relationship to other signals)

**QR is not a replacement** for parsed load fields or for broker identity resolution from headers/domains/aliases.

**Suggested integration order in intake (conceptual):**

1. Resolve **booking broker identity** using locked rules: known sender email → contact email → domain strict alias/name heuristics (existing pipeline).
2. In parallel or as a **second stage**, read **`email_intake_qr_extractions`** by `tenant_id` + `raw_value` / lineage / `linked_load_id` to **correlate** follow-up mail with an earlier document or **suggest the same load**.
3. **Product-defined** tie-break when QR and From-domain disagree — implement in code with explicit logging; the table stores facts, not the policy.

## UI / API (future)

- List/filter QR extractions per thread or attachment in ops/debug UI.
- Broker detail may show “recent QR tokens linked to this broker” via `linked_broker_id` (optional).

## Customs broker

QR extractions are **booking/intake** artifacts. They do not replace **customs broker** flows; the same load may carry both independently.
