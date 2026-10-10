# Multi-document load candidate — design contract

**Status:** Design contract only. **No implementation** is required or implied by this document.

**Purpose:** Before building the real Load page and email intake, lock a **general** rule: one operational load (or pre-commit **load candidate**) may be supported by **many** source documents, each with its own parse output and **bounded** authority. This prevents a wrong architecture (e.g. “one PDF = one load forever,” or auto-merge on weak heuristics).

**Scope:** This contract applies to **all** brokers, carriers, and document flavors. Examples may name a specific broker (e.g. TQL) **only** as illustration — the rules are **not** TQL-specific.

**Out of scope (explicitly not specified here):** Merge engine implementation, candidate grouping tables, Load page UI, email intake matching logic, field provenance storage, conflict resolution UI, or any schema/migration. Those belong to a later phase.

**Related:** [`PDF_LOAD_PIPELINE.md`](./PDF_LOAD_PIPELINE.md) (target pipeline), [`CURRENT_PDF_LOAD_PATHS_AND_GAPS.md`](./CURRENT_PDF_LOAD_PATHS_AND_GAPS.md) (current paths).

---

## 1. Generalized multi-document rule

- A **load candidate** (or future committed **load**) may have **multiple** source documents over time.
- The system **must not** assume **one document = one load** or that the first document is the only source of truth for all fields.
- Each **physical or logical document** (each upload, attachment, or revision) keeps its own **`parse_response`** (or equivalent structured extraction result). The user-facing **load candidate** presents a **merged** view that is **derived** from these documents, not a single hidden overwrite of one parse by another without rules.

This applies to PDFs, images-after-OCR, and any other supported artifact that flows through the same canonical extraction contract.

---

## 2. Document identity / grouping rule

**Strong evidence — sufficient to group documents under the same load candidate (subject to product policy):**

- Same **booking broker** (or unambiguous resolved broker identity) **and** the same **broker load reference** / **PO#** / **order number** (or equivalent primary commercial reference) when those identifiers are clearly stated.
- Same **email thread** where the **load reference** (or explicit broker instruction) ties the attachment to the same move.
- **Exact** load / reference number match across **subject, body, and/or document text** when that match is unambiguous.
- **Dispatcher / operator** explicitly attaches a document to an **existing** load candidate or load (manual grouping always allowed).

**Weak signals — not sufficient for automatic merge:**

- Same pickup **city** only  
- Same delivery **city** only  
- Same **date** only  
- Same **carrier** only  
- Same **rate** only  
- Same **commodity** only  

Weak matches may still produce a **suggestion** (“possible same load — review required”) but **must not** silently collapse documents into one candidate without strong evidence or human confirmation.

**Hard rule on reference mismatch:** If two documents assert **different** primary load references (e.g. different PO# / order numbers) and strong identity alignment does not exist, **do not** merge automatically. Treat as separate candidates or as conflict/review.

---

## 3. Document classification

Before merge or field application, each document should receive a **coarse classification** (exact enum may evolve in implementation). Intended categories include:

| Classification | Notes |
|----------------|--------|
| `rate_confirmation` | Load tender / rate con / commercial offer |
| `driver_sheet` / `carrier_information_sheet` | Operations-focused carrier/driver package |
| `appointment_sheet` | Appointments, windows, contact at stop |
| `customs_document` | Customs / border-related |
| `bol` | Bill of lading |
| `pod` | Proof of delivery |
| `invoice` | Billing to carrier or shipper (context-dependent) |
| `receipt` | Lumper, accessorial, fuel, toll, etc. |
| `accessorial_support` | Supporting evidence for extra charges or terms |
| `unknown` | Unclassified; conservative handling |

Classification drives **field relevance** and **authority** (see §4), not a single global parser behavior.

---

## 4. Field authority / ownership

Different document types carry **different** authority. Defaults below are **normative for design**; implementation may add exceptions with explicit policy.

**Rate confirmation / load tender** typically **owns** (when present and trusted):

- Broker identity and commercial framing  
- **Broker load reference** / primary PO or order id  
- **Rate** / **carrier pay** and **currency**  
- **Equipment** and mode (where stated)  
- **Commercial terms** (detention, layover, TONU, accessorial *terms*, liability framework, etc.)

**Driver sheet / carrier information / appointment-style documents** typically **own** operational detail:

- **Full** pickup/delivery **facility names**  
- **Street address**, **city** / **state** / **postal** (or province)  
- **Appointment date** and **appointment time** (or windows)  
- Stop-level **reference numbers** (PO, stop id, BOL line, etc.)  
- **Stop contact** and **driver instructions**  
- **Customs broker** if listed in operations context  

**BOL, POD, invoice, receipt** and similar **must not** silently rewrite the **original commercial** truth from the rate con (e.g. headline rate, primary reference, equipment commitment) when they are **evidence** or **actuals** documents. They provide **proof**, **actuals**, **billing**, or **support**; merges should **enrich** or **annotate** with provenance, not hide conflicts.

---

## 5. Merge rules

When documents **belong** to the same load (per §2):

1. **Best source per field** — choose or combine using document type authority (§4), recency policy, and confidence (future implementation detail; not defined here).  
2. **No blind overwrite** — later document does not automatically clobber earlier fields without rules.  
3. **Provenance** — the merged view should be able to explain **which document** (or parse) last influenced each field in principle (“field source” is a product decision later; this contract only requires the *concept*).  
4. **Preserve each document’s `parse_response`** — underlying per-document structured output remains queryable and auditable.  
5. **Conflicts** — see §6.

**Examples (illustrative):**

- **Rate** and **currency** from **rate confirmation**; **full stop address** and **appointments** from **driver / carrier information** or **appointment sheet**.  
- **PO / load reference** may appear on **both**; agreement **reinforces**; disagreement triggers **conflict** (§6).  
- **Customs broker** may appear on **customs document** or **driver sheet**; authority follows §4 and explicit rules, not “last write wins” by default.

---

## 6. Conflict rule

If documents **disagree** on a field that is not an obvious **enrichment** of the same fact, **do not** silently pick a winner.

- Create a **`needs_review` / `conflict`** (or equivalent) record that operators can see and resolve.  
- **Enrichment** without conflict: e.g. rate con says “pickup: Charlotte, NC” and the driver sheet gives a **full street address in Charlotte** — **enrich** location, do not treat as conflict.  
- **True conflict** example: rate con says pickup **Charlotte, NC** and another authoritative operations document says pickup **Atlanta, GA** for the same stop role — **conflict / review**, not auto-merge.  
- **Different `broker_load_reference` / primary PO#** on two documents that were tentatively the same group → **do not** merge automatically; require human decision or new evidence.

---

## 7. TQL example (illustration only; not a special case)

**TQL** is used here **only** as a concrete pattern many operators recognize; **all rules above are broker-agnostic.**

Typical pattern:

- A **TQL rate confirmation (RC)** may arrive first with **cities**, **rate**, and a **PO#**, but not full street-level stop detail.  
- A **TQL Driver / Carrier Information Sheet** may arrive later with **full addresses**, **appointments**, and **refs**.

If **broker identity** and **PO# / primary reference** **match** per §2, the driver sheet **enriches** the existing candidate (addresses, times, stop contacts) under §4–§5.

If the **PO# differs** between two sample PDFs, they illustrate **different** loads — they **must not** be auto-merged as one candidate. (In a real case, two files may coincidentally be **samples** with mismatched references; that is a useful reminder that **strong identity** is required.)

This section does **not** add a “TQL mode” to the product; it is narrative **only**.

---

## 8. Scope boundary (this document)

**In scope:** Design principles and rules as above — to align architecture and avoid premature coupling of “one file / one load” or unsafe auto-merge.

**Explicitly out of scope for this contract (future work, not required here):**

- Merge engine  
- Load candidate grouping storage  
- Real Load page UI  
- Email intake **matching** implementation  
- Persistent field-level provenance schema  
- Conflict **UI** and resolution workflows  

Until those exist, this document remains the **reference** for **what** the system must respect, not **how** to code it.

---

*End of contract.*
