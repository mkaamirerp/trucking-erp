# TruckERP To Do

Use this folder as the parking lot for work that is intentionally pending: bugs to resolve later, future features, deferred cleanup/removals, investigations, and known edge cases.

## Onboarding / People

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
