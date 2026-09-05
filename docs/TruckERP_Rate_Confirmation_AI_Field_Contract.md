# TruckERP Rate Confirmation — AI field contract

**STATUS: DESIGN COMPLETE — IMPLEMENTATION NOT YET APPROVED**

The design is frozen for implementation review. It is **not** wired into OpenAI, production `field_rules`, parse schema, or parser code.

Do **not** modify production code until explicit implementation authorization.

This file is the **canonical** design. It is not production `field_rules`, not the parse response schema, and not parser code.

Empty `profile_exclusion.values` arrays are the **shape**. TruckERP fills them at runtime from the tenant profile. Do not hardcode a broker or tenant in production logic. Real PDFs (Armstrong, TQL, JB Hunt, Hub Group, RXO, BM2, Landstar) appear **only as explanatory examples**.

---

## Architecture

### A. Runtime / dynamic tenant identity exclusion

- TruckERP resolves the current tenant’s identity **before** OpenAI.
- OpenAI receives the fully materialized exclusion object.
- The AI does not query the database or construct tenant identity itself.
- Backend name: **`tenant_identity_exclusion`**.
- Design name: **`profile_exclusion`**.
- These are the **same runtime object**. Do not create a duplicate exclusion payload.

### B. Static generic field semantics

- The same field rules apply to every tenant and every broker.
- No Armstrong / JB Hunt / TQL / Hub / RXO hardcoding in production logic.
- Broker-specific PDFs may remain only as examples in this design document.

---

## Field implementation status

Labels used below:

- **CURRENT PRODUCT/PARSE FIELD** — present on `LoadParseExtractedFields` / `ParseDocumentSemanticModelOutput`.
- **CURRENT PRODUCT/LOAD FIELD** — present on the Load form / `Load` schema; may or may not be on the parse schema.
- **AUXILIARY CURRENT FIELD** — on the parse contract for compatibility, not a primary extraction target.
- **PROPOSED / NOT CURRENTLY IMPLEMENTED** — approved design only; not a production requirement until explicitly implemented.

| Logical group | Product / parse field | Status |
|---|---|---|
| profile_exclusion | `tenant_identity_exclusion` (handoff) | CURRENT runtime object |
| broker company | `broker_name_snapshot` | CURRENT PRODUCT/PARSE FIELD |
| broker company phone | `broker_phone_snapshot` | **APPROVED PROPOSED FIELD** (not on parse/Load schema; first parser cutover is not blocked if schema/UI is deferred) |
| broker authority | `broker_mc_number_snapshot`, `broker_dot_number_snapshot` | CURRENT PRODUCT/PARSE FIELD |
| broker agent name | `broker_contact_name_snapshot` | CURRENT PRODUCT/PARSE FIELD |
| broker agent phone | `broker_contact_phone_snapshot` | CURRENT PRODUCT/PARSE FIELD |
| broker agent extension | `broker_contact_extension_snapshot` | **APPROVED** parse field; CURRENT on Load; **not** on parse schema yet (cutover not blocked) |
| broker agent email | `broker_contact_email_snapshot` | CURRENT PRODUCT/PARSE FIELD |
| broker agent cohesion | name + phone + extension + email as one person | CURRENT design for LOAD; parse schema has no extension yet |
| broker load reference | `broker_load_reference` | CURRENT PRODUCT/PARSE FIELD — PO # is **not** automatically primary |
| TruckERP internal load number | `load_number` (e.g. `INT-…`) | CURRENT PRODUCT/LOAD FIELD — **not** an AI extraction target |
| freight mode | `mode` | CURRENT PRODUCT/PARSE FIELD (no dedicated production `field_rules` group) |
| equipment type | `equipment_type` | CURRENT PRODUCT/PARSE FIELD (no dedicated production `field_rules` group) |
| trailer type | `trailer_type` | CURRENT PRODUCT/PARSE FIELD (no dedicated production `field_rules` group) |
| trailer size | `trailer_size` | CURRENT PRODUCT/PARSE FIELD (no dedicated production `field_rules` group) |
| commodity | `commodity` (scalar; multiple values joined with `"; "`) | CURRENT PRODUCT/PARSE FIELD (no dedicated production `field_rules` group) |
| estimated weight | `estimated_weight` | CURRENT PRODUCT/PARSE FIELD (no dedicated production `field_rules` group) |
| temperature | `temperature_requirement` | CURRENT PRODUCT/PARSE FIELD (no dedicated production `field_rules` group) |
| hazmat | parse: **APPROVED** three-state; Load: `hazmat_flag` | CURRENT PRODUCT/**LOAD** FIELD; **not** on parse schema yet; Load default `false` is an implementation gap |
| rate | `rate` | CURRENT PRODUCT/PARSE FIELD — **DESIGN-vs-PRODUCTION CONFLICT** (see below) |
| customer rate | `customer_rate` | AUXILIARY CURRENT FIELD — default null |
| miles | `miles` | CURRENT PRODUCT/PARSE FIELD (no dedicated production `field_rules` group; parse is float, Load is int) |
| stops | `stops[]` | CURRENT PRODUCT/PARSE FIELD |
| stop generic reference | `stops[].reference_number` | CURRENT PRODUCT/PARSE FIELD — kept for compatibility on first cutover |
| typed references | `references[]` `{kind, value, label}` | **RESOLVED Option B**; CURRENT on parse; Load persistence of the full collection is outside this parser decision |
| typed per-stop `stops[].references[]` | long-term collection per physical stop | **APPROVED long-term**; not required to block first parser cutover |
| secondary references persistence | Load table for all secondary refs | **OUTSIDE** current parser implementation decision |
| customs broker | `customs_broker_name` | AUXILIARY CURRENT FIELD — never freight-broker identity |
| document type | `document_type` | AUXILIARY CURRENT FIELD (parse root) |
| classification reasoning | `classification_reasoning` | AUXILIARY CURRENT FIELD (parse root) |
| warnings | `warnings` | CURRENT PRODUCT/PARSE FIELD (parse root) |
| field confidence | `field_confidence` | CURRENT PRODUCT/PARSE FIELD (parse root) |

---

## CURRENT PRODUCT GAP — typed stop references — **RESOLVED: Option B**

Choose **Option B**, not dedicated fixed columns.

`references[]` is a typed collection of semantic items, for example:

```json
{
  "kind": "pickup_number",
  "value": "NM031640",
  "label": "Pick/Drop #"
}
```

**Long-term design:** each physical stop may have its own `references[]` collection. Broker reference taxonomies are open-ended and broker-specific, so dedicated fixed columns (Pickup #, Delivery #, Appointment #, PO #, …) are not scalable.

**Compatibility for first parser cutover:** current `stops[].reference_number` remains supported. The richer per-stop `stops[].references[]` collection is **not** required to block the first parser cutover.

Permanent persistence of all secondary references on the Load is **outside** the current parser implementation decision. Do not remove parse `references[]` merely because Load persistence is not finalized.

UI headings such as PICKUP 1 / DELIVERY 1 / custom dispatcher role are **outside** this JSON. Do not add presentation headings to the AI contract.

---

## Internal load number (not AI)

Do not confuse TruckERP internal `load_number` with `broker_load_reference`.

| Source | Example | Destination |
|---|---|---|
| TruckERP internal | `INT-2A023C5255CE` | `load_number` — generated/owned by TruckERP |
| Broker PDF Load # | `3872125-1` | `broker_load_reference` — extracted by AI |

AI extracts the broker Load # into `broker_load_reference`. AI does not overwrite or generate the TruckERP internal `load_number`.

---

## Customer rate (auxiliary)

Do **not** make `customer_rate` a major AI extraction target.

Carrier rate confirmations normally disclose carrier freight pay, not broker-customer pricing.

If retaining the existing schema field for compatibility:

- default **null**
- never copy carrier `rate` into `customer_rate`
- populate only if a separate customer-facing rate is explicitly and unambiguously shown

---

## Miles (informational)

Miles are informational/reference only.

- Extract broker-provided mileage when explicitly supplied.
- Do not calculate mileage from addresses.
- Do not derive mileage from rate-per-mile.
- Do not use mileage to determine driver pay.
- Driver/company pay calculations are separate business logic **outside** this AI parse contract.
- Reject incidental mileage instructions such as “drive 250 miles after pickup.”

---

## Rate — final approved meaning

**PRIMARY AGREED FREIGHT / LINEHAUL RATE PAID BY BROKER TO CARRIER.**

Normally one load-level amount.

Do **not** include lumper, detention, layover, TONU, loading/unloading reimbursement, extra-stop payment, advances, QuickPay/factoring/payment fees, penalties, fines, late charges, tracking fines, paperwork deductions, future rate reductions, claims, or other conditional compensation.

Do **not** calculate final/net settlement.

Hub Group test:

| Label | Amount |
|---|---|
| Carrier Freight Pay | 1600.00 |
| Labor/Lumper | 83.02 |
| Total Carrier Pay | 1683.02 |
| **Approved `rate`** | **1600.00** |

**DESIGN-vs-PRODUCTION CONFLICT:** existing production `field_rules.rate_broker_pay` prefers total compensation / Total Carrier Pay. Do **not** change production code from this document.

---

Illustrative mapping (not runtime/handoff values):

```json
{
  "broker_name_snapshot": "Armstrong Transport Group",
  "broker_phone_snapshot": "877-240-1181",
  "broker_contact_name_snapshot": "Loflin Phillips",
  "broker_contact_phone_snapshot": "208-751-8073",
  "broker_contact_extension_snapshot": null,
  "broker_contact_email_snapshot": "l.phillip@armstrongtransport.com",
  "broker_load_reference": "3872125-1"
}
```

Canonical field JSON follows. `profile_exclusion` is the design name for runtime `tenant_identity_exclusion`.

```json
{
  "broker_name_snapshot": "Armstrong Transport Group",
  "broker_phone_snapshot": "877-240-1181",
  "broker_contact_name_snapshot": "Loflin Phillips",
  "broker_contact_phone_snapshot": "208-751-8073",
  "broker_contact_extension_snapshot": null,
  "broker_contact_email_snapshot": "l.phillip@armstrongtransport.com",
  "broker_load_reference": "3872125-1"
}
```

```json
{
  "profile_exclusion": {
    "purpose": "Identify our own tenant/carrier so OpenAI must not use our company identity in broker or other third-party fields.",

    "source": "TruckERP runtime tenant profile",

    "runtime": true,

    "backend_runtime_name": "tenant_identity_exclusion",

    "mapping": "Design concept profile_exclusion is the same runtime object as tenant_identity_exclusion. TruckERP materializes it before OpenAI. Do not create a duplicate exclusion object.",

    "values": {
      "names": [],
      "mc_numbers": [],
      "usdot_numbers": [],
      "phones": [],
      "emails": [],
      "email_domains": [],
      "addresses": []
    },

    "rules": [
      "These values identify OUR carrier/tenant.",
      "Treat matching values found in the PDF as tenant/carrier evidence.",
      "Never use a matching tenant company name as the freight broker.",
      "Never use tenant MC or USDOT numbers as broker authority.",
      "Never use tenant phone numbers as broker phone numbers.",
      "Never use tenant email addresses as broker or broker-contact email addresses.",
      "Never use a tenant-owned email domain as evidence that a person belongs to the broker.",
      "Do not transfer tenant information into another entity merely because it appears near that entity in the PDF.",
      "The profile exclusion values are already resolved by TruckERP before this JSON is sent to OpenAI."
    ]
  },

  "fields": {
    "broker": {
      "product_field": "broker_name_snapshot",

      "product_fields": [
        "broker_name_snapshot",
        "broker_phone_snapshot"
      ],

      "entity": "freight_broker_company",

      "goal": "Identify the freight broker/company that tendered, arranged, issued, or is responsible for paying our carrier for this specific load.",

      "before_populating_field": [
        {
          "step": 1,
          "action": "exclude_tenant",
          "rule": "Compare company candidates against profile_exclusion. Any company identified as our tenant/carrier must not be selected as the broker."
        },
        {
          "step": 2,
          "action": "find_company_candidates",
          "rule": "Identify the companies appearing in the document before selecting a broker."
        },
        {
          "step": 3,
          "action": "classify_company_roles",
          "rule": "Determine the business role of each company candidate, such as broker, carrier, shipper, receiver, consignee, customs broker, factoring company, payment provider, insurer, or stop facility."
        },
        {
          "step": 4,
          "action": "find_broker_evidence",
          "rule": "Determine which company actually tendered, arranged, issued, or is paying the carrier for this load."
        },
        {
          "step": 5,
          "action": "cross_check_broker_identity",
          "rule": "Cross-check the candidate using company name, document header or logo, corporate-information block, MC/USDOT ownership, company email domain, company phone, rate-confirmation context, payment responsibility, and broker-agent information."
        },
        {
          "step": 6,
          "action": "reject_non_broker_entities",
          "rule": "Reject the carrier/tenant, shipper, receiver, consignee, customs broker, factoring company, payment provider, insurer, and stop facilities as the freight broker."
        },
        {
          "step": 7,
          "action": "resolve_conflicting_candidates",
          "rule": "If multiple companies could appear to be the broker, use transaction-level evidence and entity ownership. Do not choose based only on proximity, page position, font size, or number of mentions."
        },
        {
          "step": 8,
          "action": "validate_identity_consistency",
          "rule": "Before populating broker_name_snapshot, verify that broker authority, broker-domain contact evidence, and other broker-specific evidence can consistently belong to the selected company."
        }
      ],

      "strong_positive_evidence": [
        "The company issued the rate confirmation.",
        "The company appears in the rate-confirmation header or corporate-information section.",
        "The document identifies the company as arranging or tendering the shipment.",
        "The company is responsible for the carrier rate or payment.",
        "MC or USDOT authority is explicitly associated with the company.",
        "Broker contact email uses the company's business email domain.",
        "A named load agent/contact is explicitly associated with the company."
      ],

      "not_sufficient_by_itself": [
        "The company appears first in the document.",
        "The company name uses large or prominent text.",
        "The company is mentioned multiple times.",
        "An address appears near the company.",
        "A phone number appears near the company.",
        "The word broker appears nearby."
      ],

      "must_not_select": [
        "tenant/carrier",
        "driver",
        "shipper",
        "receiver",
        "consignee",
        "customs broker",
        "factoring company",
        "QuickPay or payment provider",
        "insurance company",
        "stop facility"
      ],

      "company_phone": {
        "product_field": "broker_phone_snapshot",
        "implementation_status": "APPROVED PROPOSED FIELD. Separate from broker_contact_phone_snapshot. Example: Armstrong company 877-240-1181 vs Loflin Phillips direct agent phone. Schema/UI may be deferred; first parser cutover is not blocked.",
        "entity": "freight_broker_company",
        "meaning": "The main/corporate/company phone belonging to the selected freight broker company itself, not to an individual load agent.",
        "rules": [
          "Populate broker_phone_snapshot only after the broker company is identified.",
          "The number must belong to the selected broker company, not the tenant/carrier, shipper, receiver, driver, or a stop.",
          "Reject any phone matching profile_exclusion.",
          "A number in the broker corporate-information, header, or company-contact block is strong company-phone evidence.",
          "A main-office or toll-free company line without a person association belongs in broker_phone_snapshot.",
          "Do not copy broker_phone_snapshot into broker_contact_phone_snapshot.",
          "Do not use a person-specific agent phone as broker_phone_snapshot when a distinct company line is supported.",
          "Do not use an extension as evidence for broker_phone_snapshot. Extension evidence belongs to the individual agent contact.",
          "If no supported company-level broker phone exists, return broker_phone_snapshot as null."
        ]
      },

      "output": {
        "if_supported": "Return the broker company name supported by the document.",
        "company_phone_if_supported": "Return broker_phone_snapshot for a main/corporate/company phone belonging to the selected broker.",
        "if_ambiguous": null,
        "if_not_found": null,
        "company_phone_if_not_found": null,
        "never_copy_company_phone_into_contact_phone": true,
        "never_invent": true
      }
    },

    "broker_authority": {
      "product_fields": [
        "broker_mc_number_snapshot",
        "broker_dot_number_snapshot"
      ],

      "implementation_status": "CURRENT PRODUCT/PARSE FIELD",

      "entity": "freight_broker_company_authority",

      "depends_on": [
        "broker",
        "profile_exclusion"
      ],

      "goal": "Identify the MC and/or USDOT authority numbers that belong to the selected freight broker company for this load.",

      "before_populating": [
        {
          "step": 1,
          "action": "confirm_broker",
          "rule": "Use the freight broker already identified in broker_name_snapshot."
        },
        {
          "step": 2,
          "action": "exclude_tenant_authority",
          "rule": "Reject any MC or USDOT matching profile_exclusion / tenant_identity_exclusion."
        },
        {
          "step": 3,
          "action": "find_authority_candidates",
          "rule": "Find MC, Motor Carrier, USDOT, US DOT, and DOT numbers in the document."
        },
        {
          "step": 4,
          "action": "classify_ownership",
          "rule": "Determine which company each authority number belongs to: selected broker, carrier/tenant, shipper, or another party."
        },
        {
          "step": 5,
          "action": "prefer_broker_corporate_block",
          "rule": "Prefer authority shown in the broker company or corporate-information block, or otherwise clearly tied to the selected broker company."
        },
        {
          "step": 6,
          "action": "reject_proximity_to_person",
          "rule": "Do not assign carrier/tenant MC/DOT to the broker merely because it appears near a broker agent heading such as FOR LOAD INFORMATION."
        }
      ],

      "rules": [
        "Authority numbers must belong to the selected broker company, not merely be nearby numbers.",
        "Never return the carrier/tenant MC/DOT as broker authority.",
        "If broker and carrier authorities both appear, associate each with its actual company.",
        "If broker MC is supported but broker USDOT is absent, return MC and leave DOT null.",
        "Normalize supported MC/USDOT values to identifying digits.",
        "If ownership is ambiguous, return null rather than selecting another party's number."
      ],

      "output": {
        "if_mc_supported": "Return broker_mc_number_snapshot.",
        "if_dot_supported": "Return broker_dot_number_snapshot.",
        "if_only_one_supported": "Return the supported number and leave the other null.",
        "if_ambiguous": null,
        "never_invent": true
      }
    },

    "broker_agent_contact": {
      "product_fields": [
        "broker_contact_name_snapshot",
        "broker_contact_phone_snapshot",
        "broker_contact_extension_snapshot",
        "broker_contact_email_snapshot"
      ],

      "entity": "broker_agent_person",

      "depends_on": [
        "broker",
        "broker_phone",
        "profile_exclusion"
      ],

      "goal": "Identify the individual agent/contact handling this specific load for the selected broker, then return only the phone, extension, and email that belong to that same individual.",

      "broker_agent_name": {
        "product_field": "broker_contact_name_snapshot",

        "entity": "broker_agent_person",

        "depends_on": [
          "broker",
          "profile_exclusion"
        ],

        "goal": "Identify the individual agent, dispatcher, representative, or load contact working for the selected broker on this specific load.",

        "before_populating": [
          {
            "step": 1,
            "action": "confirm_broker",
            "rule": "Use the broker company already identified in the Broker field."
          },
          {
            "step": 2,
            "action": "find_named_people",
            "rule": "Find all person names appearing in the document before selecting a broker agent."
          },
          {
            "step": 3,
            "action": "exclude_tenant_people",
            "rule": "Reject people clearly belonging to profile_exclusion or our tenant/carrier."
          },
          {
            "step": 4,
            "action": "classify_person_roles",
            "rule": "Determine whether each person is a broker agent, carrier employee, driver, shipper contact, receiver contact, consignee contact, warehouse contact, customs contact, accounting/payment contact, claims contact, tracking contact, or another role."
          },
          {
            "step": 5,
            "action": "find_load_specific_agent",
            "rule": "Prefer the person explicitly identified as handling, tendering, dispatching, signing, or providing information about this specific load for the selected broker."
          },
          {
            "step": 6,
            "action": "verify_broker_relationship",
            "rule": "Confirm that the person belongs to or represents the selected broker using broker context, company email domain, agent block, signature block, or explicit load-contact wording."
          },
          {
            "step": 7,
            "action": "apply_contact_locality",
            "rule": "Name, phone, extension, and email should normally appear in the same local contact block, same logical section, or tightly related nearby lines."
          },
          {
            "step": 8,
            "action": "reject_stop_contacts",
            "rule": "Do not select people appearing only inside shipper, receiver, pickup, delivery, consignee, warehouse, or stop sections."
          },
          {
            "step": 9,
            "action": "final_check",
            "rule": "Populate broker_contact_name_snapshot only when the person is supported as the broker-side agent/contact for this specific load."
          }
        ],

        "strong_evidence": [
          "FOR LOAD INFORMATION followed by a person's name",
          "Agent Name",
          "Broker Agent",
          "Broker Contact",
          "Load Contact",
          "Dispatcher",
          "Representative",
          "Please Sign and Email to <person>",
          "For specific information about this load, contact <person>",
          "Broker signature block naming the person",
          "Person-specific email using the selected broker's company domain",
          "Name, phone, extension, and email appearing together in one broker-contact block"
        ],

        "broker_email_domain_match": {
          "rule": "If a named person's email domain clearly belongs to the selected broker company, treat that as strong evidence that the person represents the broker.",
          "strength": "STRONG",

          "requirements": [
            "The broker company must already be identified.",
            "The email must be explicitly tied to the named person.",
            "The email domain must reasonably correspond to the selected broker company.",
            "The email must not match profile_exclusion.",
            "The person's role must still be relevant to this load."
          ],

          "important_limit": "A broker-domain email alone does not make someone the load agent if the document clearly identifies that person as accounting, claims, tracking, payment, or another unrelated role."
        },

        "broker_agent_contact_cohesion": {
          "fields": [
            "broker_contact_name_snapshot",
            "broker_contact_phone_snapshot",
            "broker_contact_extension_snapshot",
            "broker_contact_email_snapshot"
          ],

          "rule": "These values describe one broker-agent contact and should normally come from the same local contact block, same logical section, or tightly related nearby lines.",

          "strong_patterns": [
            "Person name near phone",
            "Person name near extension",
            "Person name near email",
            "Phone and extension together",
            "Email and name together",
            "Name, phone, extension, and email inside the same broker-agent/contact section"
          ],

          "page_boundary_rule": "Do not assemble one broker-agent contact from unrelated evidence across distant pages.",

          "must_not_do": [
            "Do not take the agent name from page 1 and an unrelated phone from page 3.",
            "Do not take the agent name from one section and email from another person's section.",
            "Do not take an extension from another department or contact.",
            "Do not fill a missing agent field merely because a compatible-looking value appears somewhere else in the PDF.",
            "Do not use physical proximity alone when the surrounding section belongs to another entity."
          ],

          "allowed_cross_page_exceptions": [
            "The same person's name is explicitly repeated on the later page with the phone, extension, or email.",
            "The later page explicitly says contact <same person> at <phone/email>.",
            "The later page is clearly a continuation of the same broker-agent/contact block."
          ],

          "null_policy": "If a missing phone, extension, or email cannot be tied back to the selected person's contact block or explicit cross-reference, leave that detail null."
        },

        "extension_signal": {
          "rule": "An extension is strong evidence of an individual broker agent when it appears with the selected person's phone in the same broker-agent contact context.",
          "strength": "VERY_STRONG",

          "requirements": [
            "The surrounding section must belong to the selected broker.",
            "The extension must be tied to the selected person or their phone line.",
            "Do not use extensions from shipper, receiver, warehouse, accounting, carrier, or unrelated sections."
          ],

          "important_limit": "An extension strengthens an already-valid broker-agent association; it does not establish broker ownership by itself."
        },

        "important_rules": [
          "Do not choose a person merely because their name is near a phone number, email address, MC number, DOT number, or company name.",
          "First establish the person's business role.",
          "Broker company identity and broker-agent identity are separate decisions.",
          "The selected person's email domain matching the selected broker is strong supporting evidence.",
          "The selected agent's name, phone, extension, and email should remain locally coherent."
        ],

        "must_not_select": [
          "tenant/carrier employee",
          "driver",
          "shipper contact",
          "receiver contact",
          "consignee contact",
          "warehouse contact",
          "customs broker employee",
          "factoring contact",
          "accounts payable contact",
          "claims contact",
          "tracking-only contact"
        ],

        "output": {
          "if_supported": "Return the broker agent's name as shown in the document.",
          "if_ambiguous": null,
          "if_not_found": null,
          "never_invent": true
        }
      },

      "contact_phone_logic": {
        "precheck": [
          "Reject any phone matching profile_exclusion.",
          "Classify the section/entity owning every phone before considering it."
        ],

        "strong_evidence": [
          "Selected agent name and phone appear in the same contact block.",
          "Selected agent name and phone appear on the same logical line group.",
          "Document explicitly says to contact the selected agent at that phone.",
          "FOR LOAD INFORMATION identifies the selected agent and phone.",
          "Agent block identifies the selected agent and phone.",
          "The same person-phone association is repeated in the document."
        ],

        "broker_company_phone_rule": "The broker company's main/corporate phone is valid broker-company information but must remain broker_phone_snapshot. Do not copy it into broker_contact_phone_snapshot unless the document explicitly identifies that same number as the selected agent's direct contact number.",

        "output_rule": "If the agent is known but no phone is directly associated with that agent, return broker_contact_phone_snapshot as null."
      },

      "contact_extension_logic": {
        "product_field": "broker_contact_extension_snapshot",
        "implementation_status": "APPROVED parse field. Already on Load. Parse-schema implementation later; first cutover is not blocked.",
        "rule": "Populate broker_contact_extension_snapshot only when an extension is explicitly tied to the selected broker agent and the selected agent phone.",

        "requirements": [
          "The extension must belong to the same person as broker_contact_name_snapshot.",
          "The extension must belong to broker_contact_phone_snapshot or clearly identify that person's line.",
          "Do not attach an unrelated extension from another section or person.",
          "Do not infer an extension."
        ],

        "if_missing": null
      },

      "broker_agent_email": {
        "product_field": "broker_contact_email_snapshot",

        "entity": "broker_agent_person",

        "depends_on": [
          "broker",
          "broker_agent_name",
          "profile_exclusion"
        ],

        "goal": "Identify the email address belonging specifically to the selected broker agent handling this load.",

        "before_populating": [
          {
            "step": 1,
            "action": "confirm_agent",
            "rule": "Use the broker agent already identified in broker_contact_name_snapshot."
          },
          {
            "step": 2,
            "action": "exclude_tenant_email",
            "rule": "Reject any email matching profile_exclusion. It belongs to our tenant/carrier."
          },
          {
            "step": 3,
            "action": "find_email_candidates",
            "rule": "Find all email addresses in the document before selecting one."
          },
          {
            "step": 4,
            "action": "classify_email_ownership",
            "rule": "Determine whether each email belongs to the broker company, selected broker agent, shipper, receiver, carrier, accounting, claims, tracking, payment, or another entity."
          },
          {
            "step": 5,
            "action": "apply_locality",
            "rule": "Prefer an email appearing in the same local contact block, same logical section, or tightly related nearby lines as the selected broker agent."
          },
          {
            "step": 6,
            "action": "verify_person_association",
            "rule": "The email must be explicitly or strongly associated with the selected agent. A correct broker-company domain alone is not sufficient."
          },
          {
            "step": 7,
            "action": "verify_broker_domain",
            "rule": "If the email uses the selected broker company's established business domain, treat that as strong supporting evidence."
          },
          {
            "step": 8,
            "action": "final_check",
            "rule": "Return the email only if both broker-company ownership and selected-person ownership are supported."
          }
        ],

        "strong_evidence": [
          "Selected agent name and email appear together",
          "Email appears directly under or beside the selected agent",
          "Document says 'Email <person> at <email>'",
          "Document says 'Please Sign and Email to <person> (<email>)'",
          "Document says 'For specific information contact <person> at <email>'",
          "The same agent-email pair is repeated elsewhere",
          "The email uses the selected broker company's business domain"
        ],

        "broker_domain_rule": {
          "rule": "A matching broker-company domain proves company association, not necessarily person association.",

          "example": {
            "broker": "Armstrong Transport Group",
            "broker_domain": "armstrongtransport.com",

            "company_email": {
              "value": "carriers@armstrongtransport.com",
              "result": "BROKER COMPANY EMAIL ONLY"
            },

            "agent_email": {
              "value": "l.phillip@armstrongtransport.com",
              "result": "STRONG AGENT EMAIL"
            }
          }
        },

        "generic_mailbox_rule": {
          "generic_examples": [
            "carriers@",
            "dispatch@",
            "info@",
            "operations@",
            "billing@",
            "accounting@",
            "support@"
          ],

          "rule": "A generic mailbox on the broker's domain belongs to the broker company unless the document explicitly identifies it as the selected agent's personal contact email.",

          "do_not_use_for_named_agent": true
        },

        "public_email_rule": {
          "examples": [
            "gmail.com",
            "hotmail.com",
            "outlook.com",
            "yahoo.com",
            "icloud.com"
          ],

          "rule": "Do not select a public-domain email merely because it appears near the agent. It may be used only when the document explicitly identifies it as belonging to the selected broker agent and it does not match profile_exclusion."
        },

        "locality_rule": {
          "rule": "The agent email should normally be located with the selected agent's name, phone, extension, or broker-agent contact block.",

          "must_not_do": [
            "Do not take the agent name from page 1 and an unrelated email from page 3.",
            "Do not take an email from a shipper section.",
            "Do not take an email from a receiver section.",
            "Do not take an email from notes or instructions.",
            "Do not take an accounting or payment email.",
            "Do not substitute a generic broker-company mailbox when the named agent email is missing."
          ],

          "cross_page_exception": "A distant email may be used only when the later section explicitly repeats or names the same broker agent."
        },

        "conflict_policy": [
          "Person-specific email beats generic broker-company email.",
          "Explicit name-email association beats simple broker-domain matching.",
          "Same local contact block beats unrelated distant evidence.",
          "If multiple person-specific emails conflict and the document does not establish which belongs to the agent, return null rather than guessing."
        ],

        "output": {
          "if_supported": "Return the selected broker agent's email exactly as supported by the document.",
          "if_only_company_email_exists": null,
          "if_ambiguous": null,
          "if_not_found": null,
          "never_invent": true
        }
      },

      "entity_consistency_rules": [
        "Contact name, phone, extension, and email must describe the same individual.",
        "Do not assemble a contact tuple from unrelated parts of the document.",
        "Do not combine a broker agent name with a shipper phone.",
        "Do not combine a broker agent name with a receiver phone.",
        "Do not combine a broker agent name with a phone found only in notes or instructions.",
        "Do not combine a broker agent name with the broker company's general phone.",
        "Do not combine a broker agent name with the broker company's generic email.",
        "Do not combine a broker agent name with tenant/carrier email or phone.",
        "Do not combine contact details belonging to two different broker agents.",
        "Missing information should remain null rather than being filled with another entity's information."
      ],

      "output": {
        "allow_partial_contact": true,
        "never_invent": true,
        "never_fill_missing_values_from_unrelated_sections": true,
        "if_name_supported_phone_missing": {
          "broker_contact_phone_snapshot": null,
          "broker_contact_extension_snapshot": null
        },
        "if_name_supported_email_missing": {
          "broker_contact_email_snapshot": null
        }
      }
    },

    "broker_load_reference": {
      "product_field": "broker_load_reference",

      "entity": "broker_load",

      "depends_on": [
        "broker"
      ],

      "goal": "Identify the main load number/reference assigned by the broker to this specific load.",

      "before_populating": [
        {
          "step": 1,
          "action": "find_reference_candidates",
          "rule": "Find all load, order, shipment, confirmation, PO, BOL, pickup, delivery, appointment, audit, and other reference-like identifiers in the document. Do not select the first number found."
        },
        {
          "step": 2,
          "action": "classify_each_reference",
          "rule": "Determine what each identifier belongs to before selecting the broker load reference: broker load, pickup stop, delivery stop, PO, BOL, shipment, carrier, audit report, invoice, payment, authority number, phone, date, or other."
        },
        {
          "step": 3,
          "action": "identify_primary_broker_reference",
          "rule": "Select the identifier the broker uses as the principal number for this specific load."
        },
        {
          "step": 4,
          "action": "separate_stop_references",
          "rule": "Do not use pickup number, delivery number, appointment number, PO, BOL, receiving number, or other stop-specific references as the broker load reference when a separate broker load number exists."
        },
        {
          "step": 5,
          "action": "reject_non_load_numbers",
          "rule": "Reject MC, DOT, phone numbers, rates, weights, dates, timestamps, audit IDs, activity IDs, page numbers, and unrelated system identifiers."
        },
        {
          "step": 6,
          "action": "verify_document_usage",
          "rule": "Prefer a reference repeated or prominently used by the broker to identify the entire transaction."
        },
        {
          "step": 7,
          "action": "verify_broker_context",
          "rule": "Confirm that the identifier belongs to the selected broker/load transaction rather than to a stop, carrier, shipper, receiver, audit system, or another entity."
        },
        {
          "step": 8,
          "action": "resolve_multiple_candidates",
          "rule": "If several reference-like values exist, use label, document structure, repetition, and transaction meaning to identify the broker's primary load number."
        }
      ],

      "strong_labels": [
        "Load #",
        "Load Number",
        "Load ID",
        "Broker Load #",
        "Order #",
        "Order Number",
        "PO #",
        "PO Number",
        "Confirmation #",
        "Shipment #"
      ],

      "strong_evidence": [
        "Order # when clearly used as the broker's main load identifier",
        "PO # / PO Number when clearly used as the broker's main load identifier",
        "Confirmation # when clearly used as the main load identifier",
        "Shipment # when clearly established as the broker's principal load identifier",
        "The same identifier repeated in header, load summary, or load-specific sections"
      ],

      "important_rule": "The label alone does not decide ownership. PO # is NOT automatically a broker_load_reference. A PO number may populate broker_load_reference only when document semantics clearly establish that PO/order identifier as the broker's principal load identifier. Otherwise keep the principal broker Load # in broker_load_reference and retain the PO as a secondary reference (references[] / stop ownership). Production field_rules currently list PO # as a possible primary label — that requires implementation reconciliation and must not be treated as approved design.",

      "must_not_select": [
        "pickup number",
        "delivery number",
        "appointment number",
        "stop reference",
        "MC number",
        "USDOT number",
        "phone number",
        "rate",
        "rate or dollar amount",
        "weight",
        "date",
        "date or timestamp",
        "page number",
        "IP address",
        "invoice number unrelated to the shipment identity",
        "audit ID",
        "audit report ID",
        "activity-history ID",
        "signature ID",
        "digital-signature ID"
      ],

      "stop_reference_rule": {
        "rule": "A pickup, delivery, PO, BOL, appointment, or stop-specific reference must remain associated with that stop or secondary reference and must not replace the broker's primary load reference."
      },

      "conflict_policy": [
        "A clearly labeled broker Load # is stronger than a generic Reference #.",
        "Do not choose the first number found.",
        "Do not choose the largest or longest number.",
        "Do not select a value simply because it appears on the last page.",
        "Do not replace a clear broker load number with a stop-specific reference.",
        "Do not select an audit or system-generated identifier when a clear broker load number exists.",
        "If the primary broker reference cannot be determined confidently, return null."
      ],

      "output": {
        "if_supported": "Return only the identifier value. Do not include source label or prefix text.",
        "preserve_prefix_when_meaningful": false,
        "if_ambiguous": null,
        "if_not_found": null,
        "never_invent": true
      }
    },

    "stop_references": {
      "entity": "physical_stop",

      "status": "RESOLVED_OPTION_B",

      "design_decision": "Use typed {kind, value, label} collections, not dedicated fixed columns. Long-term each physical stop may have its own references[]. Current stops[].reference_number remains compatible for the first parser cutover.",

      "goal": "Identify operational reference numbers required at each pickup or delivery stop and keep every reference attached to the correct physical stop.",

      "proposed_reference_types": [
        "pickup_number",
        "delivery_number",
        "appointment_number",
        "po_number",
        "bol_number",
        "receiving_number",
        "shipping_number",
        "order_number",
        "confirmation_number",
        "other_stop_reference"
      ],

      "before_populating": [
        {
          "step": 1,
          "action": "identify_physical_stop",
          "rule": "First determine which pickup or delivery stop the surrounding section belongs to."
        },
        {
          "step": 2,
          "action": "find_reference_candidates",
          "rule": "Look for reference-like identifiers inside the stop block and in nearby notes, special instructions, pickup instructions, delivery instructions, receiving instructions, shipping instructions, and appointment instructions."
        },
        {
          "step": 3,
          "action": "classify_reference_meaning",
          "rule": "Determine what the identifier actually represents before assigning it: pickup number, delivery number, appointment number, PO, BOL, receiving number, shipping number, order number, confirmation number, or another stop-specific reference."
        },
        {
          "step": 4,
          "action": "verify_stop_ownership",
          "rule": "Confirm which physical stop owns the reference. Do not transfer a reference from one pickup or delivery to another."
        },
        {
          "step": 5,
          "action": "preserve_reference_type",
          "rule": "When the document identifies the reference type, preserve that meaning instead of reducing every reference to an untyped number."
        }
      ],

      "strong_location_evidence": [
        "Reference appears inside the shipper or pickup block",
        "Reference appears inside the receiver, consignee, or delivery block",
        "Reference appears beside the relevant facility",
        "Reference appears in special instructions explicitly referring to that stop",
        "Reference appears in pickup or delivery notes explicitly referring to that stop",
        "Reference appears in appointment instructions for that stop",
        "Reference is labeled Pickup #",
        "Reference is labeled Delivery #",
        "Reference is labeled Appointment #",
        "Reference is labeled PO #",
        "Reference is labeled BOL #",
        "Reference is labeled Receiving #",
        "Reference is labeled Shipping #",
        "Reference is labeled Order #"
      ],

      "notes_and_special_instruction_logic": {
        "rule": "References may appear in notes or special instructions rather than in the main address block.",

        "requirements": [
          "The note or instruction must clearly belong to a specific stop or facility.",
          "The reference must have operational meaning for that stop.",
          "Do not treat every number appearing in notes as a reference."
        ]
      },

      "locality_and_ownership_rules": [
        "A pickup reference must stay with its pickup stop.",
        "A delivery reference must stay with its delivery stop.",
        "An appointment number must stay with the appointment/facility it belongs to.",
        "A PO or BOL must be assigned to the correct stop or shipment context.",
        "Do not take a pickup reference from one page and assign it to a different delivery stop.",
        "Do not take a number from broker company information.",
        "Do not take a number from tenant/carrier information.",
        "Do not take a number from contact information.",
        "Do not take a number from legal terms.",
        "Do not take a number from payment or rate sections.",
        "Do not take audit IDs or activity-history IDs unless the document explicitly establishes them as operational stop references."
      ],

      "appointment_number_logic": {
        "rule": "Appointment number is an identifier and is separate from appointment date and appointment time.",

        "examples": [
          "Appointment # 123456",
          "Appt No A98765",
          "Confirmation # 55621 when explicitly referring to a stop appointment"
        ],

        "must_not_do": [
          "Do not put an appointment number into appointment_date.",
          "Do not put an appointment number into appointment_time.",
          "Do not confuse an appointment confirmation number with the broker load number."
        ]
      },

      "multiple_reference_rule": {
        "rule": "One physical stop may contain more than one valid operational reference.",

        "example": {
          "pickup_number": "NM031640",
          "po_number": "77425",
          "appointment_number": "55081"
        },

        "important": "Do not force multiple different reference types into one value or arbitrarily choose one when the document clearly provides several."
      },

      "proposed_future_output": {
        "references": [
          {
            "kind": "pickup_number",
            "value": "NM031640"
          },
          {
            "kind": "po_number",
            "value": "77425"
          },
          {
            "kind": "appointment_number",
            "value": "55081"
          }
        ]
      },

      "output_policy": {
        "if_supported": "Attach each operational reference to the correct stop and preserve its type.",
        "if_reference_type_is_uncertain": "Preserve only when sufficient stop ownership and reference meaning are supported.",
        "if_stop_ownership_is_ambiguous": null,
        "never_invent": true
      }
    },

    "freight_mode": {
      "product_field": "mode",

      "entity": "load",

      "goal": "Identify the transportation mode for this load, such as Full Truckload, Less Than Truckload, Partial, or Power Only, using explicit document evidence.",

      "before_populating": [
        {
          "step": 1,
          "action": "look_for_explicit_mode",
          "rule": "First look for an explicit load-level Mode, Freight Mode, Service Type, Shipment Type, or equivalent field."
        },
        {
          "step": 2,
          "action": "normalize_common_terms",
          "rule": "Normalize equivalent terminology only when the meaning is clear."
        },
        {
          "step": 3,
          "action": "separate_mode_from_equipment",
          "rule": "Do not determine freight mode only from trailer or equipment type."
        },
        {
          "step": 4,
          "action": "separate_mode_from_stop_behavior",
          "rule": "Live load, live unload, drop trailer, appointment type, or number of stops do not by themselves establish freight mode."
        },
        {
          "step": 5,
          "action": "check_power_only",
          "rule": "If the document explicitly identifies the shipment as Power Only, Power-Only, or equivalent, it may populate the freight mode as Power Only."
        },
        {
          "step": 6,
          "action": "avoid_guessing",
          "rule": "If mode is not explicitly stated or strongly established, return null rather than infer it from weight, trailer size, rate, commodity, or number of pallets."
        }
      ],

      "normalization": {
        "Full TruckLoad": "FTL",
        "Full Truckload": "FTL",
        "FTL": "FTL",
        "Truckload": "FTL",

        "Less Than Truckload": "LTL",
        "Less-than-Truckload": "LTL",
        "LTL": "LTL",

        "Partial": "PARTIAL",
        "Partial Truckload": "PARTIAL",

        "Power Only": "POWER_ONLY",
        "Power-Only": "POWER_ONLY"
      },

      "must_not_infer_from": [
        "53 ft trailer",
        "dry van",
        "reefer",
        "weight",
        "pallet count",
        "single pickup and single delivery",
        "live/live shipment",
        "exclusive-use wording by itself",
        "rate amount"
      ],

      "examples": {
        "armstrong": {
          "source": "Mode: Full TruckLoad",
          "output": "FTL"
        },
        "tql": {
          "source": "Mode: FTL",
          "output": "FTL"
        },
        "jbhunt": {
          "source": "Power Only Shipment: No; Live/Live Shipment: Yes",
          "output": null,
          "reason": "These fields describe operating characteristics but do not independently establish a general freight mode."
        }
      },

      "output": {
        "if_supported": "Return the normalized freight mode.",
        "if_ambiguous": null,
        "if_not_found": null,
        "never_invent": true
      }
    },

    "equipment_type": {
      "product_field": "equipment_type",

      "entity": "load_equipment_requirement",

      "goal": "Identify the equipment description or equipment requirement explicitly assigned to this load by the broker.",

      "before_populating": [
        {
          "step": 1,
          "action": "find_explicit_equipment_evidence",
          "rule": "Look for load-level fields such as Equipment, Equipment Type, Equipment Required, Equipment Requested, Trailer/Equipment, or equivalent wording."
        },
        {
          "step": 2,
          "action": "confirm_load_ownership",
          "rule": "Confirm the equipment description applies to this shipment/load and is not a carrier asset number, truck number, trailer number, return-equipment instruction, or equipment mentioned only in legal terms."
        },
        {
          "step": 3,
          "action": "preserve_source_description",
          "rule": "Preserve the meaningful equipment description supplied by the broker rather than guessing a normalized value too early."
        },
        {
          "step": 4,
          "action": "separate_equipment_from_asset_identity",
          "rule": "Do not confuse equipment requirement with the actual assigned tractor number, trailer number, container number, or chassis number."
        },
        {
          "step": 5,
          "action": "separate_equipment_from_mode",
          "rule": "Do not use freight mode such as FTL, LTL, or Power Only as equipment_type unless the document explicitly uses it as an equipment requirement."
        },
        {
          "step": 6,
          "action": "separate_normalized_components",
          "rule": "Trailer type and trailer size will be handled by their own fields. Equipment_type may preserve the broader source equipment description from which those later fields are derived."
        },
        {
          "step": 7,
          "action": "handle_broker_codes",
          "rule": "If the broker provides an equipment code, preserve it only when it is clearly an equipment designation. Do not invent the meaning of an unknown broker-specific code."
        },
        {
          "step": 8,
          "action": "avoid_inference",
          "rule": "If no equipment requirement is explicitly stated or strongly supported, return null rather than infer it from commodity, weight, temperature, dimensions, or trailer assigned by the carrier."
        }
      ],

      "strong_labels": [
        "Equipment",
        "Equipment Type",
        "Equipment Required",
        "Equipment Requested",
        "Trailer/Equipment",
        "Equipment Description"
      ],

      "valid_examples": [
        "V53, 53' Van",
        "Reefer 53'",
        "53' Dry Van",
        "Flatbed",
        "Step Deck",
        "Conestoga",
        "Straight Truck"
      ],

      "must_not_select": [
        "tractor number",
        "truck number",
        "trailer asset number",
        "container number",
        "chassis number",
        "driver information",
        "carrier-owned equipment ID",
        "equipment mentioned only in legal boilerplate",
        "equipment return phone number",
        "commodity",
        "weight",
        "temperature setting"
      ],

      "broker_code_policy": {
        "rule": "Broker-specific equipment codes may be preserved when clearly labeled as equipment, but their meaning must not be invented.",
        "example": {
          "source": "53VN48VN 28VN",
          "action": "Preserve only if clearly presented as the load's equipment requirement; do not guess expansion if unsupported."
        }
      },

      "relationship_to_other_fields": {
        "mode": "Describes freight/service mode and is separate.",
        "trailer_type": "Will contain the normalized trailer/body type when supported.",
        "trailer_size": "Will contain the normalized trailer length/size when supported.",
        "tractor_number": "Operational assigned asset; never equipment_type.",
        "trailer_number": "Operational assigned asset; never equipment_type."
      },

      "real_document_examples": {
        "armstrong": {
          "source": "Equipment: V53, 53' Van",
          "equipment_type": "V53, 53' Van"
        },

        "bm2": {
          "source": "Equipment Type: Reefer 53'",
          "equipment_type": "Reefer 53'"
        },

        "jbhunt": {
          "source": "Equipment Type: 53' Dry Van",
          "equipment_type": "53' Dry Van"
        },

        "tql": {
          "source": "Trailer Type: Van Or Reefer; Trailer Size: 48 ft or 53 ft",
          "equipment_type": null,
          "reason": "The document supplies trailer type and trailer size separately. Do not invent an additional equipment_type merely to fill the field."
        }
      },

      "output": {
        "if_supported": "Return the equipment description supported by the document.",
        "preserve_meaningful_source_code": true,
        "if_only_trailer_type_and_size_are_supplied": null,
        "if_ambiguous": null,
        "if_not_found": null,
        "never_invent": true
      }
    },

    "trailer_type": {
      "product_field": "trailer_type",

      "entity": "load_trailer_requirement",

      "depends_on": [
        "equipment_type"
      ],

      "goal": "Identify the trailer body/type required by the broker for this load, separate from trailer size, trailer asset number, freight mode, and temperature requirement.",

      "before_populating": [
        {
          "step": 1,
          "action": "find_trailer_requirement",
          "rule": "Look for Trailer Type, Equipment Type, Equipment, Trailer, Equipment Required, or equivalent load-level fields."
        },
        {
          "step": 2,
          "action": "confirm_load_context",
          "rule": "Confirm the value describes the trailer required for the shipment and not an assigned trailer asset number or equipment mentioned in unrelated instructions."
        },
        {
          "step": 3,
          "action": "separate_type_from_size",
          "rule": "When type and size appear together, extract only the trailer body/type into trailer_type and leave the length/size for trailer_size."
        },
        {
          "step": 4,
          "action": "preserve_allowed_alternatives",
          "rule": "If the broker explicitly permits more than one trailer type, preserve the alternatives instead of arbitrarily selecting one."
        },
        {
          "step": 5,
          "action": "normalize_clear_synonyms",
          "rule": "Normalize only well-established equivalent trailer terminology when meaning is unambiguous."
        },
        {
          "step": 6,
          "action": "avoid_temperature_inference",
          "rule": "Do not infer Reefer merely because a temperature appears elsewhere. The trailer requirement itself must support refrigerated equipment."
        },
        {
          "step": 7,
          "action": "avoid_commodity_inference",
          "rule": "Do not infer trailer type from commodity, weight, pallets, season, or destination."
        }
      ],

      "common_types": [
        "Dry Van",
        "Van",
        "Reefer",
        "Refrigerated",
        "Flatbed",
        "Step Deck",
        "Conestoga",
        "Power Only",
        "Straight Truck",
        "Box Truck",
        "Container",
        "Lowboy"
      ],

      "normalization": {
        "Dry Van": "Dry Van",
        "Van": "Van",
        "Reefer": "Reefer",
        "Refrigerated": "Reefer",
        "Refrigerated Van": "Reefer"
      },

      "multiple_allowed_types": {
        "rule": "If the document explicitly states alternatives, preserve the broker's allowed alternatives rather than selecting one.",
        "examples": [
          {
            "source": "Van Or Reefer",
            "output": "Van Or Reefer"
          },
          {
            "source": "Dry Van / Reefer",
            "output": "Dry Van / Reefer"
          }
        ]
      },

      "must_not_select": [
        "53 ft",
        "48 ft",
        "28 ft",
        "trailer number",
        "tractor number",
        "container asset number",
        "FTL",
        "LTL",
        "temperature setting",
        "commodity",
        "weight",
        "seal requirement",
        "live load/live unload"
      ],

      "relationship_rules": {
        "equipment_type": "May contain the broker's broader original equipment description.",
        "trailer_type": "Contains the trailer body/type only.",
        "trailer_size": "Contains the required trailer length or size only.",
        "temperature_requirement": "Contains temperature settings/handling requirements and must not by itself determine trailer type.",
        "trailer_asset_number": "Identifies the actual assigned trailer and is not trailer_type."
      },

      "real_document_examples": {
        "armstrong": {
          "source": "Equipment: V53, 53' Van",
          "trailer_type": "Van"
        },

        "bm2": {
          "source": "Equipment Type: Reefer 53'",
          "trailer_type": "Reefer"
        },

        "jbhunt": {
          "source": "Equipment Type: 53' Dry Van",
          "trailer_type": "Dry Van"
        },

        "tql": {
          "source": "Trailer Type: Van Or Reefer",
          "trailer_type": "Van Or Reefer",
          "rule": "Do not choose Van or Reefer on behalf of the broker."
        },

        "rxo": {
          "source": "Equipment: Van - 53 Feet",
          "trailer_type": "Van"
        }
      },

      "output": {
        "if_supported": "Return the trailer body/type required by the broker.",
        "preserve_explicit_alternatives": true,
        "if_ambiguous": null,
        "if_not_found": null,
        "never_invent": true
      }
    },

    "trailer_size": {
      "product_field": "trailer_size",

      "entity": "load_trailer_requirement",

      "depends_on": [
        "equipment_type",
        "trailer_type"
      ],

      "goal": "Identify the trailer length or size required by the broker for this load, separate from trailer type and trailer asset number.",

      "before_populating": [
        {
          "step": 1,
          "action": "find_size_evidence",
          "rule": "Look for trailer size or length in fields such as Trailer Size, Equipment, Equipment Type, Trailer, or equivalent load-level equipment descriptions."
        },
        {
          "step": 2,
          "action": "confirm_load_requirement",
          "rule": "Confirm the size describes the required trailer/equipment for this shipment."
        },
        {
          "step": 3,
          "action": "separate_size_from_type",
          "rule": "When type and size appear together, extract only the length/size into trailer_size."
        },
        {
          "step": 4,
          "action": "normalize_units",
          "rule": "Normalize clearly equivalent length expressions such as 53', 53 ft, and 53 Feet to a consistent display form."
        },
        {
          "step": 5,
          "action": "preserve_allowed_sizes",
          "rule": "If the broker explicitly permits multiple trailer sizes, preserve all allowed sizes rather than selecting one."
        },
        {
          "step": 6,
          "action": "reject_asset_numbers",
          "rule": "Do not confuse trailer size with trailer number, container number, tractor number, seal number, or another equipment identifier."
        },
        {
          "step": 7,
          "action": "avoid_inference",
          "rule": "Do not infer trailer size from weight, commodity, pallet count, route, or common industry practice."
        }
      ],

      "normalization": {
        "53'": "53 ft",
        "53 ft": "53 ft",
        "53 feet": "53 ft",
        "48'": "48 ft",
        "48 ft": "48 ft",
        "48 feet": "48 ft",
        "28'": "28 ft",
        "28 ft": "28 ft"
      },

      "multiple_allowed_sizes": {
        "rule": "If the broker provides alternatives, preserve the alternatives.",
        "examples": [
          {
            "source": "48 ft or 53 ft",
            "output": "48 ft or 53 ft"
          },
          {
            "source": "48'/53'",
            "output": "48 ft / 53 ft"
          }
        ]
      },

      "must_not_select": [
        "trailer asset number",
        "tractor number",
        "container number",
        "seal number",
        "weight",
        "pallet count",
        "commodity dimensions",
        "freight mode",
        "temperature"
      ],

      "relationship_rules": {
        "equipment_type": "May contain the original combined equipment description.",
        "trailer_type": "Contains the trailer body/type.",
        "trailer_size": "Contains only trailer length or supported size alternatives."
      },

      "real_document_examples": {
        "armstrong": {
          "source": "Equipment: V53, 53' Van",
          "trailer_size": "53 ft"
        },

        "bm2": {
          "source": "Equipment Type: Reefer 53'",
          "trailer_size": "53 ft"
        },

        "jbhunt": {
          "source": "Equipment Type: 53' Dry Van",
          "trailer_size": "53 ft"
        },

        "tql": {
          "source": "Trailer Size: 48 ft or 53 ft",
          "trailer_size": "48 ft or 53 ft",
          "rule": "Do not choose one allowed size."
        },

        "rxo": {
          "source": "Equipment: Van - 53 Feet",
          "trailer_size": "53 ft"
        }
      },

      "output": {
        "if_supported": "Return the trailer size required by the broker.",
        "normalize_units": true,
        "preserve_explicit_alternatives": true,
        "if_ambiguous": null,
        "if_not_found": null,
        "never_invent": true
      }
    },

    "commodity": {
      "product_field": "commodity",

      "entity": "load_freight",

      "goal": "Identify the actual product, goods, material, or freight being transported on this load.",

      "before_populating": [
        {
          "step": 1,
          "action": "find_commodity_candidates",
          "rule": "Look for load-level fields such as Commodity, Product, Commodity Description, Shipment Information, Description, Order Commodity, Commodity to Pick Up, Items, or equivalent wording."
        },
        {
          "step": 2,
          "action": "confirm_freight_ownership",
          "rule": "Confirm the value describes the freight physically being transported, not equipment, packaging instructions, payment information, facility names, or general legal wording."
        },
        {
          "step": 3,
          "action": "separate_quantity_and_weight",
          "rule": "Remove quantity, pallet count, case count, pieces, and weight from the commodity value when those belong to separate fields."
        },
        {
          "step": 4,
          "action": "separate_reference_codes",
          "rule": "Do not automatically include PO numbers, product IDs, reference numbers, NMFC values, classification codes, or other identifiers in the commodity unless the document clearly makes them part of the commodity description."
        },
        {
          "step": 5,
          "action": "compare_stops",
          "rule": "If the commodity appears at pickup or delivery stops, verify that the descriptions refer to the freight for this load."
        },
        {
          "step": 6,
          "action": "handle_multiple_products",
          "rule": "If multiple different commodities are genuinely being transported on the same load, preserve the supported commodity descriptions rather than arbitrarily selecting only one."
        },
        {
          "step": 7,
          "action": "avoid_inference",
          "rule": "Do not infer commodity from shipper name, receiver name, trailer type, temperature requirement, weight, destination, or general industry assumptions."
        }
      ],

      "strong_labels": [
        "Commodity",
        "Commodity Description",
        "Product",
        "Product Description",
        "Order Commodity",
        "Commodity to Pick Up",
        "Shipment Information",
        "Description",
        "Items"
      ],

      "relationship_rules": {
        "commodity": "Describes what is physically being transported.",
        "estimated_weight": "Weight is separate from commodity.",
        "temperature_requirement": "Temperature handling is separate from commodity.",
        "hazmat": "Hazardous-material status is separate from commodity.",
        "stop_references": "PO, pickup, delivery, BOL, order and appointment references are separate."
      },

      "must_not_select": [
        "shipper company name",
        "receiver company name",
        "facility name",
        "trailer type",
        "trailer size",
        "weight",
        "pallet count",
        "case count",
        "piece count",
        "PO number",
        "BOL number",
        "pickup number",
        "delivery number",
        "appointment number",
        "rate",
        "special instructions",
        "generic legal descriptions of freight"
      ],

      "multiple_commodity_rule": {
        "rule": "Keep the current scalar commodity field for this parser version. If exactly one supported commodity exists, return that commodity. If multiple genuinely distinct commodities are explicitly part of the same load, preserve all supported descriptions in one scalar string separated by '; '.",
        "example": "Apples; Pears; Grapes",
        "do_not_do": "Do not treat repeated mentions of the same product at different stops as multiple different commodities. Do not include weights, pallet counts, case counts, quantities, or PO/reference numbers unless they are actually part of the commodity's proper description. Do not invent a category or summarize commodities into a guessed umbrella term. A structured commodity collection is a future product/schema project."
      },

      "real_document_examples": {
        "armstrong": {
          "source": "Product: Poly Grind",
          "commodity": "Poly Grind"
        },

        "bm2": {
          "source": "Stuffer Bread",
          "commodity": "Stuffer Bread"
        },

        "hub_group": {
          "source": "Order Commodity: beans and rice",
          "commodity": "beans and rice"
        },

        "jbhunt": {
          "source": "Commodity to Pick Up: Fak (42000.0 lbs)",
          "commodity": "Fak",
          "rule": "Do not include 42000 lbs in commodity."
        },

        "rxo": {
          "source": "RETAIL GOODS (1140)",
          "commodity": "RETAIL GOODS",
          "rule": "Do not automatically treat 1140 as part of the commodity unless the document establishes that it is part of the description."
        },

        "landstar": {
          "source": "MACHINERY/MACHINE PARTS",
          "commodity": "MACHINERY/MACHINE PARTS"
        },

        "tql": {
          "source": "Tobacco and substitutes",
          "commodity": "Tobacco and substitutes"
        }
      },

      "output": {
        "if_supported": "Return the commodity description supported by the document.",
        "preserve_meaningful_description": true,
        "if_exactly_one_supported": "Return that commodity.",
        "if_multiple_supported": "Join all supported commodity descriptions in one scalar string with '; ' (example: Apples; Pears; Grapes).",
        "structured_collection": "future product/schema project, not this parser version",
        "if_ambiguous": null,
        "if_not_found": null,
        "never_invent": true
      }
    },

    "estimated_weight": {
      "product_field": "estimated_weight",

      "entity": "load_freight",

      "goal": "Identify the total estimated freight weight being transported for this load.",

      "before_populating": [
        {
          "step": 1,
          "action": "find_weight_candidates",
          "rule": "Look for Total Weight, Estimated Weight, Weight, Net Weight, Shipment Weight, Commodity Weight, or equivalent load-level and stop-level weight fields."
        },
        {
          "step": 2,
          "action": "classify_weight_scope",
          "rule": "Determine whether each weight represents the entire load, one commodity line, one pickup quantity, one stop, one piece, one pallet, or another partial quantity."
        },
        {
          "step": 3,
          "action": "prefer_explicit_total",
          "rule": "When the document provides an explicit Total Weight or Estimated Weight for the shipment, prefer that value."
        },
        {
          "step": 4,
          "action": "detect_repeated_load_weight",
          "rule": "The same total load weight may be repeated in the load summary, pickup, delivery, or commodity sections. Repeated identical values describing the same freight must not be added together."
        },
        {
          "step": 5,
          "action": "handle_component_weights",
          "rule": "If there is no explicit total and multiple distinct commodity/component weights clearly make up the complete load, they may be combined only when the document clearly establishes they are separate additive components."
        },
        {
          "step": 6,
          "action": "separate_weight_from_quantity",
          "rule": "Do not confuse pounds or kilograms with pallet count, piece count, case count, dimensions, linear feet, or quantity."
        },
        {
          "step": 7,
          "action": "normalize_units",
          "rule": "Normalize supported weight to pounds for the TruckERP estimated_weight field when the source unit is known. Never guess the unit."
        }
      ],

      "evidence_priority": [
        "Explicit Total Weight",
        "Explicit Estimated Weight",
        "Explicit shipment-level weight",
        "Commodity/load weight clearly representing the entire shipment",
        "Stop-level weight clearly representing the entire freight",
        "Sum of distinct component weights only when explicitly additive and exhaustive"
      ],

      "duplicate_weight_rule": {
        "rule": "Do not sum the same freight weight merely because it appears at both pickup and delivery or is repeated in multiple document sections.",

        "example": {
          "pickup_weight": "43000 lbs",
          "delivery_weight": "43000 lbs",
          "result": "43000 lbs",
          "not": "86000 lbs"
        }
      },

      "multiple_stop_rule": {
        "rule": "Multiple stops do not automatically mean their listed weights should be added.",

        "examples": [
          "Pickup 1 shows 43000 lbs and Delivery 1 repeats 43000 lbs -> total remains 43000 lbs.",
          "Pickup 1 explicitly loads 20000 lbs and Pickup 2 explicitly adds a different 15000 lbs -> total may be 35000 lbs if the document establishes both are part of the same final load."
        ]
      },

      "must_not_select": [
        "tractor weight",
        "trailer weight",
        "gross vehicle weight rating",
        "axle weight",
        "maximum trailer capacity",
        "pallet count",
        "piece count",
        "case count",
        "commodity classification number",
        "rate",
        "miles",
        "dimensions"
      ],

      "unit_logic": {
        "lb": "pounds",
        "lbs": "pounds",
        "pounds": "pounds",
        "kg": "kilograms",
        "kgs": "kilograms",

        "rule": "If kilograms are explicitly supplied and TruckERP requires pounds, conversion may occur deterministically after extraction. Do not ask AI to guess an unstated unit."
      },

      "real_document_examples": {
        "armstrong": {
          "source": "43000.00lbs",
          "estimated_weight": 43000
        },

        "bm2": {
          "source": "Total Weight: 17,224",
          "estimated_weight": 17224
        },

        "hub_group": {
          "source": "Weight: 43000.0",
          "estimated_weight": 43000
        },

        "jbhunt": {
          "source": "Commodity to Pick Up: Fak (42000.0 lbs)",
          "estimated_weight": 42000
        },

        "tql": {
          "source": "Estimated Weight 23000",
          "estimated_weight": 23000
        },

        "rxo": {
          "source": "42180",
          "estimated_weight": 42180
        }
      },

      "output": {
        "if_supported": "Return the total estimated freight weight for the load.",
        "preferred_unit": "lb",
        "numeric_only": true,
        "do_not_double_count_repeated_weights": true,
        "if_scope_is_ambiguous": null,
        "if_unit_is_required_but_unknown": null,
        "if_not_found": null,
        "never_invent": true
      }
    },

    "temperature_requirement": {
      "product_field": "temperature_requirement",

      "entity": "load_temperature_control_requirement",

      "goal": "Identify the temperature and refrigerated operating requirements explicitly assigned to this load.",

      "before_populating": [
        {
          "step": 1,
          "action": "find_temperature_evidence",
          "rule": "Look for Temperature, Temp, Temperature Setting, Temperature Minimum, Temperature Maximum, Set Point, Special Temp Instructions, Temperature Run Type, Continuous, Cycle/Sentry, or equivalent load-specific fields."
        },
        {
          "step": 2,
          "action": "confirm_load_specificity",
          "rule": "Confirm the temperature evidence applies to this specific shipment. Generic refrigerated-freight boilerplate or legal instructions do not establish a temperature for the load."
        },
        {
          "step": 3,
          "action": "identify_numeric_temperature",
          "rule": "Extract the explicit temperature value or range only when the document provides it."
        },
        {
          "step": 4,
          "action": "identify_unit",
          "rule": "Preserve Fahrenheit or Celsius when explicitly stated. Never guess the temperature unit."
        },
        {
          "step": 5,
          "action": "identify_run_mode",
          "rule": "Capture explicit reefer operating mode such as Continuous or Cycle/Sentry when it is stated for the load."
        },
        {
          "step": 6,
          "action": "combine_supported_requirements",
          "rule": "When both numeric temperature and run mode are provided, preserve both because they are separate operational requirements."
        },
        {
          "step": 7,
          "action": "handle_range",
          "rule": "If minimum and maximum differ, preserve the supported range. Do not select one endpoint."
        },
        {
          "step": 8,
          "action": "handle_identical_min_max",
          "rule": "If minimum and maximum are identical, treat that value as the required set point rather than representing it as a range."
        },
        {
          "step": 9,
          "action": "reject_empty_or_na",
          "rule": "Blank, N/A, None, or equivalent values do not establish a temperature requirement."
        }
      ],

      "temperature_components": {
        "set_point": "Explicit single required temperature.",
        "minimum": "Minimum allowed temperature when explicitly provided.",
        "maximum": "Maximum allowed temperature when explicitly provided.",
        "unit": "Fahrenheit or Celsius when explicitly supplied.",
        "run_mode": "Continuous, Cycle/Sentry, Start/Stop, or another explicit reefer operating mode."
      },

      "run_mode_rule": {
        "rule": "Run mode is not a numeric temperature, but it is part of the load's temperature-control requirement when explicitly stated.",

        "examples": [
          {
            "source": "-10 F / Continuous",
            "result": "-10°F, Continuous"
          },
          {
            "source": "Temp: CONTINUOUS",
            "result": "Continuous",
            "important": "Do not invent a numeric temperature."
          }
        ]
      },

      "range_rule": {
        "examples": [
          {
            "minimum": "-10°F",
            "maximum": "-10°F",
            "output": "-10°F"
          },
          {
            "minimum": "34°F",
            "maximum": "38°F",
            "output": "34°F-38°F"
          }
        ],

        "rule": "Do not collapse a genuine allowed range into a single temperature."
      },

      "generic_instruction_exclusion": {
        "rule": "Generic reefer contract language does not establish the temperature requirement for the current load.",

        "examples": [
          "Maintain required temperature.",
          "BOL and rate confirmation temperatures must match.",
          "Reefer must be pre-cooled to requested temperature.",
          "Temperature-controlled shipments must remain within required range."
        ],

        "action": "Use these statements only as supporting operating instructions, not as the source of an unstated temperature."
      },

      "must_not_infer_from": [
        "Reefer trailer type alone",
        "Frozen or refrigerated commodity name alone",
        "Food commodity",
        "Season or outside weather",
        "Shipper or receiver",
        "Generic refrigerated-freight terms",
        "BOL temperature instructions without an actual temperature value"
      ],

      "real_document_examples": {
        "bm2": {
          "source": {
            "units": "F",
            "run_type": "Continuous",
            "maximum": "-10",
            "minimum": "-10"
          },
          "temperature_requirement": "-10°F, Continuous"
        },

        "hub_group": {
          "source": "Temp: CONTINUOUS",
          "temperature_requirement": "Continuous",
          "rule": "No numeric temperature is present, so do not invent one."
        },

        "armstrong": {
          "source": "Temperature:",
          "temperature_requirement": null,
          "rule": "The field is blank. Generic temperature boilerplate elsewhere does not fill it."
        },

        "rxo": {
          "source": "Temp: N/A",
          "temperature_requirement": null
        },

        "jbhunt": {
          "source": "Temperature Controlled: No",
          "temperature_requirement": null,
          "rule": "Do not derive a temperature from generic temperature-controlled shipment terms later in the document."
        }
      },

      "output": {
        "if_numeric_and_mode_supported": "Return both temperature and operating mode.",
        "if_numeric_only_supported": "Return the supported temperature or range.",
        "if_mode_only_supported": "Return the explicit operating mode without inventing a temperature.",
        "if_blank": null,
        "if_na": null,
        "if_ambiguous": null,
        "if_not_found": null,
        "never_invent": true
      }
    },

    "hazmat": {
      "product_field": "hazmat",

      "implementation_status": "APPROVED parse field. CURRENT PRODUCT/LOAD FIELD as hazmat_flag. NOT on parse schema yet. First cutover is not blocked. Load hazmat_flag default=false is a known implementation/persistence gap: AI three-state true/false/null must not be collapsed to false merely because hazmat is absent.",

      "entity": "load_hazardous_material_status",

      "goal": "Determine whether the freight on this specific load is explicitly identified as hazardous material or non-hazardous material.",

      "output_type": "boolean_or_null",

      "before_populating": [
        {
          "step": 1,
          "action": "find_hazmat_evidence",
          "rule": "Look for load-specific fields or statements such as Hazmat, Hazardous, Hazardous Material, HM, Dangerous Goods, DG, Non-Hazardous, Haz Mat, or equivalent wording."
        },
        {
          "step": 2,
          "action": "confirm_load_specificity",
          "rule": "Confirm the evidence describes the freight on this particular load rather than generic broker terms, carrier qualifications, insurance requirements, or legal boilerplate."
        },
        {
          "step": 3,
          "action": "interpret_explicit_positive",
          "rule": "If the document explicitly states Hazmat: Yes, Hazardous, HM: Yes, Dangerous Goods, or equivalent for this shipment, return true."
        },
        {
          "step": 4,
          "action": "interpret_explicit_negative",
          "rule": "If the document explicitly states Hazmat: No, Non-Hazardous, Not Hazardous, HM: No, or equivalent for this shipment, return false."
        },
        {
          "step": 5,
          "action": "handle_checkbox_or_table",
          "rule": "For checkbox, X-mark, or table formats, determine whether the mark actually corresponds to the hazmat field. Do not interpret an isolated X without establishing the column/row relationship."
        },
        {
          "step": 6,
          "action": "reject_missing_evidence",
          "rule": "If the document does not establish hazmat status, return null rather than assuming false."
        }
      ],

      "positive_evidence": [
        "Hazmat: Yes",
        "Hazardous: Yes",
        "Hazardous Material",
        "HM: Yes",
        "Dangerous Goods: Yes",
        "Explicit checked/marked Hazmat field tied to this load",
        "Explicit hazmat classification tied to this shipment"
      ],

      "negative_evidence": [
        "Hazmat: No",
        "Hazardous: No",
        "Non-Hazardous",
        "Not Hazardous",
        "HM: No",
        "Dangerous Goods: No"
      ],

      "checkbox_and_table_rule": {
        "rule": "A checkbox, X, Y/N indicator, or abbreviated HM column is valid only when its relationship to the hazmat field is clear.",

        "important": [
          "Do not interpret an X merely because it appears near the commodity.",
          "Use table headers, row alignment, labels, or visual structure to establish meaning.",
          "If the mark cannot be confidently associated with Hazmat/HM, return null."
        ]
      },

      "must_not_infer_from": [
        "commodity name alone",
        "chemical-sounding product name alone",
        "food or ordinary freight",
        "reefer status",
        "trailer type",
        "temperature",
        "weight",
        "NMFC number",
        "freight class",
        "insurance language",
        "generic hazardous-material contract terms",
        "carrier hazmat qualification"
      ],

      "generic_boilerplate_rule": {
        "rule": "Statements describing what the carrier must do when transporting hazardous materials do not prove that the current load is hazardous.",

        "example": "Carrier must comply with all hazardous materials regulations.",

        "result": null
      },

      "real_document_examples": {
        "jbhunt": {
          "source": "Hazmat: No",
          "hazmat": false
        },

        "tql": {
          "source": "Hazmat: Non-Hazardous",
          "hazmat": false
        },

        "armstrong": {
          "source": "No load-specific hazmat value established",
          "hazmat": null,
          "rule": "Do not assume false from Poly Grind or Van equipment."
        },

        "bm2": {
          "source": "Shipment table includes an HM (X) column",
          "hazmat": null,
          "rule": "The visible extracted text alone does not safely establish whether the mark applies to this commodity. Use document/table structure before deciding."
        },

        "landstar": {
          "source": "Haz Mat appears as a field/heading but the available evidence does not clearly establish a value",
          "hazmat": null
        }
      },

      "conflict_policy": [
        "Explicit load-specific Yes/No evidence beats inference.",
        "Explicit Non-Hazardous means false.",
        "Do not convert missing hazmat information into false.",
        "If contradictory load-specific hazmat indicators cannot be resolved, return null."
      ],

      "output": {
        "explicit_hazardous": true,
        "explicit_non_hazardous": false,
        "missing_or_ambiguous": null,
        "never_invent": true
      }
    },

    "rate": {
      "product_field": "rate",

      "entity": "broker_carrier_freight_rate",

      "goal": "Identify the primary agreed freight transportation rate the broker will pay the carrier for hauling this load. This is normally one load-level amount.",

      "core_principle": "Extract the agreed freight rate only. Do not calculate net pay and do not add or subtract accessorials, reimbursements, penalties, fines, deductions, advances, or conditional charges.",

      "implementation_status": "CURRENT PRODUCT/PARSE FIELD",

      "design_vs_production_conflict": "Production field_rules.rate_broker_pay currently prefers total compensation / Total Carrier Pay. Approved design is primary linehaul/freight rate only (Hub Group 1600.00, not Total Carrier Pay 1683.02). Do not change production code from this document.",

      "before_populating": [
        {
          "step": 1,
          "action": "find_all_money_candidates",
          "rule": "Find monetary values throughout the document before selecting the rate."
        },
        {
          "step": 2,
          "action": "classify_each_amount",
          "rule": "Classify each amount as freight rate, linehaul, accessorial, reimbursement, penalty, deduction, fee, advance, quick-pay charge, detention, layover, TONU, lumper, or other monetary value."
        },
        {
          "step": 3,
          "action": "identify_primary_freight_rate",
          "rule": "Select the amount representing the broker's agreed payment to the carrier for transportation of the load itself."
        },
        {
          "step": 4,
          "action": "prefer_direct_rate_evidence",
          "rule": "Prefer explicit labels such as Rate, Agreed Rate, Carrier Freight Pay, Line Haul, Freight Charges, Load Rate, or an explicit load-level total clearly representing the freight rate."
        },
        {
          "step": 5,
          "action": "exclude_accessorials",
          "rule": "Never add detention, layover, TONU, lumper, unloading, extra stop, tarp, escort, storage, reimbursement, or other accessorial amounts into rate."
        },
        {
          "step": 6,
          "action": "exclude_penalties",
          "rule": "Never subtract late-delivery charges, tracking fines, paperwork penalties, claims, rate reductions, missed-appointment charges, or other possible deductions from rate."
        },
        {
          "step": 7,
          "action": "exclude_payment_terms",
          "rule": "QuickPay percentages, factoring fees, advance fees, EFS fees, payment terms, and invoice-processing charges do not alter the rate."
        },
        {
          "step": 8,
          "action": "avoid_net_pay_calculation",
          "rule": "Do not calculate what the carrier may ultimately receive after reimbursements, accessorials, deductions, or fees. The field is the agreed freight rate, not final settlement."
        },
        {
          "step": 9,
          "action": "preserve_currency",
          "rule": "Use explicit document currency when available. Never infer currency from route geography alone."
        }
      ],

      "strong_rate_labels": [
        "Rate",
        "Agreed Rate",
        "Load Rate",
        "Carrier Freight Pay",
        "Line Haul",
        "Linehaul",
        "Freight Charges",
        "Net Freight Charges",
        "Total Rate",
        "Total USD",
        "Total CAD"
      ],

      "excluded_money_categories": {
        "accessorials": [
          "detention",
          "layover",
          "TONU",
          "truck order not used",
          "lumper",
          "loading",
          "unloading",
          "driver assist",
          "extra stop",
          "reconsignment",
          "tarp",
          "escort",
          "storage",
          "other reimbursement"
        ],

        "penalties_and_deductions": [
          "late delivery fee",
          "late pickup fee",
          "tracking fine",
          "paperwork penalty",
          "rate reduction",
          "claim deduction",
          "non-compliance fine",
          "trailer misuse fee",
          "missed appointment penalty"
        ],

        "payment_mechanics": [
          "QuickPay fee",
          "factoring fee",
          "EFS fee",
          "fuel advance",
          "cash advance",
          "payment processing fee"
        ]
      },

      "important_total_rule": {
        "rule": "Do not automatically trust a field labeled Total Carrier Pay if that total includes accessorials or reimbursements.",

        "example": {
          "carrier_freight_pay": 1600.00,
          "labor_lumper": 83.02,
          "total_carrier_pay": 1683.02,
          "rate_output": 1600.00,
          "reason": "Labor/Lumper is an accessorial/reimbursement, not the primary freight rate."
        }
      },

      "conditional_amount_rule": {
        "rule": "A dollar amount describing what MAY happen later is never the load rate.",

        "examples": [
          "$250 late fee",
          "$50/hour detention",
          "$150 layover",
          "$150 TONU",
          "$250 tracking fine",
          "$50 paperwork deduction",
          "25% rate reduction"
        ]
      },

      "real_document_examples": {
        "armstrong": {
          "rate_source": "Rate: $1,800.00 USD",
          "rate": 1800.00,
          "exclude": [
            "$250 Late Fees",
            "2.5% QuickPay",
            "EFS advance fee"
          ]
        },

        "hub_group": {
          "rate_source": "Carrier Freight Pay: $1,600.00",
          "rate": 1600.00,
          "exclude": [
            "Labor/Lumper $83.02"
          ],
          "do_not_use": "Total Carrier Pay $1,683.02"
        },

        "jbhunt": {
          "rate_source": "Total USD $2841.0",
          "rate": 2841.00,
          "exclude": [
            "detention rates",
            "layover rates",
            "other accessorial schedules"
          ]
        },

        "tql": {
          "rate_source": "Total: $2,100.00 USD",
          "rate": 2100.00,
          "exclude": [
            "detention",
            "demurrage",
            "per diem",
            "QuickPay fees",
            "late fines"
          ]
        },

        "rxo": {
          "rate_source": "Carrier Pay / $2100.00",
          "rate": 2100.00,
          "exclude": [
            "$150 TONU",
            "$150 layover",
            "detention",
            "$150 rate reduction",
            "$50 paperwork reduction",
            "$250 tracking fine"
          ]
        },

        "bm2": {
          "rate_source": "Net Freight Charges USD 2,550.00",
          "rate": 2550.00,
          "exclude": [
            "future detention/layover",
            "TONU",
            "fuel advance fees",
            "tracking fines"
          ]
        },

        "landstar": {
          "rate_source": "Agreed Rate / $1,100.00",
          "rate": 1100.00,
          "exclude": [
            "separately authorized accessorials"
          ]
        }
      },

      "conflict_policy": [
        "A clearly labeled freight/load rate beats unrelated monetary amounts.",
        "Carrier Freight Pay beats a Total Carrier Pay that includes reimbursements or accessorials.",
        "Do not add future or conditional accessorial amounts.",
        "Do not subtract penalties or conditional deductions.",
        "Do not calculate final settlement.",
        "If two genuine primary freight-rate candidates conflict and the document does not establish which one controls, return null."
      ],

      "output": {
        "meaning": "primary agreed freight rate",
        "numeric_only": true,
        "currency_separate_if_supported": true,
        "include_accessorials": false,
        "include_reimbursements": false,
        "apply_penalties": false,
        "apply_payment_fees": false,
        "calculate_net_pay": false,
        "if_ambiguous": null,
        "if_not_found": null,
        "never_invent": true
      }
    },

    "miles": {
      "product_field": "miles",

      "entity": "load_route_distance",

      "goal": "Identify the broker-provided total distance for the transportation route covered by this load.",

      "before_populating": [
        {
          "step": 1,
          "action": "find_distance_candidates",
          "rule": "Look for load-level values labeled Miles, Total Miles, Estimated Miles, Distance (Miles), Route Miles, Loaded Miles, Trip Miles, or equivalent terminology."
        },
        {
          "step": 2,
          "action": "classify_mileage_meaning",
          "rule": "Classify every mileage value before selecting it. Determine whether it represents the total load route, one route segment, out-of-route miles, required driving after pickup, mileage reimbursement, deadhead, or another mileage concept."
        },
        {
          "step": 3,
          "action": "prefer_explicit_total_distance",
          "rule": "Prefer an explicit load-level Total Miles, Estimated Miles, Miles, or Distance value supplied by the broker."
        },
        {
          "step": 4,
          "action": "confirm_route_scope",
          "rule": "Confirm the mileage describes the transportation route for this load, normally from the first freight pickup through the final freight delivery."
        },
        {
          "step": 5,
          "action": "exclude_operational_mileage",
          "rule": "Do not use mileage appearing only in driver instructions, security requirements, minimum-driving requirements, tracking requirements, or other operational notes."
        },
        {
          "step": 6,
          "action": "exclude_accessorial_mileage",
          "rule": "Do not use Out of Route Miles, reconsignment miles, extra miles, deadhead reimbursement, or other possible accessorial mileage as the main load miles."
        },
        {
          "step": 7,
          "action": "do_not_calculate_from_addresses",
          "rule": "If the broker does not provide mileage, return null. Do not ask the AI to calculate road distance from pickup and delivery addresses."
        },
        {
          "step": 8,
          "action": "do_not_derive_from_rate",
          "rule": "Do not derive miles from rate divided by dollars-per-mile unless the document itself explicitly supplies the mileage."
        }
      ],

      "strong_labels": [
        "Miles",
        "Total Miles",
        "Estimated Miles",
        "Distance (Miles)",
        "Route Miles",
        "Trip Miles",
        "Loaded Miles"
      ],

      "excluded_mileage_types": {
        "operational_instructions": [
          "must drive 250 miles after pickup",
          "minimum miles before stopping",
          "daily driving requirement",
          "tracking mileage requirement"
        ],

        "accessorial_or_exception_miles": [
          "Out of Route Miles",
          "reconsignment miles",
          "detour miles",
          "extra miles",
          "deadhead miles unless explicitly defined as the load's total mileage"
        ],

        "other": [
          "distance to equipment return location",
          "distance to truck stop",
          "distance appearing in generic contract examples"
        ]
      },

      "multi_stop_rule": {
        "rule": "If the broker supplies one total mileage for a multi-stop load, use that total. Do not add or recalculate individual stop distances.",

        "if_only_segments_exist": "Only combine segment mileage when the document explicitly presents those segments as exhaustive components of the load's total route. Otherwise return null."
      },

      "dollars_per_mile_rule": {
        "rule": "A Dollars Per Mile value is supporting evidence only and is not itself mileage.",

        "example": {
          "rate": 2841.00,
          "estimated_dollar_per_mile": 3.40,
          "explicit_estimated_miles": 836,
          "miles_output": 836
        },

        "important": "Use the explicit 836 miles. Do not independently calculate mileage from 2841 / 3.40."
      },

      "real_document_examples": {
        "jbhunt": {
          "source": "Estimated Miles: 836.0",
          "miles": 836,
          "exclude": "Out of Route Miles mentioned in accessorial terms"
        },

        "hub_group": {
          "source": "Miles: 498.0",
          "miles": 498
        },

        "bm2": {
          "source": "Distance (Miles): 478.81",
          "miles": 478.81
        },

        "landstar": {
          "source": "Total Miles associated with route details",
          "rule": "Use the value only when its relationship to Total Miles is established by the document structure."
        },

        "tql": {
          "source": "Driver(s) must drive 250 miles after picking up",
          "miles": null,
          "rule": "250 is an operating/security instruction, not the total route mileage."
        }
      },

      "conflict_policy": [
        "Explicit Total Miles beats incidental mileage references.",
        "Explicit load-level Estimated Miles beats mileage mentioned in instructions.",
        "Main route mileage beats out-of-route/accessorial mileage.",
        "Do not choose a mileage simply because it is the largest number.",
        "If two genuine total-route mileage values conflict and the document does not establish which is authoritative, return null."
      ],

      "output": {
        "meaning": "broker-provided load route mileage",
        "informational_only": true,
        "not_used_for_driver_or_company_pay": true,
        "unit": "miles",
        "numeric_only": true,
        "calculate_from_addresses": false,
        "derive_from_rate_per_mile": false,
        "include_out_of_route_miles": false,
        "if_ambiguous": null,
        "if_not_found": null,
        "never_invent": true
      }
    },

    "stops": {
      "product_field": "stops",

      "entity": "physical_load_route",

      "goal": "Extract the ordered physical locations the truck must visit to perform this shipment, together with the operational information belonging to each visit.",

      "ui_out_of_scope": "PICKUP 1 / DELIVERY 1 / custom dispatcher headings are presentation only and must not be added to this AI JSON.",

      "stop_fields": [
        "stop_type",
        "sequence",
        "facility_name",
        "street",
        "city",
        "state_or_province",
        "postal_code",
        "country",
        "reference_number",
        "appointment_type",
        "appointment_date",
        "appointment_time_text",
        "notes"
      ],

      "before_creating_stop": [
        "Prove this is a physical location the truck is expected to visit.",
        "Determine its role in the shipment route.",
        "Associate the facility, address, appointment and references with that same physical visit.",
        "Preserve the actual route order.",
        "Do not create duplicate stops from repeated mentions elsewhere in the PDF."
      ],

      "stop_type_rules": {
        "pickup": "Freight is loaded, collected, picked up, or added to the trailer.",
        "delivery": "Freight is delivered, received, or unloaded.",
        "drop": "Use only when the document clearly establishes a distinct operational drop-type visit and preserving 'drop' is meaningful.",
        "other": "Use only for a genuine required physical shipment visit that cannot correctly be classified as pickup, delivery, or drop."
      },

      "facility_and_address": {
        "rule": "Facility name and address must belong to the same physical stop.",
        "do_not_mix": [
          "facility from one stop with address from another",
          "broker office",
          "carrier/tenant address",
          "billing address",
          "factoring address",
          "invoice mailing address",
          "customs broker office",
          "corporate headquarters unless truck actually visits it"
        ],
        "missing_components": "Populate supported components and leave unsupported components null. Never manufacture a full address."
      },

      "appointment": {
        "rule": "Date, time and appointment semantics must remain attached to their own stop.",
        "date": "Normalize unambiguous dates to YYYY-MM-DD.",
        "time": "Preserve the actual time or window supplied by the broker.",
        "examples": [
          "06:30-10:00",
          "Appt 14:00",
          "07:00-12:00",
          "FCFS"
        ],
        "never_do": [
          "turn a time window into only the first time",
          "use document creation date",
          "use signature/audit timestamp",
          "use detention timing",
          "invent an appointment time"
        ]
      },

      "reference_number": {
        "rule": "A stop reference must operationally belong to that stop.",
        "examples": [
          "pickup number",
          "delivery number",
          "PO associated with the stop",
          "appointment/reference number"
        ],
        "never_use": [
          "broker load number",
          "MC number",
          "DOT number",
          "phone number",
          "rate",
          "weight",
          "audit ID",
          "random numeric token"
        ],
        "important": "The current stop model has one generic reference_number field. More detailed typed stop references are a separate design decision."
      },

      "notes": {
        "rule": "Keep operational instructions that specifically belong to this stop.",
        "examples": [
          "check-in instruction",
          "gate instruction",
          "specific loading instruction",
          "specific delivery instruction",
          "facility-specific requirement"
        ],
        "exclude": [
          "generic broker terms",
          "payment instructions",
          "QuickPay instructions",
          "general legal boilerplate",
          "unrelated load-wide policy text"
        ]
      },

      "route_rules": [
        "Multiple pickups are valid.",
        "Multiple deliveries are valid.",
        "Pickup-delivery-pickup-delivery patterns are possible if the document actually establishes them.",
        "Do not assume exactly two stops.",
        "Do not combine two distinct physical visits because the company name is the same.",
        "Do not create two stops merely because one physical location is repeated on multiple pages.",
        "Sequence represents the physical route order shown by the broker."
      ],

      "output": {
        "if_physical_visit_supported": "Create one stop with all supported fields.",
        "if_field_missing": null,
        "if_duplicate_mention": "Do not create another stop.",
        "if_not_a_physical_route_location": "Do not create a stop.",
        "never_invent": true
      }
    },

    "references": {
      "product_field": "references",

      "design_decision": "RESOLVED Option B. references[] remains part of the AI parse contract. Long-term each physical stop may have its own references[] collection. Current stops[].reference_number remains supported during the first parser cutover. Permanent persistence of all secondary references on the Load is outside the current parser implementation decision. Do not remove references[] because persistence is not yet finalized.",

      "entity": "shipment_reference",

      "goal": "Preserve meaningful shipment and operational identifiers other than the principal broker load reference, while maintaining their business meaning and ownership.",

      "output_structure": [
        {
          "kind": "string",
          "value": "string",
          "label": "string_or_null",
          "primary_candidate": "boolean_or_null",
          "confidence": "string_or_null"
        }
      ],

      "before_populating": [
        {
          "step": 1,
          "action": "find_reference_candidates",
          "rule": "Find identifiers associated with the shipment, stops, purchase orders, BOLs, appointments, pickup, delivery, receiving, shipping, orders, confirmations, or other operational references."
        },
        {
          "step": 2,
          "action": "classify_reference_meaning",
          "rule": "Determine what each identifier means before returning it. Do not treat every number or alphanumeric token as a reference."
        },
        {
          "step": 3,
          "action": "protect_primary_load_reference",
          "rule": "The principal broker load number belongs in broker_load_reference. Secondary references must not replace it merely because they are longer, more numeric, repeated more often, or appear later."
        },
        {
          "step": 4,
          "action": "preserve_reference_type",
          "rule": "When the document clearly identifies the type, preserve that semantic type instead of flattening every identifier into generic reference."
        },
        {
          "step": 5,
          "action": "preserve_stop_ownership",
          "rule": "References belonging to a physical pickup or delivery must remain associated conceptually with that stop and must not be transferred to another stop."
        },
        {
          "step": 6,
          "action": "interpret_notes_and_instructions",
          "rule": "Operational notes may explain the true meaning of a reference. Use that explicit explanation when supported."
        },
        {
          "step": 7,
          "action": "deduplicate",
          "rule": "Repeated identical references with the same meaning should not create meaningless duplicates."
        }
      ],

      "common_kinds": [
        "pickup_number",
        "delivery_number",
        "appointment_number",
        "po_number",
        "bol_number",
        "receiving_number",
        "shipping_number",
        "order_number",
        "confirmation_number",
        "shipment_number",
        "pro_number",
        "el_number",
        "other_stop_reference",
        "other_shipment_reference"
      ],

      "label_rule": {
        "rule": "Preserve the document's source label when useful for understanding broker-specific abbreviations.",
        "examples": [
          "PO",
          "PU",
          "AO",
          "SI",
          "CO",
          "CR",
          "EL"
        ]
      },

      "semantic_override_rule": {
        "rule": "Explicit document instructions describing what a reference is used for override a superficial abbreviation when the instruction is clear.",

        "example": {
          "source": "The driver's delivery number is the AO number listed in the reference numbers on the rate con.",
          "kind": "delivery_number",
          "label": "AO"
        }
      },

      "value_validation": {
        "rule": "A nearby label does not automatically make the following text a valid reference. Confirm that the value actually behaves like an operational identifier.",

        "example": {
          "source": "Reference number: PO 13 STRAPS REQUIRED",
          "action": "Do not automatically treat '13 STRAPS REQUIRED' as a PO number merely because PO appears before it."
        }
      },

      "must_not_select": [
        "phone numbers",
        "MC numbers",
        "USDOT numbers",
        "rates",
        "weights",
        "mileage",
        "dates",
        "times",
        "timestamps",
        "IP addresses",
        "page numbers",
        "audit history IDs",
        "signature tracking IDs",
        "random numeric tokens",
        "equipment asset numbers unless explicitly shipment references"
      ],

      "real_document_examples": {
        "armstrong": {
          "broker_load_reference": "3872125-1",
          "references": [
            {
              "kind": "pickup_number",
              "value": "NM031640",
              "label": "Pick/Drop #"
            }
          ],
          "exclude": "Rate Confirmation ID 5506390 because it is an audit-system identifier."
        },

        "bm2": {
          "references": [
            {
              "kind": "other_stop_reference",
              "value": "49561506",
              "label": "Shipper References"
            }
          ],
          "rule": "Additional slash-separated pickup/delivery identifiers must be classified rather than blindly merged."
        },

        "hub_group": {
          "references": [
            {
              "kind": "po_number",
              "value": "7505967670",
              "label": "PO"
            },
            {
              "kind": "pickup_number",
              "value": "SO029636",
              "label": "PU"
            },
            {
              "kind": "delivery_number",
              "value": "531779999948867",
              "label": "AO"
            }
          ]
        },

        "rxo": {
          "references": [
            {
              "kind": "po_number",
              "value": "0001345963699",
              "label": "PO"
            },
            {
              "kind": "shipping_number",
              "value": "OR342958",
              "label": "SI"
            },
            {
              "kind": "delivery_number",
              "value": "36045870",
              "label": "CR"
            }
          ]
        }
      },

      "conflict_policy": [
        "Explicit business meaning beats position.",
        "Explicit operational instruction beats guessed abbreviation expansion.",
        "A stop-specific reference stays with its stop.",
        "The broker Load # remains the primary broker_load_reference.",
        "If reference type is uncertain but the identifier itself is clearly valid, preserve it as other_shipment_reference or other_stop_reference rather than inventing a type."
      ],

      "output": {
        "preserve_supported_secondary_references": true,
        "preserve_business_meaning": true,
        "deduplicate_equivalent_references": true,
        "never_promote_secondary_reference_without_evidence": true,
        "never_invent": true
      }
    },

    "customer_rate": {
      "product_field": "customer_rate",

      "implementation_status": "AUXILIARY CURRENT FIELD",

      "entity": "broker_customer_charge",

      "goal": "Retain the existing schema field for compatibility only. Do not treat customer_rate as a major AI extraction target.",

      "rules": [
        "Carrier rate confirmations normally disclose carrier freight pay, not broker-customer pricing.",
        "Default customer_rate to null.",
        "Never copy rate into customer_rate.",
        "Populate only if a separate customer-facing rate is explicitly and unambiguously shown."
      ],

      "output": {
        "default": null,
        "never_copy_from_carrier_rate": true,
        "never_invent": true
      }
    },

    "customs_broker_name": {
      "product_field": "customs_broker_name",

      "implementation_status": "AUXILIARY CURRENT FIELD",

      "entity": "customs_broker_company",

      "goal": "Identify a customs broker named in the document when that party is explicitly a customs broker, not the freight broker.",

      "rules": [
        "customs_broker_name is auxiliary and is not freight-broker identity.",
        "Never copy a customs broker into broker_name_snapshot.",
        "A labeled CUSTOMS BROKER line identifies a customs broker, not the freight broker."
      ],

      "example": {
        "source": "CUSTOMS BROKER: Tahoco Logistics",
        "customs_broker_name": "Tahoco Logistics",
        "broker_name_snapshot": "must remain the freight broker, never Tahoco Logistics"
      },

      "output": {
        "if_explicit_customs_broker": "Return customs_broker_name.",
        "if_not_found": null,
        "never_use_as_freight_broker": true,
        "never_invent": true
      }
    },

    "document_type": {
      "product_field": "document_type",

      "implementation_status": "AUXILIARY CURRENT FIELD",

      "location": "parse root, not extracted",

      "allowed_values": [
        "rate_confirmation",
        "driver_information_sheet",
        "invoice",
        "bol",
        "other"
      ],

      "goal": "Classify the PDF before filling extracted fields.",

      "output": {
        "if_supported": "Return the supported document_type.",
        "if_ambiguous": "other or null per existing schema",
        "never_invent_a_load_from_a_non_rate_con": true
      }
    },

    "classification_reasoning": {
      "product_field": "classification_reasoning",

      "implementation_status": "AUXILIARY CURRENT FIELD",

      "location": "parse root, not extracted",

      "goal": "Provide a short evidence summary for document_type and how stops/contacts were interpreted.",

      "rules": [
        "classification_reasoning is a short evidence summary.",
        "It is not hidden chain-of-thought.",
        "Do not dump internal reasoning traces."
      ]
    },

    "warnings": {
      "product_field": "warnings",

      "implementation_status": "CURRENT PRODUCT/PARSE FIELD",

      "location": "parse root",

      "goal": "Surface meaningful ambiguity that requires human review.",

      "rules": [
        "warnings = meaningful ambiguity requiring review.",
        "Do not emit a warning merely because an ordinary optional field is missing or null.",
        "Insufficient evidence still yields null on the field; a warning is additional, not a license to guess."
      ]
    },

    "field_confidence": {
      "product_field": "field_confidence",

      "implementation_status": "CURRENT PRODUCT/PARSE FIELD",

      "location": "parse root",

      "goal": "Record per-field confidence only after a supported extraction.",

      "rules": [
        "Confidence does not authorize guessing.",
        "Insufficient evidence yields null, even if confidence would be low.",
        "Do not populate a field solely because a low-confidence guess is available."
      ]
    },

    "truckerp_internal_load_number": {
      "product_field": "load_number",

      "implementation_status": "CURRENT PRODUCT/LOAD FIELD — not an AI extraction target",

      "goal": "Keep TruckERP internal load numbering separate from broker_load_reference.",

      "example": {
        "internal_load_number": "INT-2A023C5255CE",
        "broker_load_reference": "3872125-1"
      },

      "rules": [
        "AI extracts the broker Load # into broker_load_reference.",
        "AI does not overwrite or generate TruckERP internal load_number."
      ]
    }
  }
}
```

## Final Design Reconciliation

| Logical field/group | Current schema support | Current production `field_rules` support | Final approved semantics in this MD? | Conflict/gap? | Implementation action later? |
|---|---|---|---|---|---|
| profile_exclusion / tenant_identity_exclusion | Handoff runtime object | Referenced in broker/contact/authority rules | Yes | Names differ; same object | Map design name only; do not duplicate |
| broker company (`broker_name_snapshot`) | Parse + Load | `broker_company` | Yes | None material | Wire richer design when approved |
| broker company phone (`broker_phone_snapshot`) | **None** | **None** | Yes — **APPROVED PROPOSED**; not a first-cutover blocker | Schema/UI deferred | Add schema/UI when implementation is authorized |
| broker authority MC/USDOT | Parse (snapshots); Load hydrates via resolve-identity | `broker_authority` | Yes | None material | Align prompt with this MD when approved |
| broker agent name/phone/email | Parse + Load | `broker_contact` | Yes | Production rules weaker than design (generic mailbox / company vs person) | Update `field_rules` later |
| broker agent extension | **Load yes**; **parse schema no** | **None** | Yes — **APPROVED**; parse later | Parse cannot return extension today | Add parse field when authorized; do not attach corporate/shipper/receiver/tenant extensions |
| broker agent cohesion | Design + Load (if extension used) | Partial (person-specific contact) | Yes | Parse missing extension | Later |
| broker_load_reference | Parse + Load | `broker_load_reference` | Yes | Production lists PO # as a possible primary label; **design: PO is not automatically primary** | Implementation reconciliation required |
| internal `load_number` | Load only | N/A (not AI) | Yes | None | Keep AI off this field |
| freight mode | Parse + Load | **No dedicated group** | Yes | Schema exists; static rules do not | Add `field_rules` later |
| equipment_type / trailer_type / trailer_size | Parse + Load | **No dedicated group** | Yes | Same | Add `field_rules` later |
| commodity / estimated_weight / temperature | Parse + Load | **No dedicated group** | Yes | Commodity: scalar; multiple joined with `"; "` | Add `field_rules` later; structured commodity collection is future |
| hazmat | Load `hazmat_flag`; **not on parse** | **None** | Yes — **APPROVED** three-state parse | Load default `false` vs AI `null` for missing | Persistence reconciliation required; do not infer false |
| rate | Parse + Load | `rate_broker_pay` | Yes | **CONFLICT:** production total compensation vs design linehaul | Change `field_rules` only when implementation is approved |
| customer_rate | Parse + Load | `customer_rate_guardrail` | Yes (auxiliary) | Aligned: default null, do not copy rate | Keep as-is until told otherwise |
| miles | Parse float; Load int | **No dedicated group** | Yes | Type mismatch parse vs Load; no miles rules | Add rules later; do not use for pay |
| stops | Parse + Load | `stops` + pickup/delivery + appointment | Yes | Design `drop`/`other` vs production delivery wording | Keep cohesive group; no UI headings in JSON |
| typed references | Parse `references[]`; generic `stops[].reference_number` | `references` | Yes — **Option B RESOLVED** | Per-stop `stops[].references[]` is long-term; Load persistence of the full collection is outside this parser decision | First cutover keeps generic stop `reference_number`; do not require per-stop collection |
| customs_broker_name | Parse | Broker rules say do not confuse customs broker | Yes | No dedicated customs_broker `field_rules` group | Keep auxiliary; never freight broker |
| document_type / classification_reasoning | Parse root | Not in `field_rules` | Yes | None | Keep short evidence summary |
| warnings / field_confidence | Parse root | Mechanical validation writes some | Yes | None | Confidence must not authorize guessing |

## Known Production Conflicts

1. **Rate (must-fix later, do not fix now)**  
   Production `LOAD_RATE_CON_FIELD_RULES["rules"]["rate_broker_pay"]` meaning is *“the total compensation the broker agreed to pay our carrier”* and prefers an explicit **Total Carrier Pay** / stated total, including authorized pay-breakdown totals.  
   Approved design: **primary agreed freight/linehaul only**. Hub Group: Carrier Freight Pay **1600.00**, not Total Carrier Pay **1683.02** (lumper 83.02 excluded).

2. **Broker company phone (`broker_phone_snapshot`)** — APPROVED PROPOSED FIELD, not a first-cutover blocker.  
   Not on `LoadParseExtractedFields` or Load schema. Must stay separate from `broker_contact_phone_snapshot` (Armstrong 877-240-1181 vs Loflin 208-751-8073). Schema/UI deferred until implementation is authorized.

3. **Broker agent extension** — APPROVED parse field; Load already has it.  
   Parse schema and production `broker_contact` product_fields omit extension. Belongs only to the selected agent’s direct phone. Parse-schema work later; first cutover is not blocked.

4. **Hazmat** — APPROVED three-state parse (`true` / `false` / `null`).  
   Parse schema has no `hazmat`. Load `hazmat_flag` **default=false** is a known **implementation/persistence gap**: absent/ambiguous AI `null` must not be persisted as non-hazardous. Do not solve in code now.

5. **Mode / equipment / trailer / commodity / weight / temperature / miles**  
   These are CURRENT parse/Load fields but have **no** dedicated groups in production `field_rules`. The AI currently fills them without this contract’s static semantics. Commodity multiples, when authorized later, join with `"; "` in the existing scalar field.

6. **Miles type**  
   Parse `miles` is `Optional[float]`; Load `miles` is `Optional[int]`.

7. **broker_load_reference / PO # labels — implementation reconciliation required**  
   Production `possible_labels_examples` still include `PO #` / `PO Number` as if they were ordinary primary-load labels.  
   Approved design: **PO # is not automatically `broker_load_reference`**. A PO may fill that field only when the document clearly establishes it as the broker’s principal load identifier. Otherwise keep Load # in `broker_load_reference` and retain PO in `references[]`.

8. **Generic company mailbox vs agent email**  
   Design forbids assigning `carriers@` to a named agent. Production `broker_contact` is weaker (person-specific when supported; generic substitution language exists but not the full company-vs-agent mailbox split).

9. **Typed references persistence**  
   Parse `references[]` stays in the AI contract (Option B). Permanent Load persistence of the full secondary-reference collection is **outside** this parser decision. First cutover keeps `stops[].reference_number`.

Do **not** change parser, schema, `field_rules`, frontend, database, tests, or deployment from this document.

## Design Decisions Resolved

1. **Typed stop references — Option B.** `references[]` is a typed `{kind, value, label}` collection. Long-term each physical stop may have its own `references[]`. Dedicated fixed columns are not scalable. `stops[].reference_number` remains for first cutover. The richer per-stop collection does not block the first parser cutover.

2. **`broker_phone_snapshot` — APPROVED PROPOSED FIELD.** Broker company corporate/main phone, separate from agent phone. Armstrong `877-240-1181` is company; Loflin Phillips’ number is agent. Schema/UI may be deferred; first parser implementation is not blocked.

3. **`broker_contact_extension_snapshot` — APPROVED.** Already on Load. Belongs to the selected individual agent, normally with that person’s direct phone. Never attach an extension from corporate/general/shipper/receiver/tenant contacts. Null when unsupported. Parse-schema implementation later.

4. **Hazmat — APPROVED three-state parse.** Explicit Yes/Hazardous = `true`; explicit No/Non-Hazardous = `false`; absent or ambiguous = `null`. Never infer false because hazmat is unmentioned. Load `hazmat_flag` default=`false` is a documented implementation/persistence gap, not solved in code now.

5. **Multiple commodities — keep scalar `commodity`.** One commodity → that string. Multiple genuine commodities → `"Apples; Pears; Grapes"`. Do not attach weights/qty/POs unless they are part of the proper description. Do not invent an umbrella category. A structured commodity collection is a future product/schema project.

6. **`references[]` persistence.** Extraction remains in the AI parse contract. Permanent persistence of all secondary references on the Load is outside the current parser implementation decision. Do not drop `references[]` because persistence is not finalized.

7. **PO # vs `broker_load_reference`.** PO is not automatically the principal load identifier. It fills `broker_load_reference` only when the document clearly establishes that PO/order as the broker’s principal load identifier. Otherwise Load # stays primary and PO is a secondary reference. Production possible-label treatment of PO # requires implementation reconciliation.

---

RATE CONFIRMATION AI FIELD CONTRACT:  
**DESIGN COMPLETE — IMPLEMENTATION NOT YET APPROVED**

The design is now frozen for implementation review.  
No production code should be modified until explicit implementation authorization.
