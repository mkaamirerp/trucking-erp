# Extraction learning — tenant isolation + platform improvement

## Purpose

Describe how TruckERP can **improve parsing and guardrails over time** while keeping **each tenant’s business data in the tenant database**. The platform may hold **only sanitized, non-identifying learning artifacts** so extraction quality can improve for all customers without building a global warehouse of private PDF content.

**Related:** `CORRECTION_LEARNING_LAYER_CONCEPT.md` (maturity model, correction history), `ML_DEEP_LEARNING_ARCHITECTURE.md` (layers), `CRITICAL_EXTRACTION_CONTRACT_v1.1.json.md` (field contract).

---

## Core principle

**Do not store private field values globally.**

Store **how** a value was found, **from which section/label context**, and **why** it was accepted, rejected, or corrected — not the secret payload itself, when that payload belongs to a single carrier’s operations.

- **Tenant DB:** may retain **full** parse observations, corrections, and document snippets needed for that tenant’s support and learning (under your retention and security policy).
- **Platform DB:** may retain **only** patterns, counts, shapes, and broker/document-family metadata that are **inherently non-identifying** or **already public / directory-level** (e.g. which label on a TQL form tends to map to which field *role*).

---

## What lives in the tenant database (private, full fidelity)

The tenant is the system of record for “what happened on our loads.”

**Typical record families (illustrative):**

| Concept | Description |
|--------|-------------|
| **Raw AI output** | Full structured output for a run/field (as returned before/after guardrails), tied to `tenant_id` + load lab / workspace context. |
| **Final operator value** | What dispatch actually saved (may differ from AI). |
| **Source text** | Snippet or normalized span reference **for that tenant’s document** (not replicated to platform). |
| **Source page** | Page index for audit and re-training locally. |
| **Field path** | e.g. `extracted.broker_load_reference`, `critical_extraction.broker_name`, `stops[0].city`. |
| **Correction type** | e.g. `override`, `clear`, `remap_label`, `demote_to_secondary`, `confirm`. |
| **Timestamp / user** | Who changed it, when (for dispute and maturity). |
| **Run / document id** | Internal pointers only; not exported raw to platform. |

**Use:** per-tenant analytics, UI diff review, local rule proposals, and **inputs to a sanitization job** that emits platform patterns (below).

**Hard rule:** Treat addresses, rates, person names, free-text emails, and full stop lists as **tenant-private** unless the operator explicitly approves a **redacted** export for a specific pattern study.

---

## What may live in the platform database (sanitized patterns only)

Platform storage is for **cross-tenant quality**: better defaults, label→role priors, and maturity-weighted behavior — **without** a shared cache of customer paperwork.

**Allowed dimensions (examples):**

| Dimension | OK to store (sanitized) | Do **not** store globally |
|-----------|-------------------------|---------------------------|
| **Broker / document family** | Public or directory-level identity: e.g. “TQL”, “J.B. Hunt”, “Armstrong” as **broker keys**; **document type** (rate con vs tender). | Tenant-specific free-text broker strings copied from a private PDF. |
| **Field path** | Stable path: `broker_load_reference`, `stops[].city`, etc. | — |
| **Source section pattern** | Normalized *role*: e.g. `stop_1_pickup`, `header_rate_confirmation`, `corporate_info`, `bill_to_block` (structural, not a street). | Verbatim address blocks, named facilities from PDFs. |
| **Source label pattern** | Normalized label: `PO#`, `Load Number`, `Freight Bill #`, `EL #` (string patterns or token classes). | Full title lines that embed shipper names. |
| **Value shape** | Regex / token class: `alphanumeric_6_12`, `has_digit`, `looks_like_phone` (metadata only). | Actual load #, rate, or PO value. |
| **Section role** | `pickup_context`, `broker_identity_context`, `accounting_context`, `carrier_block`. | — |
| **Positive / negative evidence counts** | Aggregates: “accepted 12 / corrected 1 for this (broker, field, label_pattern, section_role) tuple.” | Per-event private values. |
| **Confidence score** | Decayed by disputes and time. | — |
| **Maturity status** | Align with tenant-level concept: e.g. `observation` → `pattern_detected` → `suggestion` → `active_platform_prior` → `disputed` (names can mirror `CORRECTION_LEARNING_LAYER_CONCEPT.md`). | — |

**Sanitization rule:** If a string could identify a **specific shipper, receiver, or one-off consignee**, it does not go to platform. Replace with **structural** descriptors (see examples below).

---

## Examples (tenant vs platform)

### Pickup address

- **Not stored globally (bad):** “123 Main St, Chicago, IL …”
- **Stored globally (good):**
  - “Candidate came from **Stop #1** block labeled **Pickup** / **PU**; pattern **facility + street + city + state + zip**.”
  - “**Bill To** and **Remittance** sections were **rejected** as non-stop sources for this document family.”
  - “This structural pattern was **stable across 12** operator accepts and **1** demotion to review.”

### Load / reference value

- **Not stored globally (bad):** `34307972` or `66P2859` as a global key-value.
- **Stored globally (good):**
  - “For **TQL**-family documents, **PO#** in **header** strongly associates with **`broker_load_reference` role** (maturity: suggestion).”
  - “For **J.B. Hunt**-family, **Load Number** label maps to **`broker_load_reference`** (maturity: guarded_auto_apply in platform prior — after threshold).”
  - “For **Landstar**-family, **Freight Bill #** and **EL #** are **reference candidates**; primary load id selection depends on **maturity and negative evidence** (e.g. dispatch repeatedly cleared Freight Bill as primary).”

Counts and label associations are **statistical**; the platform never needs the actual number to learn that “PO#” in header is a strong TQL signal.

---

## How tenant data improves platform (pipeline)

1. **Capture** in tenant DB: AI output, operator final value, field path, correction type, local source pointers.
2. **Normalize** locally: map raw labels to `label_pattern` and sections to `section_pattern` / `section_role` (no PII in keys).
3. **Aggregate** per tenant: frequent (broker_family, field_path, label_pattern, section_role) → **deltas** and **stability** metrics.
4. **Propose** a **sanitized** platform pattern (no values, only shape + label + family + stats).
5. **Review** (human or policy job): optional platform admin approval before cross-tenant effect.
6. **Publish** to platform store with **maturity** and **confidence**; support **dispute** when new tenant corrections contradict the pattern.
7. **Deprecate** or **downgrade** on contradiction or drift (same as maturity `disputed` in concept doc).

**Nothing in step 4–6 requires shipping raw PDF text to the platform** — only derived metadata and counts.

---

## Runtime precedence (highest first)

When applying extraction, merging AI output, and guardrails, evaluate in this order (later steps cannot override a higher decision without explicit “break glass” or review):

1. **Tenant active extraction rules**  
   Rules explicitly enabled for this tenant (including tenant-only learned rules and overrides).
2. **Platform active extraction rules**  
   Sanitized, approved priors (label→field role, demotions, etc.).
3. **Broker-specific hints**  
   From broker directory + known document families (non-secret configuration).
4. **Generic extraction contract**  
   e.g. critical extraction v1.1 + Pydantic shape + static contract text.
5. **AI reasoning**  
   Model output (schema-constrained), treated as a proposal.
6. **Deterministic guardrails**  
   Reject instruction tokens, require digits for ref ids, section heuristics, etc.
7. **Human review**  
   Queue, UI flags, and “needs_review” on fields — final authority is always people for production loads when policy requires it.

**Note:** In dispute, (1) and (2) may be re-weighted; platform priors should **degrade** when per-tenant evidence consistently disagrees (see `disputed` in correction-learning doc).

---

## Security and product commitments

The **platform learning system must not**:

- Expose one tenant’s **raw PDF text**, **exact addresses**, **rates**, **driver names**, or **private email content** to another tenant.
- Use **cross-tenant value stores** (e.g. “all PO numbers seen”) as a training set.
- Send **unredacted** extraction payloads to a shared analytics bucket without **tenant_id** isolation and policy.

**May**:

- Use **public / directory broker keys**, **structural** section/label features, and **aggregated** statistics.
- Improve **default prompts, priors, and guardrail ordering** for everyone when patterns are provably **non-identifying**.

---

## Summary

| Store | Where | What |
|-------|--------|------|
| Full observations + corrections + snippets | **Tenant DB** | Everything needed to operate, audit, and learn locally. |
| Sanitized patterns + counts + maturity | **Platform DB** | **How** labels and sections map to field **roles** and **shapes** for broker/document families — **not** the private values themselves. |

This preserves **tenant data isolation** while allowing **platform-wide extraction quality** to improve from many tenants’ *behavior in the aggregate*, not from a shared copy of their paperwork.

---

## Implementation status (in repo)

- **Tenant table** `load_lab_field_learning_events` (Alembic tenant revision `v0a1b2c3d4e5`): append-only `ai_proposed` rows after a successful **Load Lab** semantic extract (key scalar paths + a few stop fields) and operator events via API.
- **API (tenant):** `GET/POST /api/v1/load-lab/runs/{run_id}/field-learning-events` — list and record operator overrides (tenant session only; values stay in tenant DB).
- **Platform table** `platform_extraction_sanitized_patterns` (Alembic platform `0044_platform_extraction_sanitized_patterns`): **sanitized** pattern rows only; **no** cross-tenant aggregation job yet.
- **API (platform admin key):** `GET/PUT /api/v1/platform/extraction-sanitized-patterns` — list and **manual** upsert of priors. `PUT` rejects patterns that look like email/street blobs (lightweight server-side check).

**Not implemented yet (follow-up):** automatic promotion from tenant events → platform priors, tenant-specific “active rule” table, and wiring **runtime precedence** (1)–(7) into the extraction pipeline. Those require product decisions and worker safety review.
