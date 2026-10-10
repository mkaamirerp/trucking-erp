ok now we are in serious discussion of driver onboarding i am going to paste the respose from cursor then i will paste what I asked otherway aound then we make a plan

What needs to happen (for your plan to work)
Database
Add one column to driver_onboarding_submissions, e.g. intake_payload JSONB NULL, via a new tenant migration.
Model
Add intake_payload (e.g. Mapped[dict | None] / JSONB) to DriverOnboardingSubmission.
Schema
Extend create/update payload to accept the nested structure (work_history, references, documents, agreement flags, CDL class, endorsements, DOB, SSN last 4, etc.) and validate it as needed.
Add intake_payload to DriverOnboardingSubmissionOut (and ensure it’s returned by the GET submission endpoint).
Driver portal
Replace or extend the current form into the 4 steps (License; Personal; Work history + References; Documents + Agreements), and on save/submit send both the existing flat fields and the new blob as intake_payload in the same request(s).
Admin page
Replace (or heavily modify) the existing admin detail page with your FleetPro-style component that reads submission.intake_payload and displays all four steps; keep using the existing approve/reject endpoints.
Questions before implementation
Create/update API shape
Should the driver portal send everything in a single create/update request with a body like { ...flatFields, intake_payload: { cdl_class, endorsements, work_history, references, documents, agree_* } }, or do you want separate endpoints (e.g. save step 1, save step 2, …) that merge into one submission? (Your note suggests “intake_payload exists for extended fields” and “flat columns come from the model as-is,” which fits a single payload with flat + intake_payload.)
Document keys
Your admin UI uses DOC_META keys: medical, mvr, drug, psp, ss, employ, cert, bank. Should intake_payload.documents be exactly Record<string, string> keyed by these (e.g. value = storage key or filename), or do you use different keys on the driver side that we need to map?
Approve response type
Backend returns { submission, person } (PersonOut). The frontend type currently says driver. For the new admin page, are you okay with changing the type to person (and using that only if needed), or do you need the API to also return a “driver” view (e.g. from driver_profiles) for backward compatibility?
Status casing
API returns DRAFT, SUBMITTED, etc. Your new component types use lowercase ("draft" | "submitted" | ...). Should the admin page normalize in the frontend (e.g. status?.toLowerCase()), or do you want the API to return lowercase status for this flow?
Existing admin list/detail
Should the list page (DriverOnboardingAdminListPage.tsx) stay as-is (only add a link to the new detail), and the detail page be fully replaced by your pasted FleetPro component (with submissionId, tenantSlug, apiBase, onBack props), or do you want to keep the current detail page and add the new one as a separate route (e.g. /admin/driver-onboarding/:id/full)?
person_id
Today, create flow creates Person + DriverProfile + PersonRole and sets submission.person_id. With the 4-step flow, should we keep the same behavior (create/update Person from flat + any fields we copy from intake_payload on approve), or do you want person created only on “submit” (step 4 complete) and not on draft?
Once these are decided, the changes are: one tenant migration, model + schema updates, driver portal 4-step form, and admin detail page replacement (or new route) using your FleetPro layout and existing approve/reject endpoints. I’m in Ask mode so I can’t edit the repo; if you want the actual code changes applied, switch to Agent mode and we can do it step by step.

Yes — before we let Cursor touch code, we should lock the direction first.

My read is this:

Cursor’s shape is reasonable, but it is pointed at the older object driver_onboarding_submissions, while our more current direction is PersonApplication + PersonApplicationFile as the intake container. That is the first thing we should settle, otherwise we will build the 4-step flow on a table we already planned to replace.

My recommendation

Do not invest more in driver_onboarding_submissions unless you deliberately want a temporary bridge.
Build this on person_applications and keep intake_payload JSONB there as the single flexible intake store.

That matches our newer direction better:

application = intake container

files = PersonApplicationFile

approval = promote application into People/DriverProfile/Documents

admin review = read from intake_payload

no second migration later just to move the same blob again

Best plan to lock
1) Canonical object

Use:

person_applications as the main onboarding record

person_application_files for uploaded files

intake_payload JSONB for all extended step data

Flat columns should stay only for the truly top-level searchable/reportable fields you need early. Everything else goes into intake_payload.

2) 4-step flow

Use one application record across all steps:

Step 1: License

Step 2: Personal

Step 3: Work history + References

Step 4: Documents + Agreements

Each step saves into the same application row.

3) Save model

Use draft-save per step, not one giant submit-only payload.

Best pattern:

POST /person-applications → create draft

PATCH /person-applications/{id} → merge fields into intake_payload

POST /person-applications/{id}/submit → validate required minimums, set status SUBMITTED

That gives you:

resume later

partial saves

fewer data loss issues

better UX

4) Approval model

Do not create Person/DriverProfile on draft.
Create them on admin approval only.

Reason:

drafts are messy, incomplete, abandoned

you avoid polluting people, driver_profiles, person_roles

admin remains the gatekeeper

So:

Draft / submitted application lives in onboarding tables only

On approval:

create/update people

create driver_profile

create role rows

promote/link documents

mark application approved

store resulting person_id

This is cleaner and matches your earlier direction.

Answers to Cursor’s questions

Here is what I would tell Cursor.

1) Create/update API shape

Use separate save endpoints by application, but all merge into one record.

Recommended:

POST /api/v1/person-applications

PATCH /api/v1/person-applications/{id}

POST /api/v1/person-applications/{id}/submit

Payload style:

{
  "first_name": "John",
  "last_name": "Doe",
  "phone": "...",
  "email": "...",
  "intake_payload": {
    "license": { ... },
    "personal": { ... },
    "work_history": [ ... ],
    "references": [ ... ],
    "documents": { ... },
    "agreements": { ... }
  }
}

But operationally the frontend can send only the section it is editing, and backend merges it.

2) Document keys

Yes, lock canonical keys now. Do not let driver-side and admin-side drift.

Recommended canonical keys:

medical

mvr

drug

psp

social_security

employment_history

certificate

bank_info

If you want shorter UI aliases, map them in frontend only.
Backend should use one canonical vocabulary.

Even better: make documents an array of structured items instead of loose string map.

Recommended:

"documents": [
  {
    "doc_type": "medical",
    "file_id": 123,
    "status": "uploaded"
  }
]

That is stronger than Record<string, string>.

3) Approve response type

Return person, not driver.

Reason:
your architecture is now People-first, not old driver-first.

Recommended approval response:

{
  "application": {...},
  "person": {...},
  "driver_profile": {...}
}

That gives flexibility without forcing old frontend assumptions.

4) Status casing

Keep API statuses uppercase:

DRAFT

SUBMITTED

APPROVED

REJECTED

Frontend can normalize for display if needed.
Do not weaken backend consistency just for UI style.

5) Existing admin list/detail

Keep the list page mostly as-is for now.
Replace the detail page with the new richer FleetPro-style review screen.

That is the least disruptive path:

admin list stays stable

detail becomes the full 4-step review UI

same approve/reject actions remain

6) person_id

Create person_id only on approval, not on draft and not on ordinary save.

That is my strongest recommendation.

Data shape I recommend

Inside intake_payload, use stable sections:

{
  "license": {
    "country": "US",
    "state": "PA",
    "number": "...",
    "class": "A",
    "endorsements": ["N", "T"],
    "restrictions": [],
    "expires_on": "2027-01-10",
    "dob": "1990-05-01",
    "ssn_last4": "1234",
    "extraction": {
      "status": "SUCCESS",
      "sources": {},
      "confidence": {}
    }
  },
  "personal": {
    "address": {...},
    "emergency_contact": {...},
    "citizenship": "...",
    "work_authorization": "...",
    "can_cross_border": true
  },
  "work_history": [
    {
      "company_name": "...",
      "start_date": "...",
      "end_date": "...",
      "position": "...",
      "reason_for_leaving": "..."
    }
  ],
  "references": [
    {
      "name": "...",
      "phone": "...",
      "relationship": "..."
    }
  ],
  "documents": [
    {
      "doc_type": "medical",
      "file_id": 101,
      "status": "uploaded"
    }
  ],
  "agreements": {
    "background_check": true,
    "drug_testing": true,
    "electronic_signature_name": "John Doe",
    "signed_at": "2026-03-05T10:15:00Z"
  },
  "review": {
    "missing_items": [],
    "admin_notes": null
  }
}

This is much safer than a random freeform blob.

Phased implementation plan
Phase 1 — lock architecture

Decide this first:

use person_applications, not old submission table

draft-save per step

person_id only on approval

uppercase backend statuses

canonical document keys / types

Phase 2 — backend foundation

tenant migration for intake_payload JSONB on person_applications if not already present

schema updates

merge-patch logic for nested intake_payload

submit endpoint with validation

GET application detail returns full payload

Phase 3 — file handling

all uploads go to person_application_files

each uploaded doc stored as file row

intake_payload.documents references file IDs

no raw filename-only logic

Phase 4 — driver portal

4-step wizard

save draft each step

resume support

required checks only block final submit, not draft save

Phase 5 — admin review

FleetPro-style detail page

show all sections from intake_payload

show uploaded file cards

required vs missing docs clearly marked

approve/reject unchanged at action level

Phase 6 — promotion on approval

create/update People-first entities

create driver profile

attach/promote docs

write person_id back to application

audit log everything

Biggest hidden danger here

The biggest danger is building the UI and payload around one model, while approval logic still assumes another model.

In plain words:

portal writes to onboarding blob

admin reads blob

but approve code still expects flat legacy fields or creates driver/person too early

That mismatch causes silent corruption, duplicate records, and partial approvals.

So before UI work starts, lock this rule:

Application data lives in person_applications.intake_payload; approval is the only promotion boundary into People/DriverProfile/business records.

What I would send Cursor

You can send this as the decision set:

Locked decisions for driver onboarding:

1. Do not build new work on driver_onboarding_submissions unless required as a temporary compatibility layer. Canonical onboarding object is person_applications with person_application_files.

2. Use intake_payload JSONB on person_applications as the single container for extended 4-step onboarding data.

3. 4-step flow:
   - license
   - personal
   - work_history + references
   - documents + agreements

4. Save model is draft-save per step against one application record:
   - POST create application
   - PATCH update/merge application
   - POST submit application

5. Do not create Person/DriverProfile on draft. Create/promote only on admin approval. person_id is assigned on approval.

6. Keep backend status values uppercase: DRAFT, SUBMITTED, APPROVED, REJECTED. Frontend can normalize display.

7. Admin list can stay mostly unchanged. Replace admin detail with the richer FleetPro-style review page.

8. Documents should not be a loose filename map. Store uploads in person_application_files and reference them from intake_payload via structured entries, preferably with doc_type + file_id + status.

9. Approve response should be people-first:
   { application, person, driver_profile }
   not legacy driver-only shape.

10. Backend must provide merge-safe nested intake_payload updates and return the full intake_payload on detail GET.

Paste what you asked Cursor next, and I’ll reconcile both sides into one final build plan.

What needs to happen (for your plan to work)
Database
Add one column to driver_onboarding_submissions, e.g. intake_payload JSONB NULL, via a new tenant migration.
Model
Add intake_payload (e.g. Mapped[dict | None] / JSONB) to DriverOnboardingSubmission.
Schema
Extend create/update payload to accept the nested structure (work_history, references, documents, agreement flags, CDL class, endorsements, DOB, SSN last 4, etc.) and validate it as needed.
Add intake_payload to DriverOnboardingSubmissionOut (and ensure it’s returned by the GET submission endpoint).
Driver portal
Replace or extend the current form into the 4 steps (License; Personal; Work history + References; Documents + Agreements), and on save/submit send both the existing flat fields and the new blob as intake_payload in the same request(s).
Admin page
Replace (or heavily modify) the existing admin detail page with your FleetPro-style component that reads submission.intake_payload and displays all four steps; keep using the existing approve/reject endpoints.
Questions before implementation
Create/update API shape
Should the driver portal send everything in a single create/update request with a body like { ...flatFields, intake_payload: { cdl_class, endorsements, work_history, references, documents, agree_* } }, or do you want separate endpoints (e.g. save step 1, save step 2, …) that merge into one submission? (Your note suggests “intake_payload exists for extended fields” and “flat columns come from the model as-is,” which fits a single payload with flat + intake_payload.)
Document keys
Your admin UI uses DOC_META keys: medical, mvr, drug, psp, ss, employ, cert, bank. Should intake_payload.documents be exactly Record<string, string> keyed by these (e.g. value = storage key or filename), or do you use different keys on the driver side that we need to map?
Approve response type
Backend returns { submission, person } (PersonOut). The frontend type currently says driver. For the new admin page, are you okay with changing the type to person (and using that only if needed), or do you need the API to also return a “driver” view (e.g. from driver_profiles) for backward compatibility?
Status casing
API returns DRAFT, SUBMITTED, etc. Your new component types use lowercase ("draft" | "submitted" | ...). Should the admin page normalize in the frontend (e.g. status?.toLowerCase()), or do you want the API to return lowercase status for this flow?
Existing admin list/detail
Should the list page (DriverOnboardingAdminListPage.tsx) stay as-is (only add a link to the new detail), and the detail page be fully replaced by your pasted FleetPro component (with submissionId, tenantSlug, apiBase, onBack props), or do you want to keep the current detail page and add the new one as a separate route (e.g. /admin/driver-onboarding/:id/full)?
person_id
Today, create flow creates Person + DriverProfile + PersonRole and sets submission.person_id. With the 4-step flow, should we keep the same behavior (create/update Person from flat + any fields we copy from intake_payload on approve), or do you want person created only on “submit” (step 4 complete) and not on draft?
Once these are decided, the changes are: one tenant migration, model + schema updates, driver portal 4-step form, and admin detail page replacement (or new route) using your FleetPro layout and existing approve/reject endpoints. I’m in Ask mode so I can’t edit the repo; if you want the actual code changes applied, switch to Agent mode and we can do it step by step.

Here is the plan I would lock if we are proceeding on the current driver_onboarding_submissions path.

Final decisions
1) Create/update API shape

Use one submission record with:

existing flat fields kept as-is

extended data inside intake_payload

Frontend can still save step-by-step, but each save should call the same update endpoint and send only the changed section. Backend should merge intake_payload, not replace the whole blob unless explicitly intended.

Recommended shape:

{
  "first_name": "John",
  "last_name": "Doe",
  "phone": "123",
  "email": "john@example.com",
  "intake_payload": {
    "license": { ... },
    "personal": { ... },
    "work_history": [ ... ],
    "references": [ ... ],
    "documents": [ ... ],
    "agreements": { ... }
  }
}

So the answer is:

single create/update contract

step-based frontend

merge behavior on backend

2) Document keys

Do not use a loose Record<string, string> long-term if we can avoid it.

Use canonical document types and structured entries.

Recommended canonical types:

medical

mvr

drug

psp

ss

employ

cert

bank

Recommended storage inside intake_payload:

"documents": [
  { "doc_type": "medical", "file_name": "medical.pdf", "status": "uploaded" },
  { "doc_type": "mvr", "file_name": "mvr.pdf", "status": "missing" }
]

If you need a lighter first pass, you may temporarily use:

"documents": {
  "medical": "medical.pdf",
  "mvr": "mvr.pdf"
}

But I recommend structured entries now so you do not repaint this later.

3) Approve response type

Keep backend people-first.

Return:

{
  "submission": { ... },
  "person": { ... }
}

If frontend still has an old driver type, fix the frontend type.
Do not force backend to fake a driver object just for compatibility unless absolutely necessary.

4) Status casing

Keep API statuses uppercase:

DRAFT

SUBMITTED

APPROVED

REJECTED

Frontend should normalize display if it wants lowercase.
Do not change API casing just for one component.

5) Existing admin list/detail

Keep the admin list page as-is for now.

Replace the detail page with the richer FleetPro-style detail component.
No need for a second parallel detail route unless you want a temporary safety route during transition.

So:

list stays

detail gets replaced

6) person_id

Do not create Person + DriverProfile on draft.

Best decision:

draft save = only submission row

submit = still only submission row, status becomes SUBMITTED

approve = create Person, DriverProfile, PersonRole, set submission.person_id

This is the cleanest and safest flow.

If you create people on draft, you will accumulate junk incomplete records.

Recommended intake_payload structure
{
  "license": {
    "cdl_class": "A",
    "endorsements": ["N", "T"],
    "dob": "1990-01-01",
    "ssn_last4": "1234",
    "license_number": "X1234567",
    "license_state": "PA",
    "license_expiry": "2027-02-01"
  },
  "personal": {
    "address": {
      "street": "123 Main St",
      "city": "Boston",
      "state": "MA",
      "postal_code": "02110",
      "country": "US"
    },
    "emergency_contact": {
      "name": "Jane Doe",
      "phone": "555-1111",
      "relationship": "Sister"
    }
  },
  "work_history": [
    {
      "company_name": "ABC Trucking",
      "position": "Driver",
      "start_date": "2023-01-01",
      "end_date": "2024-01-01",
      "reason_for_leaving": "Better opportunity"
    }
  ],
  "references": [
    {
      "name": "Mike Smith",
      "phone": "555-2222",
      "relationship": "Supervisor"
    }
  ],
  "documents": [
    {
      "doc_type": "medical",
      "file_name": "medical.pdf",
      "status": "uploaded"
    }
  ],
  "agreements": {
    "agree_background_check": true,
    "agree_drug_testing": true,
    "agree_truthfulness": true,
    "signed_name": "John Doe",
    "signed_at": "2026-03-05T12:00:00Z"
  }
}
Backend behavior to lock
Migration

Add:

driver_onboarding_submissions.intake_payload JSONB NULL

Model

Add:

intake_payload

Schemas

Create nested Pydantic schema, not raw untyped dict only.

At minimum:

LicensePayload

PersonalPayload

WorkHistoryItem

ReferenceItem

DocumentItem

AgreementPayload

Then wrap them under intake_payload.

Update logic

Important:

backend must deep merge sections like license, personal, agreements

arrays like work_history and references can be full replacement per save unless you explicitly want patch-by-row behavior

Validation

Do not require everything at draft stage.

Validation levels:

Draft save: permissive

Submit: enforce required minimums

Approve: enforce admin-required checks

UI behavior to lock
Driver portal

4-step wizard:

License

Personal

Work history + References

Documents + Agreements

Each step:

saves draft

can resume later

writes into same submission

Admin detail

New detail page should:

read flat fields

read submission.intake_payload

show all 4 sections clearly

highlight missing docs

keep current approve/reject actions

Biggest danger

The hidden danger here is this:

If approve logic still assumes flat columns only, while the new UI stores critical data only in intake_payload, approval will silently miss data.

So approval must explicitly read from:

flat submission fields

intake_payload

and map them into:

Person

DriverProfile

PersonRole

documents

That mapping must be written carefully.

What I would tell Cursor
Locked implementation decisions:

1. Proceed on driver_onboarding_submissions for this phase.
2. Add intake_payload JSONB nullable via tenant migration.
3. Keep existing flat fields unchanged; extended onboarding data goes under intake_payload.
4. Use one create/update contract with flat fields + intake_payload.
5. Frontend may save step-by-step, but backend should merge intake_payload into the same submission record.
6. Keep API statuses uppercase; frontend can normalize display.
7. Keep admin list page mostly unchanged; replace admin detail page with the new FleetPro-style review page.
8. Do not create Person/DriverProfile on draft. Only create them on approve, then set submission.person_id.
9. Approve response remains people-first: { submission, person }.
10. Prefer structured documents inside intake_payload, not just Record<string,string>.
11. Submit validation should be stricter than draft-save validation.
12. Approve logic must read both flat fields and intake_payload and map them into Person/DriverProfile/documents.