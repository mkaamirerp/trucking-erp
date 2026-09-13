# TruckERP Onboarding Rules

Status: architecture / foundation design

Purpose: define one onboarding engine for every person entering TruckERP while keeping common person data, role-specific requirements, work scope, employment/business relationship, jurisdiction, evidence, verification, and operational eligibility separate.

This document is the design source for future onboarding work. It is intentionally broader than Driver onboarding. Driver is one role using the same engine.

---

## 1. Core principle: one door into People

TruckERP has one human-entry pipeline:

```text
Invitation / application
  -> applicant onboarding
  -> admin review
  -> approval
  -> Person
  -> PersonRole(s)
  -> role-specific profile / credentials / operational projections
```

The application is the pre-approval working record. `Person` is the canonical approved human/contact identity. Role-specific facts do not belong in People merely because they were collected during onboarding.

Examples:

- Contact/mailing address -> Person.
- Driver-licence address -> driver credential/profile evidence, not editable People contact address.
- Mechanic certification -> mechanic credential/evidence, not a generic Person field.
- Payroll setup -> payroll/employment setup, not a Driver field.

The system must not become a collection of copied forms such as `DriverForm`, `MechanicForm`, and `DispatcherForm` that duplicate common identity/contact fields. It should be one common onboarding shell that renders reusable requirement sections according to rules.

---

## 2. Existing onboarding/application types

Current application types in TruckERP are:

- `DRIVER`
- `DISPATCHER`
- `HR`
- `MECHANIC`
- `PAYROLL`
- `SAFETY`
- `OFFICE_ADMIN`
- `OTHER`

`application_type` controls the onboarding workflow/form track. `requested_role_code` controls the role proposed for assignment on approval. Keep those concepts separate.

Admin may change the proposed/requested role during review if the business decision differs from the original invitation, but that change must be explicit, audited, and must trigger requirement re-evaluation before final approval.

Do not make `OWNER_OPERATOR` a Person role merely to change onboarding questions. Owner-operator/company-driver is an employment/business relationship or Driver-specific operating arrangement, not the occupation itself.

---

## 3. Applicability is not timing

Every onboarding requirement needs two independent answers:

1. **Does this requirement apply to this person?**
2. **At what stage must it be satisfied?**

A requirement can apply to everyone but still not be mandatory on the initial application.

Example:

```text
Work eligibility question
  applies to: every hire
  asked at: application

Work-authorization evidence
  applies to: when verification is required
  requested by: admin/system rule
  blocking stage: work_start

SIN
  applies to: employee/payroll setup
  collected at: post-offer/payroll stage
  not an initial recruiting identity field
```

Do not use one global `required=true` boolean to represent the entire lifecycle.

---

## 4. Applicability dimensions

Requirements are selected by reusable dimensions, not hard-coded role pages.

### 4.1 Common / universal

Examples:

- legal name / core identity
- contact information
- contact/mailing address
- emergency contact
- legal entitlement to work in Canada question
- common agreements/policies where applicable
- Ontario health-and-safety awareness where applicable

Universal does **not** mean every supporting document is mandatory at application submission.

### 4.2 Role

Examples:

- commercial-driver qualification for Driver
- dispatcher experience for Dispatcher
- mechanic credentials for Mechanic
- safety/compliance credentials for Safety

### 4.3 Scope

Scope describes what the person will actually do.

Initial useful tags include:

```text
OPERATES_COMPANY_VEHICLE
ROAD_TESTS_COMMERCIAL_VEHICLES
COMMERCIAL_DRIVER
CITY
OTR
CROSS_BORDER_US
SAFETY_SENSITIVE
SUPERVISOR
MANAGES_DRIVERS
HANDLES_PAYROLL
HANDLES_PERSONAL_INFORMATION
```

A Mechanic can gain road-test requirements without becoming a Driver role. An Office Admin can gain company-vehicle requirements without changing occupational role.

### 4.4 Jurisdiction

Initial useful tags:

```text
CA
ON
US
```

A rule may require a combination such as Driver + Cross-border U.S. + U.S. jurisdiction.

### 4.5 Employment/business relationship

Role answers **what the person does**. Relationship answers **how the person works for the company**.

Examples:

```text
COMPANY_EMPLOYEE
PART_TIME_EMPLOYEE
CONTRACTOR
OWNER_OPERATOR
```

For Driver, provides-own-truck / provides-own-trailer remain Driver-specific operating/equipment attributes. They do not become Person roles.

---

## 5. Applicability rule model: explicit DNF

Applicability must be explicit and deterministic.

Use **disjunctive normal form (DNF)**:

- a requirement contains one or more applicability clauses;
- every predicate inside one clause is **AND**;
- multiple clauses are combined with **OR**.

Conceptually:

```text
requirement applies if:
  clause_1
  OR clause_2
  OR clause_3
```

Each clause can contain predicates from the supported dimensions.

Example:

```text
Requirement: DRIVER_LICENCE

Clause 1:
  role in [DRIVER]

OR

Clause 2:
  role in [MECHANIC]
  AND scope contains ROAD_TESTS_COMMERCIAL_VEHICLES

OR

Clause 3:
  scope contains OPERATES_COMPANY_VEHICLE
```

Within a clause:

- `role_any = [DRIVER, MECHANIC]` means OR among those values;
- `scope_all = [CROSS_BORDER_US, COMMERCIAL_DRIVER]` means both must be present;
- `scope_any = [...]` means at least one must be present;
- jurisdiction and relationship predicates are evaluated the same way according to explicit `*_any` / `*_all` fields.

Do not use ambiguous bare arrays whose AND/OR meaning has to be guessed.

Recommended conceptual clause shape:

```text
applicability_clause {
  role_any[]
  role_all[]
  scope_any[]
  scope_all[]
  jurisdiction_any[]
  jurisdiction_all[]
  relationship_any[]
  relationship_all[]
}
```

Most real rules will use `role_any`, `scope_all`, and `jurisdiction_any`. The exact physical schema can be normalized later, but the boolean semantics are locked here.

---

## 6. Requirement definition contract

Conceptual shape:

```text
onboarding_requirement_definition {
  id
  code
  name
  category
  description
  version
  active

  authority_class
  authority_reference

  applicability_clauses[]

  data_type
  document_type
  requires_document
  admin_requestable
  expiry_tracking
  verification_required

  first_visible_stage
  blocking_stage

  waivable
  waivable_by[]

  applicant_visible
  admin_visible
}
```

### 6.1 Authority class

Use explicit source classes:

```text
REGULATORY
INSURANCE
CUSTOMER
COMPANY_POLICY
CONTRACTUAL
```

Do not describe a company policy as a legal requirement.

### 6.2 Waiver rules

`WAIVED` is a valid requirement status only when the requirement definition allows waiver.

Rules:

- `REGULATORY` requirements default to `waivable = false` unless a lawful exception process is explicitly modeled.
- insurance/customer/company-policy/contractual requirements may be waivable only if the definition says so;
- `waivable_by` controls which admin permission/role may waive it;
- waiver requires reason, actor, timestamp, and audit event;
- the UI must never show a Waive action when `waivable = false`.

---

## 7. Scope determination: who sets it and when

Some scope facts are known before invitation; others are discovered during onboarding. Scope therefore needs an explicit source and precedence model.

### 7.1 Scope sources

A scope assignment can come from:

```text
ADMIN_ASSIGNED
APPLICANT_ANSWER_DERIVED
SYSTEM_DERIVED
POLICY_DERIVED
```

Store source, actor where applicable, timestamp, and rule/version that produced the value.

### 7.2 Precedence

Recommended precedence:

1. explicit admin-approved scope;
2. system/policy-derived mandatory scope;
3. applicant-answer-derived provisional scope.

Applicant answers may propose or derive scope, but they must not silently override an admin-approved work assignment.

### 7.3 Example

```text
Invitation says role = MECHANIC
Applicant answers: "Yes, I will road-test repaired trucks"
  -> provisional scope ROAD_TESTS_COMMERCIAL_VEHICLES
  -> newly applicable DL + abstract requirements appear
Admin review confirms or removes that scope
  -> requirement set re-evaluates
```

For Driver:

```text
Admin assignment may pre-set CROSS_BORDER_US
Applicant answers may confirm passport/FAST/status details
Applicant cannot remove CROSS_BORDER_US merely by answering "No" if the offered job requires it
```

### 7.4 Mid-application scope changes

Whenever a scope is added/removed:

1. recalculate requirements;
2. add newly applicable requirement instances;
3. preserve prior requirement/evidence history;
4. mark no-longer-applicable instances without deleting them;
5. recalculate gates;
6. show the change in admin review/audit.

---

## 8. Policy profile and policy-dependent requirements

Do not turn company policy into hidden branching logic.

Use a policy profile/version as an input to requirement evaluation.

Conceptually:

```text
tenant_policy_profile
  -> requirement definitions / overrides
  -> effective date/version
```

Facts such as `OPERATES_COMPANY_VEHICLE` describe the person/work assignment. Whether that fact requires an annual abstract, background check, or extra training can come from `INSURANCE` or `COMPANY_POLICY` requirement definitions.

When policy changes:

- do not rewrite old application history;
- evaluate the current Person against the new active policy/version where operationally required;
- create new requirement instances rather than mutating historical ones in place.

---

## 9. Lifecycle stages and gates

Recommended stages:

```text
application_draft
application_submit
admin_review
approval
work_start
operational_eligible
company_vehicle_eligible
commercial_driver_eligible
dispatch_eligible
cross_border_eligible
safety_sensitive_cleared
```

A Person can exist in People without being eligible for every operational capability.

### 9.1 Gate dependency table

The gate graph is explicit; gates are not just labels.

| Gate | Minimum parent dependencies | Additional evaluated requirements |
|---|---|---|
| `PERSON_APPROVED` | none | approval-stage common/role requirements |
| `WORK_AUTHORIZED` | none | verified work-authorization requirements when applicable |
| `WORK_START_READY` | `PERSON_APPROVED` + `WORK_AUTHORIZED` when work authorization applies | employment/relationship setup, required agreements, safety orientation, other work-start blockers |
| `COMPANY_VEHICLE_ELIGIBLE` | `WORK_START_READY` | DL, driving abstract/MVR, insurer/company-policy requirements for vehicle operation |
| `COMMERCIAL_DRIVER_ELIGIBLE` | `WORK_START_READY` | commercial licence, medical qualification, regulatory/insurance Driver qualification requirements |
| `SAFETY_SENSITIVE_CLEARED` | `WORK_START_READY` | applicable safety-sensitive testing/clearance requirements |
| `DISPATCH_ELIGIBLE` | for Driver: `COMMERCIAL_DRIVER_ELIGIBLE`; for non-driving dispatch staff: `WORK_START_READY` | role/scope-specific dispatch requirements |
| `CROSS_BORDER_ELIGIBLE` | role-appropriate operational gate plus `WORK_AUTHORIZED` where applicable | border/admissibility/travel/qualification requirements for cross-border scope |

Important: `DISPATCH_ELIGIBLE` is role-aware. A Dispatcher employee does not require `COMMERCIAL_DRIVER_ELIGIBLE`; a truck Driver does.

The implementation may represent this as a dependency graph/table, but circular dependencies are forbidden.

---

## 10. Requirement status is not evidence status

Conceptual requirement statuses:

```text
NOT_APPLICABLE
NOT_STARTED
OPTIONAL
REQUESTED
PROVIDED
UNDER_REVIEW
VERIFIED
REJECTED
EXPIRED
WAIVED
```

Conceptual evidence statuses:

```text
UPLOADED
ACTIVE
SUPERSEDED
REJECTED
EXPIRED
```

Examples:

- DL uploaded but expired -> evidence exists; requirement is not satisfied.
- Work permit uploaded but awaiting review -> evidence exists; work-start gate remains blocked.
- FAST card uploaded but optional -> evidence exists; no blocking effect.

---

## 11. Evidence can satisfy multiple requirement instances

Reusable evidence must be modeled explicitly.

Use a many-to-many satisfaction link:

```text
evidence_item
  -> evidence_satisfaction
       -> requirement_instance
```

Conceptually:

```text
evidence_satisfaction {
  evidence_id
  requirement_instance_id
  satisfaction_status
  verified_by
  verified_at
  notes
}
```

A document may satisfy more than one requirement instance when allowed.

Example:

```text
one verified driver's licence document
  -> satisfies DRIVER_LICENCE instance for Driver role
  -> also satisfies COMPANY_VEHICLE_DRIVER_LICENCE instance created by a second active role/scope
```

### 11.1 Reuse rule

Evidence is reusable only when all required compatibility checks pass, including as applicable:

- accepted `document_type` / evidence type;
- not expired/superseded/rejected;
- verification level meets the target requirement;
- identity/person matches;
- jurisdiction/issuer constraints match;
- requirement definition explicitly permits that evidence type.

Do **not** dedupe merely because two requirements share a similar name.

---

## 12. Requirement code and version semantics

`code` identifies the business concept. `version` identifies the definition/rule version that created an instance.

Rules:

- requirement instances freeze `definition_id` + `definition_version` + relevant evaluated trigger context;
- history never collapses instances from different versions;
- satisfaction reuse may cross versions **only** when the newer definition explicitly accepts the evidence type and its verification still meets the newer rule;
- dedupe of the active/effective checklist is primarily by stable business `code`, but historical instances remain distinct;
- a material rule change that should coexist with the old concept must use a new requirement code, not silently redefine semantics under the old code.

Example:

```text
DRIVER_ABSTRACT v1
DRIVER_ABSTRACT v2
```

The person may see one current Driver Abstract requirement, but audit/history retains both instances that existed at their respective times.

---

## 13. Expiry data belongs in Phase A

The notification/renewal scheduler can wait until a later phase. The **data model cannot**.

Phase A schema must support:

```text
issued_at
expires_at
expiry_source
verification_at
renewal_window_days (definition/policy)
status derived from expiry
```

Requirements/evidence that expire must be able to become `EXPIRED` and invalidate gates even before automated reminders are implemented.

Phase F adds monitoring/notification automation, not the first expiry columns.

---

## 14. Common Person onboarding data

Common Person/contact concepts include:

### Identity

- first name
- middle name where applicable
- last name
- date of birth where lawfully/operationally required at the appropriate stage

### Contact

- email
- phone
- contact/mailing address

### Emergency contact

- name
- relationship
- phone
- optional alternate contact information

### Work eligibility question

At applicant stage use a neutral question such as:

> Are you legally entitled to work in Canada?

Do not make citizenship, PR status, SIN, or immigration-document upload a mandatory initial-application identity question merely because the eligibility question is common.

---

## 15. Work authorization: separate question, verification, and payroll identity

Do not bundle these into a generic `Government ID` requirement.

### 15.1 Work eligibility

Applicant-stage question:

```text
Are you legally entitled to work in Canada?
Yes / No
```

### 15.2 Work-authorization verification

Admin/system-requestable at the appropriate stage.

Possible evidence types, when applicable:

- proof of permanent resident status
- work permit
- study permit with work authorization
- maintained-status / extension evidence
- other permitted supporting evidence

Useful facts:

```text
authorization_type
issued_date
expires_at
conditions/restrictions
verification_status
verified_at
verified_by
```

### 15.3 SIN / payroll identity

Keep SIN separate from immigration/work-authorization evidence and collect it at the appropriate payroll/employment stage with stricter access controls.

Temporary-resident SIN expiry considerations must be representable by the expiry model.

---

## 16. Address source-of-truth rule

```text
Person contact data
  !=
credential/source-document data
```

### Contact/mailing address

- applicant-controlled;
- promoted into People;
- editable later as normal Person contact data.

### Driver-licence address

- sourced from accepted DL/PDF417 evidence;
- stored with Driver licence/profile evidence;
- not freely edited through People contact fields;
- changes through controlled replace/update of the licence.

`Same as driver licence address` may copy current values into contact fields, but the two sources stay distinct.

This pattern applies to other role credentials too: evidence-derived facts stay with the credential/evidence source instead of silently becoming generic Person fields.

---

## 17. Driver's licence is not universal

Split these concepts:

- work eligibility / identity;
- driver's licence;
- commercial-driver qualification.

Typical triggers:

```text
DRIVER -> licence requirement
MECHANIC + ROAD_TESTS_COMMERCIAL_VEHICLES -> licence requirement
OFFICE_ADMIN + OPERATES_COMPANY_VEHICLE -> licence requirement if active policy requires
DISPATCHER -> no licence requirement unless driving scope applies
```

The same DL capture/PDF417 pipeline can be reused anywhere the requirement applies without making the whole onboarding engine Driver-shaped.

---

## 18. Driving record / abstract is separate

Do not bundle MVR/driving abstract with medical or drug/alcohol testing.

A driving record can apply to:

- Driver;
- Mechanic with road-test scope;
- another role with company-vehicle scope;
- insurer/company-policy requirements.

Its refresh cycle, evidence, verification, and gate are independent.

---

## 19. Commercial-driver qualification package

Depending on role/scope/jurisdiction/policy, Driver requirements can include:

- licence class/endorsements/status/expiry;
- driving abstract/MVR;
- regulated prior-employer/safety-performance history where applicable;
- commercial medical qualification;
- drug/alcohol program requirements where applicable;
- equipment experience;
- safety/compliance acknowledgements;
- cross-border requirements where applicable.

Driver work history is not merely generic HR references. It may need a specialized regulatory structure while reusing common employer/contact primitives.

---

## 20. Cross-border is a scope, not a role

Use scope such as:

```text
CROSS_BORDER_US
```

Potential requirements may include:

- required travel/admissibility evidence;
- border/customs/company training;
- cross-border qualification rules;
- customer/company-specific credentials.

### FAST

FAST is a separate trusted-traveller/commercial-clearance credential. It is not synonymous with legal cross-border eligibility.

Model separately:

```text
Cross-border eligibility / required travel evidence
FAST membership/card (optional unless a specific policy requires it)
```

### Commercial medical label

Do not use `USDOT_MEDICAL` as the generic requirement code. Use a neutral code such as:

```text
COMMERCIAL_DRIVER_MEDICAL_QUALIFICATION
```

and let jurisdiction/scope determine the accepted evidence/rule profile.

External FMCSA documentation may use U.S.-specific medical terminology; that does not change TruckERP's generic requirement label.

---

## 21. Role modules

The UI renders a common shell plus applicable modules.

### DRIVER

- commercial licence / DL evidence
- specialized driving history
- driving abstract/MVR
- equipment experience with years per type
- commercial medical qualification
- safety-sensitive requirements
- cross-border requirements when applicable
- Driver relationship/equipment contribution setup

### DISPATCHER

- dispatch experience
- TMS/load-board experience where company-defined
- HOS/compliance/coercion-policy training where applicable
- border/customs knowledge where applicable

### MECHANIC

- mechanic licence/certifications
- specialty/tool/equipment experience
- DL / abstract only when road-test/company-vehicle scope applies
- safety-sensitive/shop training where applicable

### SAFETY

- safety/compliance qualifications
- HOS/compliance training
- audit/recordkeeping competencies
- cross-border compliance knowledge where applicable
- driving qualification only when actual scope requires driving

### HR

- HR experience/credentials where required
- privacy/confidentiality acknowledgements
- common employment setup

### PAYROLL

- payroll/accounting experience where required
- confidentiality/privacy requirements
- common employment setup

### OFFICE_ADMIN

- office/admin experience
- company-system/process training
- vehicle-operation evidence only when scope applies

### OTHER

- configurable fallback for uncommon roles;
- not a dumping ground for owner-operators or known occupations.

---

## 22. Employment/payroll/tax setup

Do not assume every Person is an employee.

### Employee relationship

Potential post-offer/work-start requirements:

- direct deposit/banking
- federal TD1
- provincial/territorial TD1, e.g. TD1ON
- payroll/SIN setup
- employment agreement

### Contractor / owner-operator relationship

Potential setup:

- legal business name
- entity/type
- business number where applicable
- GST/HST registration where applicable
- remittance/payment banking
- insurance evidence
- contractor/owner-operator agreement
- truck/trailer/equipment contribution information

Do not force employee TD1/payroll requirements onto an owner-operator because both may have role `DRIVER`.

---

## 23. Document/evidence model

A requirement may be satisfied by zero, one, or multiple evidence items, and one evidence item may satisfy multiple requirement instances.

Conceptual model:

```text
requirement_instance
  <- evidence_satisfaction -> evidence_item

requirement_instance
  -> review/verification state
  -> blocking stage
  -> expiry impact
  -> audit history

evidence_item
  -> document metadata/files
  -> issuer/effective/expiry facts
  -> evidence status
```

TruckERP's existing document-request/resume mechanism should be driven by requirement instances instead of inventing a separate upload flow for each role.

Admin actions can include:

- request evidence;
- provide instructions/reason;
- accept/reject evidence;
- link reusable evidence to another applicable requirement;
- waive only where allowed;
- preserve superseded history.

---

## 24. Requirement instances freeze what applied

When rules evaluate for an application/person, freeze enough context to explain later why the requirement existed.

At minimum preserve:

```text
definition_id
requirement_code
definition_version
evaluated_role(s)
evaluated_scope(s)
evaluated_jurisdiction(s)
evaluated_relationship
evaluated_policy_profile/version
applicability_clause matched
created_at
```

Policy/rule changes do not rewrite historical application truth.

---

## 25. Re-evaluation when role/scope/relationship changes

Examples:

- Mechanic later gains road-test scope.
- Driver changes local-only -> cross-border.
- Dispatcher gains Safety role.
- Company Driver becomes owner-operator.

Re-evaluation must:

1. calculate newly applicable requirements;
2. reuse valid compatible evidence where permitted;
3. preserve old instances/history;
4. mark no-longer-applicable instances rather than delete them;
5. recalculate gates;
6. require admin confirmation where a changed role/scope affects employment/operational authorization.

Never create a duplicate Person merely because role/scope changes.

---

## 26. Multiple roles

People may hold multiple PersonRoles.

Effective requirements are the union of applicable requirements across active roles/scopes, evaluated through the rule engine.

Do not ask for the same evidence twice when one verified evidence item validly satisfies multiple active requirement instances.

History still retains the distinct instances and definition versions that existed.

---

## 27. Applicant answer -> applicability flow

Applicant answers can affect requirement selection, but only through declared derivation rules.

Conceptually:

```text
answer
  -> derivation rule
  -> provisional scope/fact
  -> requirement re-evaluation
```

Examples:

```text
"Will you road-test repaired trucks?" = Yes
  -> provisional ROAD_TESTS_COMMERCIAL_VEHICLES

"Will your assigned work include U.S. cross-border trips?"
  -> normally admin/job-assignment driven
  -> applicant answer can confirm/flag conflict, not silently redefine offered work

"Are you legally entitled to work in Canada?" = No/needs review
  -> work-authorization verification workflow
  -> does not automatically set a Driver scope
```

Derivation rules must be explicit/versioned. Do not hide business logic inside React conditionals.

---

## 28. Applicant UX

The applicant experiences one coherent application:

```text
Welcome
  -> common identity/contact
  -> applicable common requirements
  -> role/scope sections
  -> requested documents/evidence
  -> review & submit
```

Rules:

- hide irrelevant sections;
- explain conditional requests when useful;
- distinguish optional vs requested vs blocking-at-later-stage;
- save/resume safely;
- do not expose internal tag codes;
- keep mobile-first/accessibility behavior;
- use admin request flow for sensitive evidence not needed at initial submission.

---

## 29. Admin UX

Recommended grouping:

```text
Common / Person
Role-specific
Scope-specific
Employment / pay setup
Documents / evidence
Eligibility / gates
```

For each requirement show:

- name;
- why it applies / matched clause;
- authority class;
- status;
- linked evidence;
- expiry;
- verifier;
- blocking stage;
- allowed actions.

Waive appears only when permitted by the definition and user permission.

---

## 30. Eligibility outputs

Examples:

```text
PERSON_APPROVED
WORK_AUTHORIZED
WORK_START_READY
COMPANY_VEHICLE_ELIGIBLE
COMMERCIAL_DRIVER_ELIGIBLE
DISPATCH_ELIGIBLE
CROSS_BORDER_ELIGIBLE
SAFETY_SENSITIVE_CLEARED
```

These are derived operational capabilities, not document fields.

A Person may be approved but not yet dispatchable or cross-border eligible.

---

## 31. Seed matrix: illustration only

This matrix is a human-readable cross-check, **not** the rule-storage format.

Any cell that says `Scope`, `Policy`, `Jurisdiction`, `Conditional`, or similar must be implemented as an actual requirement definition with applicability clauses. Do not encode this table itself as business logic.

| Requirement / section | DRIVER | DISPATCHER | MECHANIC | SAFETY | HR | PAYROLL | OFFICE_ADMIN | OTHER |
|---|---|---|---|---|---|---|---|---|
| Contact / mailing information | Common | Common | Common | Common | Common | Common | Common | Common |
| Emergency contact | Common | Common | Common | Common | Common | Common | Common | Common |
| Legally entitled to work in Canada? | Common | Common | Common | Common | Common | Common | Common | Common |
| Work-authorization evidence | Conditional/admin request | Same | Same | Same | Same | Same | Same | Same |
| Employment/contract acknowledgements | Relationship/stage | Same | Same | Same | Same | Same | Same | Same |
| OHSA awareness where applicable | Jurisdiction/stage | Same | Same | Same | Same | Same | Same | Same |
| Banking / payroll / tax | Relationship/stage | Same | Same | Same | Same | Same | Same | Configurable |
| Driver's licence | Yes | Scope | Road-test/scope | Scope | Scope | Scope | Scope | Scope |
| Driving abstract / MVR | Policy/scope | Policy/scope | Road-test/scope | Policy/scope | Policy/scope | Policy/scope | Policy/scope | Policy/scope |
| Commercial DL details | Yes | No | Scope | Scope | No | No | No | Scope |
| Driver equipment experience | Yes | No | Mechanic experience instead | No | No | No | No | Role-specific |
| Commercial-driver medical | Role/scope/jurisdiction | No | Scope only if actual commercial-driving duty | Scope | No | No | No | Scope |
| Drug/alcohol/safety-sensitive program | Scope/jurisdiction | Scope | Scope | Scope | Scope if designated | Scope if designated | Scope if designated | Scope |
| Cross-border requirements | Scope | Scope if job requires | Scope if job requires | Scope | No | No | No | Scope |
| Dispatch experience | No | Yes | No | Crossover scope | No | No | No | Role-specific |
| Mechanic licences/certifications | No | No | Yes | No | No | No | No | Role-specific |
| Safety/compliance credentials | No | Policy/scope | No | Yes | No | No | No | Role-specific |
| Work history/references | Specialized Driver variant | Yes | Yes | Yes | Yes | Yes | Yes | Configurable |

---

## 32. Security and privacy

Particularly sensitive data includes:

- SIN
- banking information
- immigration/work-authorization evidence
- background-check results
- medical/compliance evidence

Design expectations:

- RBAC by data category/job function;
- no sensitive values in normal logs;
- mask/redact in broad People views;
- audit sensitive view/download/change actions where appropriate;
- preserve superseded evidence/history instead of casual deletion;
- do not expose payroll/immigration data merely because someone can view Driver operations.

---

## 33. Known anti-patterns to prevent

1. Do not combine government/work eligibility with driver's licence.
2. Do not combine MVR with medical/drug testing.
3. Do not make cross-border a role.
4. Do not make owner-operator a role.
5. Do not equate FAST with legal border eligibility.
6. Do not use `USDOT_MEDICAL` as the generic Canadian/U.S. commercial medical requirement code.
7. Do not treat Driver regulated work history as generic references.
8. Do not promote credential-derived facts into generic People contact fields.
9. Do not require every applicable item at application submission.
10. Do not infer compliance from document upload alone.
11. Do not scatter `if role == ...` logic across frontend/backend.
12. Do not delete history when role/scope/policy/evidence changes.
13. Do not leave tag-combination semantics implicit.
14. Do not let applicant answers silently override admin-approved work scope.
15. Do not show Waive for non-waivable requirements.
16. Do not postpone expiry data modeling until notification work.

---

## 34. Phase A must lock these five artifacts first

Before schema implementation begins, Phase A must produce/confirm these contracts against the live/current repo:

### A. Applicability/DNF contract

- exact clause structure;
- AND/OR semantics;
- role/scope/jurisdiction/relationship predicate representation;
- policy profile/version input;
- deterministic evaluation examples.

### B. Evidence satisfaction contract

- evidence item model;
- many-to-many evidence-to-requirement satisfaction join;
- compatibility/reuse rules;
- verification ownership;
- supersession/expiry behavior.

### C. Gate dependency contract

- persisted/derived gate representation;
- dependency graph;
- role-aware gates such as Driver dispatch vs Dispatcher work eligibility;
- invalidation when requirements expire/change.

### D. Scope determination contract

- admin-assigned vs applicant-derived vs policy/system-derived scope;
- precedence;
- mid-application changes;
- audit and re-evaluation behavior.

### E. Authority/waiver contract

- `authority_class`;
- `authority_reference`;
- `waivable`;
- `waivable_by`;
- waiver reason/audit requirements.

Phase A is complete only when these are explicit enough that the migration/schema work is translation rather than another design debate.

---

## 35. Recommended implementation sequence

### Phase A — foundation report / schema lock

Audit current:

- `PersonApplication`
- `Person`
- `PersonRole`
- role profiles/extensions
- current documents/evidence
- document-request/resume flow
- admin review
- approval/promotion mapping
- application-type gates

Then propose the minimum schema for:

- requirement definitions + versions;
- DNF applicability clauses;
- requirement instances;
- scope assignments/source;
- evidence items;
- evidence satisfaction join;
- verification/status;
- expiry fields;
- gate dependencies/state;
- authority/waiver policy.

### Phase B — common onboarding contract

Move common Person/contact/work-eligibility concepts behind the shared onboarding contract.

### Phase C — Driver as first complete consumer

Use Driver as the first full rule set without making the engine Driver-shaped.

### Phase D — Dispatcher / Mechanic / Safety

Add their definitions through the same engine.

### Phase E — HR / Payroll / Office Admin / Other

Add remaining role and relationship definitions.

### Phase F — renewal monitoring / notifications

Build expiry reminders/automation on top of expiry data that already exists from Phase A.

---

## 36. Acceptance tests for the architecture

The design is working only if these scenarios can be expressed without adding a new hard-coded form branch:

1. Company Driver, Ontario, local-only.
2. Company Driver, Ontario, cross-border U.S.
3. Owner-Operator Driver, Ontario, cross-border U.S.
4. Dispatcher who never drives.
5. Dispatcher later authorized to operate a company vehicle.
6. Mechanic who does not road-test.
7. Mechanic who road-tests commercial vehicles.
8. Safety employee handling cross-border compliance but not driving.
9. Office Admin with no driving responsibility.
10. Office Admin later authorized to use a company vehicle.
11. One Person with Dispatcher + Safety roles.
12. Temporary work authorization with expiry and admin-requested evidence.
13. Applicant whose contact address differs from driver's-licence address.
14. Existing Person gaining a new role without a duplicate Person record.
15. Requirement definition changes after an older application was approved while old history remains intact.
16. One evidence item validly satisfying requirement instances created by two active roles.
17. Same requirement code across two versions preserving history while showing one current effective checklist item.
18. Applicant answer creates provisional road-test scope, then admin rejects that scope and requirements recalculate without deleting history.
19. Non-waivable regulatory requirement never exposes Waive.
20. Evidence expires before Phase F notifications exist and the related operational gate becomes invalid.

---

## 37. Reference notes for rule authors

These references ground future requirement-definition review; they are not substitutes for legal/compliance review before labeling a rule mandatory.

- Ontario OHSA worker awareness guidance / O. Reg. 297/13: https://www.ontario.ca/document/guide-occupational-health-and-safety-act-requirements-basic-awareness-training/worker and https://www.ontario.ca/laws/regulation/130297
- CRA TD1 Ontario: https://www.canada.ca/en/revenue-agency/services/forms-publications/td1-personal-tax-credits-returns/td1-forms-pay-received-on-january-1-later/td1on.html
- Service Canada temporary-resident SIN guidance: https://www.canada.ca/en/employment-social-development/services/sin/temporary-residents.html
- IRCC maintained-status/work-permit extension guidance: https://www.canada.ca/en/immigration-refugees-citizenship/services/work-canada/extend/expired-permit.html
- FMCSA U.S./Canada CDL reciprocity: https://www.fmcsa.dot.gov/international-programs/reciprocity-and-recognition-united-states-and-canadian-commercial-drivers
- FMCSA Canadian cross-border medical qualification guidance: https://www.fmcsa.dot.gov/international-programs/medical-qualification-requirements
- CBSA FAST: https://www.cbsa-asfc.gc.ca/prog/fast-expres/menu-eng.html

Note: external U.S. references may use terms such as DOT/USDOT medical. TruckERP's generic requirement code remains `COMMERCIAL_DRIVER_MEDICAL_QUALIFICATION` unless a truly U.S.-specific requirement is intentionally modeled.

---

## 38. Locked architecture summary

```text
ONE ONBOARDING ENGINE

Person/common data
  + Role(s)
  + Work scope(s)
  + Jurisdiction(s)
  + Employment/business relationship
  + Policy profile/version
        |
        v
Explicit DNF applicability evaluation
        |
        v
Requirement instances (frozen/versioned)
        |
        +-> questions/data
        +-> acknowledgements
        +-> admin-requestable evidence
        +-> evidence satisfaction links
        +-> verification
        +-> expiry
        +-> waiver where lawful/allowed
        |
        v
Gate dependency engine
        |
        +-> Person approved
        +-> Work authorized
        +-> Work-start ready
        +-> Company-vehicle eligible
        +-> Commercial-driver eligible
        +-> Dispatch eligible
        +-> Cross-border eligible
        +-> Safety-sensitive cleared
```

The goal is not to make every role use the Driver form. The goal is to make every person use the same onboarding **engine**, with explicit, versioned, auditable requirements selected by role, scope, jurisdiction, relationship, policy, and lifecycle stage.
