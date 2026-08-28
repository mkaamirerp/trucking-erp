# TruckERP — Load Rate Confirmation Semantic Parser Design

**Status:** **DESIGN LOCK + IMPLEMENTED / SHIPPED (Rate Confirmation v2)**  
**Implementation anchor:** local cutover commit `5498e6c4` (included in inspection branch `inspect/current-working-state-2026-08-28`).  
**Scope:** Load / New Load rate-confirmation PDF parse only (not Fuel, not Load Lab product, not email intake rewrite).  
**Current production path on this inspection branch:** `POST /api/v1/loads/parse-document` → `load_document_parse_rate_con.parse_pdf_bytes_to_load_document_response()` → page acquisition → cached tenant identity exclusion + frozen field rules + page-separated text → OpenAI `gpt-4o-mini` → mechanical validation → existing `LoadDocumentParseResponse` hydration.  
**Critical boundary:** no `PRODUCT_PARSE_DIAGNOSTICS`, `broker_party`, `carrier_party`, `role_hint`, ranked semantic candidates, or server-side semantic repair on the Rate Confirmation v2 handoff.

**Implementation note:** The original August 13 design explored a richer prebuilt “evidence package” and a separate provenance-heavy semantic result. The shipped v2 cutover intentionally uses the simpler frozen production handoff: **tenant identity exclusion + field rules + page-separated document text** under the existing product output schema. Historical conceptual sections below are retained where they explain the reasoning, but they do not override the frozen implemented contract.

---

## 1. Problem statement — historical pre-cutover baseline

Before the v2 cutover, the live New Load rate-con path extracted PDF text, built **diagnostics** that already assigned business meaning (`role_hint: broker_context|carrier_context`, `broker_party|carrier_party`, ranked references), embedded that dump in the OpenAI user message, then ran post-AI regex/guardrail repairs.

That was the wrong boundary.

**Pre-AI JSON must describe evidence, not decide the business meaning of that evidence.**

Once code guesses wrong (e.g. `carriers@…` → carrier MC, stop-level `Broker:` → freight broker, first PO → primary load id), OpenAI is handed a **biased** version of the document.

Armstrong identity work (prompt + diagnostics fix + candidate-backed repairs) improved one regression case. It was intentionally not allowed to grow into a second full-text semantic parser. The v2 cutover retires that diagnostics-as-brain path for the product Rate Confirmation parser.

---

## 2. Locked design principle and shipped v2 path

```text
PDF
  → acquisition (usable embedded text | OCR-required gate)
  → page-separated text
  + tenant_identity_exclusion (runtime, from THIS tenant's company profile)
  + frozen Rate Confirmation field_rules
  → OpenAI rate-confirmation semantic profile
  → existing schema-valid semantic JSON
  → mechanical validation only
  → LoadDocumentParseResponse (New Load hydration)
```

OpenAI owns broker/carrier interpretation, primary reference selection, contact meaning, rate meaning, and stop semantics.

Post-AI server code may perform **mechanical** checks only: schema/shape cleanup, exact/normalized tenant-exclusion matches, numeric/date/sequence sanity, weak literal-presence warnings, and leak stripping. It must not re-parse the PDF into a competing semantic engine.

The original richer “evidence IDs / provenance object” concept remains a possible future enhancement; it is **not required** to change the current v2 production contract.

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
2. **This PDF** (page-separated text)

Same builder for every tenant. Unknown broker #1001 uses the same code as any known broker; the runtime tenant profile and document text are different, not the parser implementation.

```text
request tenant_id
  → PlatformTenant + PlatformCompanyProfile (cached server-side)
  → normalize → tenant_identity_exclusion
  → PDF acquisition → pages[]
  → add frozen field_rules
  → assemble v2 handoff
  → OpenAI
```

Never:

- `brokers/armstrong.json`, `brokers/jbhunt.json`, …
- browser IndexedDB as authoritative identity for OpenAI
- hardcoded broker or tenant names/MC/phones in parser code

Tenant `brokers` table / dropdown MC-DOT resolution remains downstream product logic after semantic output; it is not the OpenAI input authority.

---

## 5. Tenant identity exclusion — frozen implemented contract

### Source of truth (platform DB)

The production builder intentionally uses only the following Rate Confirmation-relevant sources:

| Source | Fields used by the exclusion builder |
|---|---|
| `PlatformTenant` | `name` |
| `PlatformCompanyProfile` | `legal_name`, `mc_number`, `usdot_number`, `company_phone`, `company_email`, `address_street`, `address_city`, `address_postal` |

`cvor_number`, `operator_license`, address region/country, and unrelated company-profile fields are **not** part of the frozen first production exclusion shape. Do not expand this source list or output shape without new evidence and an explicit parser decision.

Derived at runtime. Not a second stored profile copy that can drift.

### Frozen flat shape

```json
{
  "names": ["Tenant Display Name", "Legal Company Name"],
  "mc_numbers": ["1397898"],
  "usdot_numbers": ["3842541"],
  "phones": ["6472419696"],
  "emails": ["info@example.com"],
  "email_domains": ["example.com"],
  "addresses": [
    {
      "street": "123 Example St",
      "city": "Brampton",
      "postal": "L6T2T4"
    }
  ]
}
```

**Exact top-level keys are frozen for this slice:**

`names`, `mc_numbers`, `usdot_numbers`, `phones`, `emails`, `email_domains`, `addresses`.

No `tenant_id` is sent inside this object. No nested `hard_identifiers` wrapper is used in the shipped v2 handoff.

Public mailbox domains (`gmail.com`, `hotmail.com`, `outlook.com`, `yahoo.com`, …) must **not** appear in `email_domains`.

Module: `app/services/load_parser_tenant_identity_exclusion.py`.

### Historical nested-wrap concept — not current contract

Earlier design discussion considered wrapping the exclusion in a richer nested object containing CVOR/operator-licence and region/country values. That is **not the production v2 contract** and must not be treated as an implementation target unless a later evidence-backed decision explicitly reopens the shape.

### Normalization

- Phone → digits only; NANP 11-digit values starting with `1` store the last 10 digits
- MC / USDOT → normalized authority id (digits when present; leading zeros stripped)
- Email → lowercase; `email_domains` from company email only when not a public provider
- Names → collapse whitespace; keep display casing; dedupe case-insensitively
- Address → `street`, `city`, `postal` only; postal spaces collapsed / uppercased
- Do **not** invent every visual phone variant in the JSON
- Missing/null profile fields → empty arrays (never `null`, `"None"`, or `""` list entries)

### Hard vs supporting

- **Hard:** MC / USDOT → strong “this party is us” identifiers
- **Supporting:** name, phone, email, address → useful corroboration but not authority-number equivalents

### AI instruction

Treat matching parties as **our carrier / tenant**.  
Use that to understand the transaction side.  
Do **not** emit those values as broker company or broker contact.  
Do not erase them from reasoning.

### Cache (server-side, load-parser only)

```text
get_load_parser_tenant_identity_exclusion(tenant_id)
  logical cache key: load_parser_tenant_identity:{tenant_id}
  in-process TTL: 1800 seconds (30 minutes)
  invalidate on company-profile create/update paths that change exclusion inputs
```

- Trusted backend only
- Cache stores plain dicts, not ORM instances
- Defensive copies prevent one parse from mutating cached state
- **Not** browser IndexedDB as source of truth
- Fuel does not inherit this Load-profile exclusion object automatically

### Demo/profile caveat

Exclusion quality is only as good as the canonical platform tenant/company profile. Fixture behavior must never justify hardcoding a tenant identity into parser code.

---

## 6. OpenAI handoff v2 — implemented production contract

The shipped v2 handoff is intentionally simpler than the original conceptual evidence-bucket design.

```json
{
  "handoff_version": "load_rate_con_openai_handoff_v2",
  "profile": "rate_confirmation",
  "tenant_identity_exclusion": { "...": "frozen flat shape from §5" },
  "field_rules": { "...": "frozen Rate Confirmation rules" },
  "document": {
    "filename": "Armstrong.pdf",
    "content_type": "application/pdf",
    "page_count": 3,
    "extraction_method": "product_pdf_text",
    "acquisition_method": "digital_text",
    "pages": [
      { "page_number": 1, "text": "..." }
    ]
  }
}
```

The handoff must not contain pre-decided business conclusions such as:

- `PRODUCT_PARSE_DIAGNOSTICS`
- `broker_party` / `carrier_party`
- `role_hint`
- `contact_candidates`
- ranked `reference_candidates`
- `financial_hints`
- `route_stop_hints`
- diagnostics-driven semantic repair instructions

### Acquisition / OCR gate

```text
digital PDF → embedded text extraction → page usability classifier → OpenAI
scanned / weak-text page → requires_ocr = true → controlled OCR-required response
```

OCR is **not implemented yet**. If any page is classified OCR-required, the Rate Confirmation production parser does not send blank/weak pages into OpenAI and does not fall back to the legacy semantic diagnostics path.

### Historical evidence-bucket concept

The earlier proposal to prebuild generic buckets such as `organizations`, `people`, `authority_numbers`, `contacts`, `references`, `money`, `stops`, `equipment`, and `weights` remains design history. It is not part of the current v2 handoff and should not be added casually; doing so could reintroduce a second semantic parser if those buckets begin assigning business meaning.

---

## 7. Semantic result / provenance direction

OpenAI currently returns the existing schema-owned semantic payload (`ParseDocumentSemanticModelOutput`) that maps into `LoadDocumentParseResponse`.

The original design proposed a richer `RateConfirmationSemanticResult` with explicit `evidence_ids` / provenance. That remains a possible future schema evolution, but **is not required for the shipped v2 cutover**.

Locked semantic behavior still applies:

- Individual agent ≠ broker company
- Factoring / QuickPay / AP / shipper / receiver / customs broker / insurer ≠ freight broker by default
- Prefer person-specific phone/email; do not substitute after-hours, corporate main, claims, AP
- Primary load reference = broker’s principal id for this shipment (whatever label the document uses)
- Rate = compensation to our carrier; distinguish linehaul/total from detention, TONU, late fees, QuickPay fees, lumpers
- Stop roles and appointment semantics belong to the model via `field_rules`, not to a competing server ranking engine

No hidden chain-of-thought is required. If richer provenance is added later, it should use explicit evidence fields/snippets rather than hidden reasoning.

---

## 8. Product mapping (existing hydration contract)

Keep New Load hydration on:

`LoadDocumentParseResponse` / `LoadParseExtractedFields`
(`broker_name_snapshot`, `broker_contact_*`, `broker_load_reference`, `rate`, `stops`, …)

The v2 production parser validates the OpenAI payload into the existing schema, then applies mechanical validation and tenant broker-name canonicalization for hydration.

Do not put new semantic business rules in the product adapter/validator.

---

## 9. Historical pre-v2 OpenAI handoff baseline

On 2026-08-13, a dump of the exact pre-cutover Chat Completions body for Armstrong (minus Authorization) was captured for review:

- Host path example: `/home/admin/openai_handed_armstrong.json`
- Endpoint: `POST https://api.openai.com/v1/chat/completions`
- Model: `gpt-4o-mini`, temperature `0.1`
- Messages contained:
  - extraction instructions
  - `PRODUCT_PARSE_DIAGNOSTICS` including **role_hint / broker_party**
  - extracted PDF text
- Schema: `load_document_parse_guarded_truckerjson_v1`
- **Not sent then:** `tenant_identity_exclusion`

That capture is now **historical baseline evidence**, not a description of the current v2 production handoff.

---

## 10. Explicit non-goals / guardrails

- Per-broker JSON packs or broker catalog as OpenAI input
- Browser IndexedDB as identity authority for parse
- Fuel / other document profiles inside this Load-specific contract
- Reintroducing a generic `pdf_pipeline` mega-framework merely for naming consistency
- Frontend broker dropdown / MC-DOT alias resolution as OpenAI input authority
- Expanding post-AI full-text regex semantic ranking as the brain
- Expanding the frozen tenant exclusion shape without evidence
- Calling OpenAI on OCR-required blank/garbage pages

---

## 11. Implementation record and remaining work

### Shipped / complete in the v2 cutover

1. **Slice 1 — tenant identity exclusion** from platform tenant + company profile
2. **Slice 1B — in-process TTL cache** with invalidation on profile write paths
3. **Slice 2 — frozen Rate Confirmation field rules + OpenAI handoff v2**
4. **Slice 3A — embedded-text page acquisition / OCR-required classifier**
5. **Mechanical post-model validation** with no semantic candidate ranking/repair
6. **Production cutover** of `POST /api/v1/loads/parse-document` to `load_document_parse_rate_con`
7. **Legacy semantic diagnostics/repair modules removed from the product Rate Confirmation runtime path**

### Remaining / separate slices

- OCR provider/orchestration for OCR-required pages
- Any richer explicit provenance/evidence-id schema, if later approved
- Broader shared profiles such as Fuel/Toll under the shared document parsing architecture
- Additional golden-fixture coverage where original PDFs are available

---

## 12. Historical relationship to Armstrong tactical fixes

Before v2, tactical Armstrong prompt/diagnostic repairs were used to stabilize the old guarded parser. They are retained only as historical reasoning for why server-side semantic guesses were risky.

The v2 product path deliberately replaces that boundary with field rules + tenant exclusion + page text → OpenAI → mechanical validation.

Do not resurrect the old candidate/diagnostics stack as a fallback for Rate Confirmation parsing.

---

## 13. Acceptance criteria — current v2

- [x] No broker-specific JSON files or hardcoded broker identities in parser code
- [x] Tenant exclusion built only from frozen platform tenant + company-profile fields (dynamic per request/cache)
- [x] Production handoff contains no `PRODUCT_PARSE_DIAGNOSTICS`, `broker_party`, `carrier_party`, or `role_hint`
- [x] OpenAI receives frozen `field_rules` + page-separated text + tenant exclusion
- [x] Product hydration remains `LoadDocumentParseResponse`
- [x] Server-side identity cache; invalidate on relevant profile writes; no IndexedDB authority
- [x] OCR-required PDFs are blocked from semantic parsing until OCR exists
- [x] Post-model validation is mechanical, not a second semantic parser
- [ ] OCR provider implemented
- [ ] Rich evidence-id/provenance result contract (future only if approved)
- [ ] All originally discussed seven fixture PDFs available and frozen as golden evidence

---

## Document control

| Field | Value |
|---|---|
| Owner | TruckERP load intake / parse |
| Location | `docs/TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md` |
| Supersedes | Ad-hoc chat conclusions and the pre-v2 diagnostics-as-input Rate Confirmation path |
| Current implementation | `5498e6c4` Rate Confirmation v2 cutover on inspection branch |
| Next doc update | OCR slice, explicit provenance schema change, or any approved change to the frozen tenant exclusion / field-rules contract |
