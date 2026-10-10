# Email Intake Filtering and Load Intake Safety

**Status:** **CURRENT SAFETY / OWNERSHIP LOCK — refreshed 2026-08-28.**  
**Scope:** Email ingestion, relevance routing, Load Intake review, and the boundary between email handling and the shared Document Parser.  
**Product rule:** Email Intake may collect, classify, parse selected documents for review, and create explicit review/draft workflows. It must not silently become Dispatch, Trip execution, custody, payroll, settlement, or accounting truth.

**Current parser architecture:** [`../TruckERP_Shared_Document_Parsing_Architecture.md`](../TruckERP_Shared_Document_Parsing_Architecture.md). There is **one shared Document Parser engine/pipeline with attached profiles**. Rate Confirmation v2 is the first shipped production profile. Email Intake is a caller of that parser; it does not own a second Rate Confirmation parser.

**Related current docs:**

- [`../CURRENT_PDF_LOAD_PATHS_AND_GAPS.md`](../CURRENT_PDF_LOAD_PATHS_AND_GAPS.md)
- [`../TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md`](../TruckERP_Load_Rate_Confirmation_Semantic_Parser_Design.md)
- [`../BROKER_EMAIL_INTAKE_QR_DESIGN.md`](../BROKER_EMAIL_INTAKE_QR_DESIGN.md)
- [`../GMAIL_AUTOMATIC_INGESTION.md`](../GMAIL_AUTOMATIC_INGESTION.md)

The older mixed current/target investigation report is preserved under `../archive/email/` for historical detail.

---

## 1. Ownership boundary

Email Intake owns:

- provider notification / sync orchestration
- message, thread, and attachment persistence
- provider-neutral normalization
- relevance / routing signals
- broker-intake resolution around the message context
- duplicate-content and QR checks where applicable
- review records and operator triage
- provenance linking message/thread/attachment → review → explicit Load action

The shared Document Parser owns:

- document acquisition
- the active document profile and field rules
- semantic interpretation
- schema-constrained output
- mechanical validation

For a Rate Confirmation PDF, Email Intake must call the same public product parser used by other product callers:

```text
app/services/load_document_product_parser.py
  → parse_pdf_bytes_to_load_document_response(...)
  → Rate Confirmation v2 profile
```

**Do not build an email-specific Rate Confirmation semantic parser.** Email-specific broker routing, QR extraction, duplicate detection, and review policy are surrounding intake behavior, not document-parser semantics.

---

## 2. Current implementation state

| Area | Current state on `main` |
|---|---|
| Gmail OAuth / delta ingestion | Implemented |
| Gmail PDF intake (`apply_email_pdf_intake`) | Implemented |
| Microsoft 365 / Graph ingestion | Implemented |
| IMAP / Other mailbox ingestion | Implemented; sync remains operator/cron driven where configured |
| Product Rate Confirmation parser from email PDF review | **Implemented through the shared public product parser / Rate Confirmation v2** |
| Automatic `Load` creation inside `apply_email_pdf_intake` | **No** |
| Explicit create-draft-from-review action | Exists as a separate operator/product action |
| Full A/B/C/D/E relevance classifier | **Not implemented** |
| OCR execution inside shared Document Parser | **Not implemented** |
| Async Load Page parse job | Design only |

### Gmail

Gmail post-ingestion routing may run `apply_email_pdf_intake`. Generic subject/snippet cues can route a thread to review. When PDF attachments are selected for semantic review, intake calls `load_document_product_parser.parse_pdf_bytes_to_load_document_response(...)` and stores the result as review evidence.

The review payload still uses historical field/key naming such as `guarded_parse` in places. That storage label is **not** proof that the old diagnostics/guarded semantic architecture is active; the public parser now routes to Rate Confirmation v2.

### Microsoft 365 and IMAP

Current non-Gmail mailbox intake is intentionally conservative: new active unlinked threads can be placed into review rather than using the full future relevance classifier. This keeps provider ingestion working without pretending that provider-neutral A/B/C/D/E filtering is already complete.

---

## 3. Load creation boundary

### Email ingestion / PDF intake must not silently create operational truth

`apply_email_pdf_intake` must not:

- create a final/committed Load merely because a PDF was attached
- create a Trip
- assign a driver, truck, or trailer
- set execution/custody state
- write payroll or settlement state
- create a driver dispatch package
- post AR/accounting truth

### Explicit operator actions are separate

A review may lead to an explicit action such as:

- create a draft Load
- link an existing Load
- open the canonical Load Page for verification
- dismiss / mark non-load
- re-run or inspect parsing

Those actions must remain auditable and must not be confused with passive email ingestion.

---

## 4. Canonical Load verification surface

`LoadWorkspaceForm` is the production load form.

Document-parser output is **candidate/hydration data**. Email review may store that candidate with provenance, but the production Load workflow owns human verification and normal Load persistence rules.

```text
email / attachment
  → intake relevance + review
  → shared Document Parser(profile=rate_confirmation) when selected
  → LoadDocumentParseResponse candidate
  → Load Intake review / Load Workspace hydration
  → human verify / edit / explicit save
```

Email Intake does not bypass the Load Page simply because semantic extraction returned schema-valid JSON.

---

## 5. Relevance filtering — current gap and target

The full provider-neutral classifier remains a **target**, not current code truth.

Target categories:

| Category | Meaning | Load-intake treatment |
|---|---|---|
| **A — new load likely** | Strong evidence of a new rate confirmation / tender | Primary Load Intake candidate; human verification |
| **B — load related** | Related to an existing load/trip, not a new load | Review / link candidate |
| **C — broker/company non-load** | Business email but not load workflow | Keep out of primary Load Intake |
| **D — unrelated** | Not a load/business intake item | Ignore for Load workflow |
| **E — needs review** | Ambiguous / low-confidence | Human review queue |

Only A, B, and E should normally occupy dispatcher-facing Load Intake/review surfaces once this classifier is implemented.

### Current limitation

Until the full classifier exists:

- Gmail uses lightweight broker-neutral cues plus PDF/broker review logic.
- Microsoft/IMAP remain more review-heavy.
- unrelated mail can still create review noise.

Do not describe current routing as if the A/B/C/D/E classifier already exists.

---

## 6. Broker and sender signals

Email Intake may use tenant/global broker identity and sender context for **routing and review** through the broker-intake resolver.

Rules:

- no hardcoded single-broker Gmail gate as the core architecture
- ambiguous/conflicting broker signals go to review
- header/domain/known-sender/MC-DOT signals may help intake routing
- these signals must not become a second semantic interpretation engine for the Rate Confirmation document itself

Inside the document, broker/carrier/reference/rate/stop meaning belongs to the active Document Parser profile.

---

## 7. QR and duplicate-content checks

QR extraction and PDF SHA-256 duplicate checks are intake/provenance features. They may help route, link, or warn, but they do not override parser semantics or automatically authorize a Load/Trip write.

A duplicate document may support reuse or review policy where explicitly designed; it must not silently merge unrelated operational records.

---

## 8. Safety rules for future work

Any future email-intake change must preserve these rules:

1. **One Document Parser, many profiles.** Email is a caller, not a parser fork.
2. **Relevance before broad parsing.** As the classifier improves, only relevant/ambiguous candidates should consume semantic parsing by default.
3. **No silent final Load creation.** Explicit product policy/operator action is required.
4. **No execution side effects.** Email/parser paths cannot assign, dispatch, start Trips, change custody, or trigger payroll/settlement.
5. **Provenance stays attached.** Review/draft suggestions should retain thread/message/attachment source identifiers where practical.
6. **Unknown/conflict → review.** Do not force ambiguous sender/broker/document evidence into an operational decision.
7. **Provider differences must not create different business semantics.** Gmail, Microsoft, and IMAP may differ in transport/sync mechanics; Load/Rate Confirmation semantics still belong to the same parser profile.

---

## 9. Current code anchors

- `app/services/email_engine/message_router.py`
- `app/services/email_engine/message_classifier.py`
- `app/services/email_engine/intake_service.py`
- `app/services/email_intake_review_service.py`
- `app/services/broker_intake_unified.py`
- `app/services/load_document_product_parser.py`
- `app/services/load_document_parse_rate_con.py`
- `apps/web/src/pages/LoadInboxPage.tsx`
- `apps/web/src/loadWorkspace/LoadWorkspaceForm.tsx`

When documentation conflicts with these boundaries, current code + Shared Document Parsing Architecture + the current parser/profile docs win.
