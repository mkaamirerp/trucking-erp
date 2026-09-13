# TruckERP To Do

Use this folder as the parking lot for work that is intentionally pending: bugs to resolve later, future features, deferred cleanup/removals, investigations, and known edge cases.

## Onboarding / People

### Onboarding requirements engine / role and scope rules

Status: architecture defined; implementation pending.

Use [`docs/Onboarding_Rules.md`](../Onboarding_Rules.md) as the design source for the future onboarding requirements engine.

Key direction:

- One onboarding door into People for every worker/person.
- Common Person/contact data stays separate from role-specific credential/evidence data.
- Requirements are selected by explicit applicability dimensions: common/universal, role, scope, jurisdiction, and employment/business relationship.
- Requirement applicability is separate from lifecycle timing; not every applicable item is mandatory at initial application submission.
- Use stage/eligibility gates such as application submit, approval, work start, company-vehicle eligibility, dispatch eligibility, and cross-border eligibility instead of one `required`/`blocking` flag.
- Documents/evidence, verification state, and operational eligibility are separate concepts.
- Driver is the first full rule set but the engine must not be Driver-shaped.
- Owner-operator is a relationship/business arrangement, not a separate PersonRole.
- Cross-border is a work scope, not a role.
- Preserve requirement/evidence history when roles, scope, policy, or documents change.

Before implementation, do a focused schema report against the current PersonApplication / Person / PersonRole / document-request / approval-promotion flow and propose the minimum requirement-definition + requirement-instance + evidence/gate model. Do not build copied role-specific forms or scatter `if role == ...` logic through frontend/backend.

### Existing applicant detection before sending onboarding link

Status: pending / future work.

When an admin enters an email to send an onboarding application link, TruckERP must check whether that email already exists in People / applicant history before creating or sending a new application.

Rules:

- No duplicate email identities in People.
- If the email already exists, warn the admin before sending a new link.
- Show the existing person/applicant and current/previous application status, including partial, submitted, rejected, withdrawn/declined, approved, or other historical states.
- Provide an **Open Applicant** action from the warning so the admin can review the existing record immediately.
- From the Applicant Review page, allow the admin to resend/reissue a secure onboarding link.
- If there is an active or incomplete application, the applicant should resume from the saved state/step rather than starting over.
- Support a **Please update your application** flow that reopens the saved application for review/update when appropriate.
- Preserve prior application history, notes, documents, decisions, and audit trail. Do not overwrite or erase a previous rejected/withdrawn/completed application merely because the person is invited again.
- One person identity may have multiple application cycles over time; duplicate People records for the same normalized email should not be created.

Architecture intent:

```text
Admin enters email
  -> lookup normalized email in People + person_applications
  -> no match: normal new-application flow
  -> match: warning with person/application history + Open Applicant
      -> resend/resume existing active application
      OR
      -> request update/reopen as appropriate
      OR
      -> create a new application cycle linked to the same person while preserving prior history
```

Do not implement this as a silent duplicate check only; the admin needs enough context and a direct route to the existing applicant record to decide what to do.

### Driver licence data is updated only by replacing/updating the licence

Status: pending / future work.

Driver-licence-derived identity/licence data must not be treated as ordinary editable contact/profile fields. Once accepted from the current driver licence, those values stay tied to that licence record until the licence itself is replaced or updated.

Rules:

- Do not allow applicant contact-info edits to directly change DL-derived data.
- DL-derived fields include the authoritative values captured from the licence/PDF417, such as name, date of birth, licence number, issuing region, class, issue/expiry dates, sex, height, and licence address where present.
- Contact/mailing information is a separate concept and may differ from the address printed on the driver licence.
- On Applicant Review, add an admin action such as **Update Driver Licence** / **Replace Driver Licence**.
- That action should upload/confirm the new licence, rerun the normal DL processing/parsing flow, and then update the current DL-derived values from the new accepted licence.
- Preserve the previous licence/document and audit history; replacing a licence must not erase historical evidence.
- In People / Driver Detail, the current driver licence should be visible and have the same controlled replace/update action.
- Any DL-derived People fields should update from the newly accepted licence through the same canonical flow, not by freehand editing those fields independently.
- Changing contact/mailing address must not overwrite the address printed on the current driver licence.

Architecture intent:

```text
Current accepted DL
  -> authoritative DL-derived values
  -> shown in Applicant Review / People

Admin chooses Update/Replace Driver Licence
  -> upload + process + confirm new DL
  -> preserve old DL/history
  -> new accepted DL becomes current
  -> refresh DL-derived fields in application/person/driver projections
  -> audit the change

Contact/mailing information
  -> separate editable data
  -> may use "same as driver licence address"
  -> may differ without changing the DL record
```

This is future work; do not mix it into the current onboarding validation/date-field patch.
