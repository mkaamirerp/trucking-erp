# TruckERP — Load Rate Confirmation Semantic Parser Design

**Status:** DESIGN LOCK (discussion captured; not implemented as the new contract yet)  
**Scope:** Load / New Load rate-confirmation PDF parse only (not Fuel, not Load Lab product, not email intake rewrite)  
**Date captured:** 2026-08-13  
**Related:** live path today = `POST /api/v1/loads/parse-document` → guarded product parser (`load_document_parse_guarded` + diagnostics + OpenAI `gpt-4o-mini`)

---

## 1. Problem statement

The live New Load rate-con path extracts PDF text, builds **diagnostics** that already assign business meaning (`role_hint: broker_context|carrier_context`, `broker_party|carrier_party`, ranked references), embeds that dump in the OpenAI user message, then runs post-AI regex/guardrail repairs.

That is the wrong boundary.

**Pre-AI JSON must describe evidence, not decide the business meaning of that evidence.**

Once code guesses wrong (e.g. `carriers@…` → carrier MC, stop-level `Broker:` → freight broker, first PO → primary load id), OpenAI is handed a **biased** version of the document.

Armstrong identity work (prompt + diagnostics fix + candidate-backed repairs) improved one regression case. It must **not** become a second full-text semantic parser. The durable design is below.

---

## 2. Design principle

```text
PDF
  → acquisition (digital text | OCR)
  → evidence package (labels + context + ids; NO broker/carrier conclusions)
  → tenant_identity_exclusion (runtime, from THIS tenant's company profile)
  → OpenAI rate-confirmation semantic profile
  → RateConfirmationSemanticResult (with evidence provenance)
  → thin map → LoadDocumentParseResponse (New Load hydration)
```

OpenAI owns if/but party logic, primary reference selection, and person-specific contacts.

Post-AI may **cite-check** (cited value appears in evidence/page text) and hydrate. It must not re-parse the PDF into a competing semantic engine.

---

## 3. Why seven rate cons expose the design

Design fixtures (not broker hardcodes):

| Document | What it proves |
|---|---|
| **Armstrong** | Broker company ≠ agent person; after-hours / corporate / agent phones distinct; carrier MC/DOT vs broker MC; email local-part `"carrier"` must not decide MC role |
| **J.B. Hunt** | Explicit BROKER vs motor-carrier labels; broker contact may have email only (null phone better than claims/corporate/carrier number) |
| **TQL** | Primary identifier can be **PO#** (not always Load #); factoring address under carrier must not become broker |
| **Hub Group** | Clear Load # plus many stop PO/refs — POs must not replace primary load id |
| **RXO** | Multiple possible RXO legal names in boilerplate; Spencer = contact; Imran/647 = carrier side |
| **Landstar** | Issuer / load agent vs stop-level `Broker:` (e.g. customs) — “find the word broker” fails |
| **Agriculture** | Effectively no machine-readable text; rendered pages need **OCR before** semantics |

### Primary reference examples (semantic, not ranked enums)

| Document | Primary identifier (illustrative) |
|---|---|
| Armstrong | Load #3872125-1 |
| J.B. Hunt | Load Number 66P2859 |
| Hub | Load #2398968 |
| RXO | Load Confirmation 179967 (preserve LZ… separately if present) |
| TQL | PO# as rate-con id when that is how the broker identifies the load |
| Agriculture | Order Number when that is the prominent load id |
| Landstar | Freight Bill # as primary; preserve EL # separately |

Rigid `load_number > order_number > PO` ranking is **not** universally correct.

---

## 4. Dynamic JSON (runtime — not per broker)

There are **thousands of brokers**. Do **not** create a JSON file per broker.

**Dynamic JSON** = one object **assembled in memory at parse time** for:

1. **This authenticated tenant** (company profile from platform DB)
2. **This PDF** (pages + evidence)

Same builder for every tenant. IK, Jaysm, demo, unknown broker #1001: same function, different data.

```text
request tenant_id
  → PlatformTenant + PlatformCompanyProfile (or server cache)
  → normalize → tenant_identity_exclusion
  → PDF acquisition → pages + evidence
  → assemble RateConfirmationParseInput
  → OpenAI
```

Never:

- `brokers/armstrong.json`, `brokers/jbhunt.json`, …
- browser IndexedDB as authoritative identity for OpenAI
- hardcoded broker or tenant names/MC/phones in parser code

Tenant `brokers` table / dropdown MC-DOT resolution is a **later** step after semantic output is correct — not OpenAI input.

---

## 5. Tenant identity exclusion

### Source of truth (platform DB)

| Source | Fields |
|---|---|
| `PlatformTenant` | `id`, `name` (workspace / display name) |
| `PlatformCompanyProfile` | `legal_name`, `mc_number`, `usdot_number`, `cvor_number`, `operator_license`, `company_phone`, `company_email`, `address_*` |

Derived at runtime. Not a second stored profile copy that can drift.

### Conceptual shape

**Builder output (first implementation slice — flat):**

```json
{
  "names": ["IK Logistics", "9582479 Canada Inc"],
  "mc_numbers": ["1397898"],
  "usdot_numbers": ["3842541"],
  "cvor_numbers": [],
  "phones": ["6472419696"],
  "emails": ["info@iklogistics.com"],
  "email_domains": ["iklogistics.com"],
  "addresses": [
    {
      "street": "123 Example St",
      "city": "Brampton",
      "region": "ON",
      "postal": "L6T2T4",
      "country": "CA"
    }
  ]
}
```

Public mailbox domains (`gmail.com`, `hotmail.com`, `outlook.com`, `yahoo.com`, …) must **not** appear in `email_domains`.

Module: `app/services/load_parser_tenant_identity_exclusion.py`.

**Later OpenAI assembly** may wrap this object and optionally present hard identifiers (MC/USDOT/CVOR) separately from supporting values in the prompt. Nested wrap example:

```json
{
  "tenant_identity_exclusion": {
    "tenant_id": 53,
    "hard_identifiers": {
      "mc": ["…"],
      "usdot": ["…"],
      "cvor": ["…"],
      "operator_license": ["…"]
    },
    "identity_values": {
      "names": ["…display/legal/DBA as stored…"],
      "phones": ["6472419696"],
      "emails": ["info@example.com"],
      "addresses": [
        {
          "street": "…",
          "city": "…",
          "region": "…",
          "postal": "…",
          "country": "CA"
        }
      ]
    }
  }
}
```

(Operator licence and nested wrap are **not** required in the first builder slice.)

### Normalization

- Phone → digits only (prompt: formatting variants match); NANP 11-digit values starting with `1` store the last 10 digits
- MC / USDOT / CVOR → digits (leading zeros stripped); no invented format variants
- Email → lowercase; `email_domains` from company email only when not a public provider
- Names → collapse whitespace; keep display casing; dedupe case-insensitively
- Address → non-empty fields only; region/country uppercased; postal spaces collapsed
- Do **not** invent every visual phone variant in the JSON
- Missing/null profile fields → empty arrays (never `null`, `"None"`, or `""` list entries)

### Hard vs supporting

- **Hard:** MC / USDOT / CVOR / operator licence → strong “this party is us”
- **Supporting:** name, phone, email, address → alone, city/region is never enough

### AI instruction (conceptual)

Treat matching parties as **our carrier / tenant**.  
Use that to understand the transaction side.  
Do **not** emit those values as broker company, broker contact, or broker address.  
Do not erase them from reasoning.

### Cache (server-side, load-parser only)

```text
get_load_parser_tenant_identity(tenant_id)
  cache key: load_parser_tenant_identity:{tenant_id}
  (optional: bind to profile.updated_at)
  TTL 30–60 minutes
  invalidate on company profile SAVE
```

- Trusted backend only (works for New Load, email intake, future API)
- **Not** browser IndexedDB as source of truth
- Fuel does not share this object until Fuel has its own profile

### Demo caveat (tenant 53 as of 2026-08-13)

Live `platform_company_profiles` for tenant 53 is **not** IK Logistics (placeholder `legal_name` / MC / USDOT; phone/email null). Exclusion is only as good as the profile. Fixture PDFs that show IK as carrier still work via PDF evidence; exclusion prevents confusing **us** with the broker when the profile is real.

---

## 6. RateConfirmationParseInput (conceptual)

Three layers:

### A. Acquisition / document

```json
{
  "profile": "rate_confirmation",
  "document": {
    "filename": "Armstrong.pdf",
    "page_count": 3,
    "acquisition_method": "digital_text",
    "text_quality": "good",
    "pages": [{ "page": 1, "text": "…" }]
  }
}
```

Rule:

```text
digital PDF → text extraction
scanned / empty text → OCR
                 ↓
            same evidence + pages contract
                 ↓
            OpenAI rate-con profile
```

If text is empty, do **not** call the model on blank pages; return `needs_ocr` or run OCR first. Agriculture is the fixture that requires OCR. OCR implementation is a separate slice.

### B. Evidence (no conclusions)

Preserve observed labels from the PDF (`Carrier Name`, `BROKER Contact`, `After Hours`, `PO #`, `Bill To`, `Load #`, …). Attach `id`, page, short context.

Buckets (illustrative): `organizations`, `people`, `authority_numbers`, `contacts`, `references`, `money`, `stops`, `equipment`, `weights`.

**Deliberately missing from evidence:**

- `broker_party` / `carrier_party`
- `broker_mc` / `primary_phone`
- `role_hint: broker_context`

Proximity heuristics may feed **context strings**; they must not become conclusions in the input JSON.

### C. Tenant exclusion

Runtime object from §5.

---

## 7. RateConfirmationSemanticResult (conceptual)

OpenAI returns semantic structure with **provenance**, not product snapshot field names only.

Illustrative:

```json
{
  "document_type": "rate_confirmation",
  "carrier": {
    "is_tenant": true,
    "company_name": "…",
    "tenant_match_basis": ["mc_number", "dot_number"],
    "evidence_ids": ["org_1", "auth_1"]
  },
  "broker": {
    "company_name": "Armstrong Transport Group",
    "mc_number": "555609",
    "evidence_ids": ["org_2", "auth_3"],
    "confidence": "high"
  },
  "broker_contact": {
    "name": "Loflin Phillips",
    "phone": "208-751-8073",
    "email": "l.phillips@armstrongtransport.com",
    "evidence_ids": ["person_1", "contact_1"],
    "confidence": "high"
  },
  "primary_load_reference": {
    "value": "3872125-1",
    "source_type": "load_number",
    "evidence_id": "ref_1"
  },
  "references": [],
  "carrier_rate": {
    "total": 1800.0,
    "currency": "USD",
    "evidence_ids": ["money_1"]
  },
  "stops": [],
  "warnings": []
}
```

Rules of thumb for the model:

- Individual agent ≠ broker company
- Factoring / QuickPay / AP / shipper / receiver / customs broker / insurer ≠ freight broker by default
- Prefer person-specific phone/email; do not substitute after-hours, corporate main, claims, AP
- Primary load reference = broker’s principal id for this shipment (whatever label the document uses)
- Rate = compensation to our carrier; distinguish linehaul/total from detention, TONU, late fees, QuickPay fees, lumpers
- Landstar: issuing broker / load agent vs stop-level `Broker:` (may map to `customs_broker_name` or stop note in product layer — not `broker_name_snapshot`)

No hidden chain-of-thought required; provenance via `evidence_ids` / snippets.

---

## 8. Product mapping (existing hydration contract)

Keep New Load hydration on:

`LoadDocumentParseResponse` / `LoadParseExtractedFields`
(`broker_name_snapshot`, `broker_contact_*`, `broker_load_reference`, `rate`, `stops`, …)

Thin adapter only:

`RateConfirmationSemanticResult` → snapshots.

Do not force the model to invent product field names as its only brain. Do not put new business rules in the adapter.

---

## 9. What current live OpenAI hand-off looks like (baseline)

As of 2026-08-13, a dump of the exact Chat Completions body for Armstrong (minus Authorization) was captured for review:

- Host path example: `/home/admin/openai_handed_armstrong.json`
- Endpoint: `POST https://api.openai.com/v1/chat/completions`
- Model: `gpt-4o-mini`, temperature `0.1`
- Messages: system prompt + user text that embeds:
  - extraction instructions
  - `PRODUCT_PARSE_DIAGNOSTICS` (JSON string, capped ~20k chars) including **role_hint / broker_party**
  - extracted PDF text
- Schema: `load_document_parse_guarded_truckerjson_v1`
- **Not sent:** `tenant_id`, `tenant_identity_exclusion`, company profile

This baseline documents why the architecture must change: diagnostics already assert meaning before the model runs.

---

## 10. Explicit non-goals (this design slice)

- Per-broker JSON packs or broker catalog as OpenAI input
- Browser IndexedDB as identity authority for parse
- Fuel / other document profiles (separate later)
- Shared `pdf_pipeline` mega-framework (unless later locked)
- Frontend broker dropdown / MC-DOT alias resolution (after parser correctness)
- Expanding post-AI full-text regex semantic ranking as the long-term brain
- Implementing OCR in the same slice as the JSON contract (record Agriculture as requiring it)

---

## 11. Implementation order (when approved)

1. Freeze **RateConfirmationParseInput** + **RateConfirmationSemanticResult** field lists in this doc (or linked schema files).
2. Hand-author expected semantic JSON for the seven fixture PDFs.
3. Spec `build_load_parser_tenant_identity(tenant_id)` + cache invalidate-on-profile-save (no product code until approved).
4. Implement acquisition → evidence (labels only) → exclusion → OpenAI → cite-check → hydrate.
5. Retire / shrink diagnostics conclusions (`role_hint`, party roles as inputs) and the tactical identity guardrail stack as the new path lands.
6. OCR path for empty-text PDFs (Agriculture).

Do **not** start coding the new contract until the JSON shapes and seven expected results are accepted.

---

## 12. Relationship to uncommitted Armstrong identity fix

Tactical work may remain in the working tree (prompt contract, email-local-part MC hint, company/person inconsistency repair, contact repair from **existing** `contact_candidates` only — no full-text phone/email rescan).

That path can stabilize today’s product. It is **compatible with “don’t ship more regex as the brain,”** not with “diagnostics conclusions forever.”

When this design ships, most pre-AI role conclusions and agent-phone scoring should go away in favor of evidence + tenant exclusion + OpenAI + cite-check.

---

## 13. Acceptance criteria (design)

- [ ] No broker-specific JSON files or hardcoded broker identities in parser code
- [ ] Tenant exclusion built only from platform tenant + company profile (dynamic per request)
- [ ] Evidence input has observed labels; no `broker_party` / `role_hint` conclusions
- [ ] OpenAI selects broker company, agent contact, primary reference, rate with provenance
- [ ] Seven fixtures have expected semantic results before code
- [ ] Empty-text PDFs require OCR (or explicit `needs_ocr`) before semantics
- [ ] Product hydration remains `LoadDocumentParseResponse`
- [ ] Server-side identity cache; invalidate on profile save; no IndexedDB authority

---

## Document control

| Field | Value |
|---|---|
| Owner | TruckERP load intake / parse |
| Location | `docs/TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md` |
| Supersedes | Ad-hoc chat conclusions on rate-con identity / evidence vs conclusions (2026-08-13) |
| Next doc update | When input/output schemas are field-frozen and golden fixtures attached |
