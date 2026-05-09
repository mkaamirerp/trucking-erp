# Email intake filtering and Load Intake safety

**Mode:** Architecture / product design report (documentation only).  
**As-of:** Aligned to **current `main`** (post neutral intake refactor; broker-specific Gmail gate removed from the PDF intake path).  
**Master index:** Listed under **Load, email intake** in [DOCUMENTATION_MASTER_INDEX.md](../DOCUMENTATION_MASTER_INDEX.md).  
**Related docs:** [GMAIL_AUTOMATIC_INGESTION.md](../GMAIL_AUTOMATIC_INGESTION.md), [BROKER_EMAIL_INTAKE_QR_DESIGN.md](../BROKER_EMAIL_INTAKE_QR_DESIGN.md), [TRIP_CONTAINER_LOAD_PAGE_PARSER_INTEGRATION_MAP.md](../TRIP_CONTAINER_LOAD_PAGE_PARSER_INTEGRATION_MAP.md), [CURRENT_PDF_LOAD_PATHS_AND_GAPS.md](../CURRENT_PDF_LOAD_PATHS_AND_GAPS.md). Cursor rule: `.cursor/rules/gmail-delta-ingestion-architecture.mdc`.

### Implementation status vs this document

| Topic | Status on `main` |
|-------|------------------|
| **Neutral Gmail PDF intake** (`apply_email_pdf_intake`), **review-only** non-Gmail mailboxes, broker-neutral **stage-1** text cues, **no `Load()` from `apply_email_pdf_intake`** (guardrail tests) | **Implemented** |
| **Full A/B/C/D/E classifier** (§2–3, §7) | **Target only — not implemented** |
| **Async Load Page parse jobs** | **Design only** — see [`load_parser/ASYNC_LOAD_PAGE_PARSE_JOB_DESIGN.md`](../load_parser/ASYNC_LOAD_PAGE_PARSE_JOB_DESIGN.md) |
| **One canonical extraction brain** across workspace, Lab, and email intake | **Not achieved** — see [CURRENT_PDF_LOAD_PATHS_AND_GAPS.md](../CURRENT_PDF_LOAD_PATHS_AND_GAPS.md) |

---

## 1. Current email intake behavior (code-verified)

### 1.1 Mailbox watching

| Capability | Status in repo |
|-----------|----------------|
| **Gmail OAuth** | Supported via tenant `TenantEmailAccount` with `provider == "gmail"`; tokens in encrypted fields. |
| **Gmail `users.watch` + Pub/Sub** | Supported: `gmail_users_watch` posts to Gmail API with `labelIds: ["INBOX"]` by default (`app/services/gmail_watch.py`). Push lands on `POST /api/v1/webhooks/gmail/pubsub` (`app/routers/gmail_pubsub.py`). |
| **Gmail History API** | Used for delta: `sync_gmail_delta_for_tenant` (`app/services/email_ingestion_gmail.py`) with `historyTypes=messageAdded`. |
| **IMAP (“Other” mail)** | Supported for primary `TenantEmailMailbox` with `mailbox_type == "other"`. Sync is **operator/cron driven** via `sync_other_imap_inbox_for_tenant` (`app/services/email_ingestion_imap.py`); `schedule_other_imap_sync_placeholder` is still a stub. |
| **Microsoft 365 / Graph** | Supported: OAuth + delta sync + webhook `POST /api/v1/webhooks/microsoft-graph` (`app/routers/microsoft_graph_webhook.py`, `app/services/microsoft_graph_sync.py`). Subscription requires `MICROSOFT_WEBHOOK_NOTIFICATION_URL`; renewal via admin/cron patterns in code. |

**Primary mailbox assumption:** Ingestion entrypoints consistently select **one** row per tenant per provider (`limit(1)` on `TenantEmailAccount` for Gmail/Microsoft; primary `TenantEmailMailbox` for IMAP). Product-wise this is **one primary connected inbox per provider class**, not arbitrary multi-mailbox fan-in.

### 1.2 Message fetching

**Gmail (after Pub/Sub or manual sync):**

1. History lists **affected thread IDs** (`messageAdded` only).
2. For **each** thread ID, the backend calls `users.threads.get` with **`format=full`** (`app/services/email_providers/gmail_adapter.py` → `email_ingestion_gmail._upsert_full_thread_from_gmail`).
3. That returns the **entire Gmail thread** (all messages in the thread), not only the newest message.
4. Bodies: `message_normalizer` walks MIME parts and extracts **plain text** where present; attachments are recorded with **metadata** (`attachmentId`, filename, mime, size) from the full payload (`attachment_parts_from_gmail_payload`). Binary attachment bytes are **not** inlined in the normalize step; persistence sets `download_status="metadata_only"` on new rows (`app/services/email_engine/persistence.py`).
5. **First-time cursor:** If `gmail_history_id` is unset, the first successful sync may **only** advance the cursor to the current profile `historyId` **without** importing backlog (`sync_gmail_delta_for_tenant` early return). After that, deltas pull new activity only.

**IMAP:**

1. Incremental **UID** fetch: new UIDs since `imap_last_seen_uid`, or on first run / UIDVALIDITY change a capped slice of **up to `max_messages` newest** messages from **all** mailbox UIDs (`imap_sync_incremental_sync` in `app/services/email_ingestion_imap.py`).
2. Each message is fetched as **RFC822** (full raw message) and normalized to one thread + one message (thread key from References / In-Reply-To / Message-ID).

**Microsoft 365:**

1. Graph **delta** pages; for each added/updated message, `graph_get_message` plus `graph_list_attachments` when `hasAttachments` (`app/services/microsoft_graph_sync.py`).
2. Normalized through `graph_api_message_to_normalized` (same shared ingestion engine as Gmail/IMAP after normalize).

### 1.3 Intake / review creation

| Question | Answer |
|----------|--------|
| Does every new email create a thread/message row? | **Yes** (for messages that survive normalize + upsert): persistence always upserts `EmailThread` + `EmailMessage` (+ attachment metadata rows). |
| Default `intake_bucket` on new threads? | **Server default `needs_review`** on `email_threads.intake_bucket` (`app/models/email_ingestion.py`). |
| Does every thread get a load intake / review item? | **No single rule** — behavior is **post-persistence routing** (`route_after_ingestion` → `run_post_ingest_intake`). Review rows (`EmailIntakeReview`) are created when `sync_email_intake_review_for_thread` runs and `intake_bucket == "needs_review"` with a parseable `routing_reason` path (see `app/services/email_intake_review_service.py`). |
| Only certain emails create “review” rows? | **`apply_email_pdf_intake`** (Gmail) **may** call `upsert_intake_review_from_intake_source` for broker/PDF outcomes (ambiguous broker, blocked, duplicate PDF hash, parse-review snapshot, low-confidence PDF, etc.). Other behavior depends on `routing_reason` and `sync_email_intake_review_for_thread` (`app/services/email_intake_review_service.py`). |
| Can non-load email appear in dispatcher-facing queues? | **Yes** — see §1.7. |
| Are review records separate from final loads? | **Yes.** `EmailThread.linked_load_id` is optional; `EmailIntakeReview` is a separate table keyed by thread. |

**Gmail-specific routing (`apply_email_pdf_intake`, `app/services/email_engine/intake_service.py`):**

Post-ingestion Gmail uses path `post_ingest_intake_path(provider) -> "email_pdf_intake"` → `run_post_ingest_intake` → **`apply_email_pdf_intake`** (see also thin alias `apply_intake_routing_for_email_thread` in `app/services/email_intake_routing.py`).

- **Stage 1 (broker-neutral, subject/snippet only):** `thread_indicates_load_intake_text_cues` / `subject_or_snippet_indicates_load_intake_text_cues` in `app/services/email_engine/message_classifier.py` — generic rate-con / BOL / MC·DOT **language** regex only; **no** broker registry, **no** hardcoded broker domains or brands in this module.
- **Load rows:** `apply_email_pdf_intake` is documented in code as **email PDF intake — no auto `Load`**. It **does not** instantiate `Load()`; guardrail coverage includes `tests/test_email_pdf_intake_no_auto_load.py`. Threads already in **`intake_bucket == "new_load"`** with a link are skipped early (legacy / manual state — verify product meaning before changing).
- **No PDF but stage-1 cues:** `needs_review` with `EMAIL_INTAKE_TOUCHPOINTS_NO_PDF_ATTACHMENT` (and QR tag supplement when applicable).
- **PDF attachments present:** after unified **`resolve_booking_broker_for_email_intake`** (and review exits on ambiguous/blocked/global conflicts), the service may call **`parse_pdf_bytes_to_load_document_response`** (`app/services/load_document_product_parser.py` → guarded implementation) on attachment bytes, persist a **truncated guarded-parse snapshot** into intake review (`EMAIL_INTAKE_PDF_PARSE_REVIEW_PRIMARY`), and set **`needs_review`**. Supplemental MC/DOT for resolver can use **`extract_pdf_text_bytes`** / **`extract_broker_mc_dot_hints`** from `app/services/email_intake_pdf.py` (text helpers only — not a second public parser).
- **QR:** `extract_qr_strings_from_pdf_bytes` / `record_intake_qr_extraction` still run on PDF bytes where applicable.
- **No PDF and no stage-1 cues:** unlinked active threads may move from **`needs_review` → `background`** with **`AUTO_NON_INTAKE_MAIL_BACKGROUND`**.

**Non-Gmail providers (`apply_review_only_mailbox_intake`):**

- For **Microsoft 365** and **IMAP (`other`)**, **every** newly ingested active unlinked thread is forced to **`needs_review`** with **`MAILBOX_INTAKE_REVIEW_ONLY`** (and the function explicitly **no-ops for Gmail**, which uses **`apply_email_pdf_intake`** instead).

**UI bands (`LoadInboxPage.tsx`):** operators see three bands — `new_load`, `needs_review`, and `background` (background rendered with the same row component as needs_review but separate list).

### 1.4 Attachment requirements

| Question | Answer |
|----------|--------|
| Is PDF required to **persist** email? | **No.** All inbound messages persist with or without attachments. |
| Does **`apply_email_pdf_intake` auto-create a `Load` from a PDF? | **No** on current `main` — intake uses **review + parse snapshot**, not automatic load creation (see tests under `tests/test_email_pdf_intake_no_auto_load.py`). |
| Can email without PDF enter review? | **Yes** — e.g. Gmail with stage-1 text cues but no PDF → `needs_review`; MS365/IMAP → `needs_review` for every new unlinked thread. |
| Is filename inspected? | **Yes** — PDF pick includes `filename.ilike("%.pdf")` (and `application/pdf`) via `_latest_pdf_attachment_rows`. |
| When is PDF **content** parsed? | **After post-persist intake starts**, inside **`apply_email_pdf_intake`** (manual upload / recompute call the same routing entrypoint — see `docs/CURRENT_PDF_LOAD_PATHS_AND_GAPS.md`). There is **no** separate “classify before persistence” stage matching §2 yet. |

### 1.5 Broker / domain / reference matching (current code)

The **booking broker resolver** used in the Gmail PDF intake path is `resolve_booking_broker_for_email_intake` (`app/services/broker_intake_unified.py`):

- **Tenant workspace:** known sender → domain → alias (`resolve_broker_for_intake_from_header`), with `intake_blocked` semantics on tenant `Broker`.
- **Global reference (read-only):** header-based match, then supplemental **MC/DOT** via `resolve_global_broker_by_mc_dot` when header alone is insufficient.
- **Conflicts:** ambiguous global header, blocked match, header vs MC/DOT disagreement, global tier-D review-only, intake signal conflict, global match without workspace materialization — all route to **`needs_review`** with structured reasons.

**Not observed as a pre-filter before ingestion:** there is **no** stage that drops or skips persistence based solely on broker directory match. Filtering is **post-persist bucket assignment**.

### 1.6 Broker-specific handling (current `main`)

| Broker / pattern | Behavior |
|-----------------|----------|
| **Hardcoded broker-only Gmail gate** (historical: TQL-only PDF keyword gate, `apply_gmail_tql_intake_gate`, `tql_digital_pdf_high_confidence`, etc.) | **Removed** from the active Gmail PDF intake path. `app/services/email_intake_pdf.py` now exposes **text extraction + MC/DOT hint helpers** only; intake PDF semantics go through **`parse_pdf_bytes_to_load_document_response`** and unified broker resolution. |
| **JB Hunt, RXO, Armstrong, Landstar, etc.** | **No** parallel hardcoded intake gates in `message_classifier` / `intake_service`. Matches, if any, flow through **tenant/global broker resolution** and operator actions (e.g. create draft from review). |
| **Legacy wire tokens** | Constants such as `LEGACY_EMAIL_INTAKE_AUTO_DIGITAL_PDF_RATE_CONFIRMATION` may remain in `app/constants/email_intake_routing.py` for historical routing strings — not a live auto-load path in **`apply_email_pdf_intake`**. |

### 1.7 Current risk (direct answer)

**Can unrelated or non-load emails enter dispatch / load intake review today?**

**Yes.**

1. **Microsoft 365 and IMAP:** **Every** ingested active unlinked thread is labeled **`needs_review`** (`apply_review_only_mailbox_intake`). There is **no** content-based classifier excluding newsletters, alerts, or personal mail before that queue.
2. **Gmail:** Threads with **no** stage-1 text cues and **no** PDF path may move to **`background`**, which is **still visible** in Load Inbox (third band). Threads with **stage-1 cues** and/or **PDFs** can land in **`needs_review`** with parse/broker review — **without** the full A/B/C/D/E model in §2.
3. **Generic cue false positives:** the stage-1 regex is **broker-neutral** but can still match **benign or unrelated** subject/snippet text that resembles rate-con / MC·DOT language, pulling threads into review or PDF parsing **before** a real classifier exists.

**What prevents wholesale spam:** operational reality depends on what arrives in the **connected INBOX** (Gmail watch is INBOX-labeled only) and tenant discipline; **code does not implement a general spam / non-load filter.**

**Other load-creation paths:** declaring “no automatic loads from email” requires checking **all** code paths — e.g. **operator-driven** `create_draft_load_from_review_thread`, **link load**, QR linkage helpers, and any **legacy** `new_load` bucket semantics — not **`apply_email_pdf_intake` alone**.

**Definitive implementation files:**

- `app/services/email_ingestion_gmail.py`, `app/services/email_ingestion_imap.py`, `app/services/microsoft_graph_sync.py` — fetch + persist.
- `app/services/email_engine/email_ingestion_engine.py`, `app/services/email_engine/persistence.py` — upsert.
- `app/services/email_engine/message_router.py`, `app/services/email_engine/message_classifier.py`, `app/services/email_engine/intake_service.py` — buckets + **`apply_email_pdf_intake`** / **`apply_review_only_mailbox_intake`**.
- `app/services/email_intake_review_service.py` — review row sync.
- `apps/web/src/pages/LoadInboxPage.tsx` — operator-visible queues.

---

## 2. Target behavior (product intent)

**Not implemented as a full classifier on `main` today** — §1 describes what actually runs; the following is **product intent** to converge toward.

Align runtime with the following intent (not yet fully implemented):

1. Provider notification means only **“new mail may exist.”**
2. Backend fetches **delta / new message metadata** and **minimal necessary body** for classification (full-thread replay may remain a Gmail implementation detail, but **classification should not assume every thread message needs operational treatment**).
3. Normalize and persist **archival** copies as needed for audit.
4. Run a **classifier before** (or immediately after normalize in a dedicated step) that assigns **operational relevance**, not just provider type.
5. Only **load-relevant** or **explicitly review-worthy** threads appear in primary dispatcher **load intake** surfaces. Everything else is archive / low-visibility / ignored for load workflow.

### Target categories (routing)

| ID | Category | Route (conceptual) |
|----|----------|--------------------|
| **A** | New load / rate confirmation likely | Load intake candidate; optional draft only under strict rules; **human verification before commitment.** |
| **B** | Load-related but not a new load | Load-related review; **link** to existing load/trip as candidate; **no** auto-new final load. |
| **C** | Broker/company but not load | **Do not** clutter primary load intake; archive only or separate business inbox. |
| **D** | Unrelated | Ignore for load workflow; **no** intake candidate. |
| **E** | Needs human review | Explicit **low-confidence** queue; audited triage. |

**Rule:** Only **A**, **B**, and **E** belong in dispatcher-facing **load intake / review**. **C** and **D** must not clutter those queues.

---

## 3. Filtering signals (target model)

The classifier should combine **positive**, **weak**, and **negative** signals. **Today**, only a **minimal broker-neutral stage-1** cue exists (`thread_indicates_load_intake_text_cues` — subject/snippet regex in `message_classifier.py`); broker matching is **`resolve_booking_broker_for_email_intake`**, not an A/B/C/D/E classifier. The table below is the **target** superset.

### 3.1 Strong positive (examples)

- Known broker sender / domain / tenant directory match / global reference / MC·DOT with corroborating load context.
- Rate-confirmation or load-tender **PDF** characteristics (layout/text patterns, not only filename).
- Subject/body strong load / ratecon language.
- Structured trip fields in body or PDF (pickup/delivery, reference numbers).

### 3.2 Medium positive (examples)

- Logistics-like domain without definitive directory match.
- PDF filename hints (`ratecon`, `confirmation`, `tender`, etc.) — **low trust alone**.
- Partial lane / equipment / rate cues without full confirmation.

### 3.3 Negative (examples)

- Invoice-only, remittance, newsletter markers, unsubscribe blocks, auth/security templates, obvious personal or banking templates.
- Attachments clearly unrelated (marketing, blank, wrong vertical) **after cheap inspection**.
- “Carrier packet” without load tie (unless product defines a separate workflow).

### 3.4 Broker-specific nuance (target)

- **TQL:** rate confirmation **and** separate driver-info PDFs should map to **B** when tied to an existing load signal, **A** only when a new load is well supported.
- **Multi-party MC/DOT:** never assume first MC/DOT block is broker; corroborate with header + directory + layout.

**Design principle:** broker-specific **templates** may exist as **hints**, but the **system must not depend** on a growing list of hardcoded broker-only branches for core safety.

---

## 4. Safety boundaries (non-negotiable)

### 4.1 Email intake / classifier must **not** (by default)

- Create **final / committed** loads without explicit human confirmation policy.
- Dispatch loads, create trips, assign drivers/trucks/trailers, or set operational statuses that imply execution (`dispatched`, custody, driver package send, payroll, settlement, AR posting).
- Treat parsed gross/rate as accounting truth without Load Page verification.

### 4.2 Email intake **may**

- Normalize and store message/thread/metadata.
- Classify and annotate signals + confidence.
- Create **intake candidates** and **draft** loads **only** when policy allows and **draft** is understood as non-final.
- Hydrate Load Page / review fields with **provenance** (message id, attachment id, parser version).
- Emit **audit events**.

### 4.3 Gap vs current code

**`apply_email_pdf_intake` (Gmail PDF intake)** on current `main` **does not** create a **`Load` row** or call `Load()` — it routes to **`needs_review`** / **`background`** and intake review with optional **guarded-parse snapshot**. That aligns with the **“no auto final load”** side of §4.1.

**Residual gaps vs target policy:**

- **Manual / other paths** can still create loads (e.g. **create draft from review** in `app/services/email_threads.py`). Audit those flows separately before claiming “no loads from email anywhere.”
- **Legacy bucket `new_load`** is still respected as a skip condition in `apply_email_pdf_intake`; confirm no other writer relies on it for unintended automation.
- The **full A/B/C/D/E classifier** (§2) and **negative-signal filtering** are still **not** implemented — review queues can remain noisy (§1.7).

---

## 5. Human review (target + current hooks)

### 5.1 Target dispatcher actions

- Ignore / mark not load.
- Mark broker-non-load (**C**).
- Link to existing load / trip candidate (**B**).
- Open **canonical Load Page** (**A**/confirm draft).
- Create draft from candidate under policy.
- Re-run parser; correct fields; confirm broker and document type.

### 5.2 Audit (target)

Each action should record: actor, original classification + confidence, signals snapshot, action, field corrections, load/trip links, ignore reason, source message/thread/attachment ids.

### 5.3 Current audit spine

`EmailIntakeReview` + append-only `EmailIntakeReviewEvent` (`app/services/email_intake_review_service.py`) already capture lifecycle events (`review_opened`, `claimed`, `resolved`, `dismissed`, duplicate flows, etc.). **Gap:** events today do **not** automatically store a full **signal vector** or classifier version; that would be part of the proposed classifier output (§7).

---

## 6. Relationship to Load Page / parser (boundary)

This mirrors [TRIP_CONTAINER_LOAD_PAGE_PARSER_INTEGRATION_MAP.md](../TRIP_CONTAINER_LOAD_PAGE_PARSER_INTEGRATION_MAP.md):

| Layer | Responsibility |
|-------|------------------|
| **Email intake** | Watch, fetch delta, normalize, **classify relevance**, create **candidates / review items**, provenance. |
| **Parser** | From **selected** attachments/body: structured extraction, TruckERP JSON shape, confidence/diagnostics — **hydration only**. |
| **Load Page (`LoadWorkspaceForm`)** | **Canonical** human verification and edit surface for load truth. |
| **Trip / dispatch** | Assignment, execution, custody, driver package, payroll — **downstream** of confirmed load/trip workflows. |

**Email intake + parser must not** create trips, dispatch, or trigger payroll/settlement.

### 6.1 B5-A semantic parser evidence vs email intake (gate required)

**B5-A** (`POST /api/v1/loads/parse-document` with the semantic adapter enabled) produced **parser-path** evidence only — e.g. improved stop structure and broker MC/DOT on **synthetic lab PDFs** under controlled conditions. That evidence is **not** permission for **email intake** to process **all** mail, run the parser on every attachment, or widen automatic intake.

**Email intake should implement a filter / classifier gate *before* parser use** (or equivalent strict selection). **Today**, PDF attachments on Gmail can still reach **`parse_pdf_bytes_to_load_document_response`** inside **`apply_email_pdf_intake`** after broker resolution, **without** the full §2 classifier — a **gap** vs this target. The parser — legacy or semantic — should eventually operate on **human- or policy-selected** candidates, not on the full firehose of normalized threads.

**Correct product flow (target):**

1. **Provider** notifies **new mail** (push / delta wake-up only).
2. **Backend** fetches **new/delta** message(s) and normalizes thread/message/attachment metadata.
3. **Classifier** decides whether the message is a **load / rate confirmation / intake candidate** (or low-confidence review — §2 category **E**).
4. Only **likely load/ratecon** messages or **explicit low-confidence review** candidates enter **load intake** (primary queues). Unrelated mail must not be parser-driven intake noise.
5. **Parser / semantic extraction** may run **only** on **selected** candidate attachments and/or body text (narrow scope, provenance preserved).
6. **Parser output** hydrates **Load Page** draft / **review** fields **only** — not operational truth by itself.
7. **Human** verifies, edits, **saves**, and marks **ready** on the canonical Load Page (or dismisses / ignores).
8. **No** parser or email path may **create trips**, **assign** equipment, write **`dispatch_trips`**, set **`Load.status = dispatched`**, or trigger **payroll**, **custody**, **driver package**, settlement, or other execution-side effects.

**B5-A caveat:** The run showed semantic can **improve stop extraction and broker MC/DOT** versus legacy regex on **synthetic** fixtures; it **does not** replace **real broker PDF** evaluation, production monitoring, or the **classifier gate** above. **Do not** use B5-A as sole justification for **broad email auto-processing** or for skipping **human verification** on the Load Page.

---

## 7. Proposed classifier / routing output (target JSON)

Single envelope the router can persist (e.g. JSON column or sidecar table) and pass to UI + audit:

```json
{
  "classification": "new_load_likely | load_related | broker_non_load | unrelated | needs_review",
  "confidence": "high | medium | low",
  "route": "load_intake | load_related_review | ignore_for_load_workflow | human_review",
  "signals_positive": [],
  "signals_negative": [],
  "broker_match": {
    "source": "tenant_directory | tenant_domain | tenant_known_sender | global_reference | none",
    "broker_id": null,
    "global_broker_id": null,
    "confidence": "high | medium | low"
  },
  "attachment_assessment": {
    "has_pdf": true,
    "likely_rate_confirmation": true,
    "likely_driver_info_sheet": false,
    "likely_invoice": false
  },
  "safety": {
    "may_create_intake_candidate": true,
    "may_create_draft_load": false,
    "may_create_final_load": false,
    "may_dispatch": false,
    "may_create_trip": false
  }
}
```

**Mapping to §2 categories:**

- **A** → `classification=new_load_likely`, `route=load_intake` (primary queue).
- **B** → `classification=load_related`, `route=load_related_review`.
- **C** → `classification=broker_non_load`, `route=ignore_for_load_workflow` (archive optional).
- **D** → `classification=unrelated`, `route=ignore_for_load_workflow`.
- **E** → `classification=needs_review`, `route=human_review` with mandatory `confidence=low|medium`.

---

## 8. Implementation notes (non-binding)

- **Provider parity:** Today Gmail uses **`apply_email_pdf_intake`**; MS365/IMAP use **`apply_review_only_mailbox_intake`**. Any future **A/B/C/D/E** classifier should run **after** normalize for **all** providers to avoid drift.
- **Performance:** Full-thread Gmail fetches are expensive; classification could eventually operate on **latest message + attachment manifest** until a human opens the thread.
- **Regression anchors:** When implementing, preserve `docs/GMAIL_AUTOMATIC_INGESTION.md` proof checklist and QR lineage rules in `docs/BROKER_EMAIL_INTAKE_QR_DESIGN.md`.

---

*End of report.*
