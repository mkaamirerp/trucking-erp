# TruckERP Onboarding Rules

Status: architecture / foundation design

Purpose: define one onboarding engine for every person entering TruckERP while keeping common person data, role-specific requirements, work scope, employment relationship, jurisdiction, evidence, and operational eligibility separate.

This document is the design source for future onboarding work. It is intentionally broader than Driver onboarding. Driver is one role using the same onboarding engine.

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
- Driver-licence address -> driver licence / driver profile evidence, not editable People contact address.
- Mechanic certification -> mechanic credential/evidence, not a generic Person field.
- Payroll setup -> payroll/employment setup, not a Driver field.

The system must never become a collection of separate copied forms such as `DriverForm`, `MechanicForm`, `DispatcherForm`, each duplicating identity/contact fields. It should be one common onboarding shell that renders reusable requirement sections according to rules.

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

`application_type` controls the onboarding workflow/form track. `requested_role_code` controls the role assigned on approval. Keep those concepts separate.

Do not make `OWNER_OPERATOR` a Person role merely to change onboarding questions. Owner-operator/company-driver is an employment/business relationship or Driver scope, not the occupation itself.

---

## 3. The important distinction: applicability is not the same as timing

Every onboarding requirement needs two separate answers:

1. **Does this requirement apply to this person?**
2. **At what stage must it be satisfied?**

A requirement can apply to everyone but still not be mandatory on the initial application.

Example:

```text
Work eligibility question
  applies to: every hire
  asked at: application

Work-authorization evidence
  applies to: only when verification is needed
  requested by: admin
  blocking stage: work_start

SIN
  applies to: employee/payroll setup
  collected at: post-offer / payroll setup
  should not be treated as an initial recruiting identity field
```

This prevents the common mistake of using a single `required=true` flag for the entire onboarding lifecycle.

---

## 4. Four applicability dimensions

Requirements are selected by reusable dimensions, not by hard-coded role pages.

### 4.1 Universal/common

Common information or obligations for the applicable workforce population, independent of a specific occupational role.

Examples:

- legal name / core identity
- contact information
- contact/mailing address
- emergency contact
- legal entitlement to work in Canada question
- employment agreement / policies when applicable
- Ontario health-and-safety awareness for workers covered by OHSA

Universal does **not** mean every document must be uploaded on the first application screen.

### 4.2 Role-conditional

Requirements caused by what the person does.

Examples:

- commercial-driver qualifications for Driver
- dispatcher experience for Dispatcher
- 310T / other mechanic credentials for Mechanic
- safety/compliance qualifications for Safety

### 4.3 Scope-conditional

Requirements caused by the actual work scope, even within the same role.

Examples:

- `OPERATES_COMPANY_VEHICLE`
- `ROAD_TESTS_COMMERCIAL_VEHICLES`
- `CROSS_BORDER_US`
- `SAFETY_SENSITIVE`
- `CITY_ONLY`
- `OTR`
- `SUPERVISOR`

A Mechanic who road-tests trucks can require driving evidence without becoming a Driver role. A Dispatcher who never drives should not be asked for a driver's licence merely because a Driver form happens to contain one.

### 4.4 Jurisdiction-conditional

Requirements can depend on the legal/regulatory jurisdiction involved in the person's work.

Initial useful tags:

- `CA`
- `ON`
- `US`

A rule may require a combination, for example:

```text
role_tags = [DRIVER]
scope_tags = [CROSS_BORDER_US]
jurisdiction_tags = [US]
```

Do not encode `if driver then US rule` in frontend code. The jurisdiction is a separate dimension.

---

## 5. Employment/business relationship is another independent dimension

The role answers **what the person does**. The relationship answers **how the person works for the company**.

Examples:

- `COMPANY_EMPLOYEE`
- `PART_TIME_EMPLOYEE`
- `CONTRACTOR`
- `OWNER_OPERATOR`

For Drivers, existing TruckERP concepts such as provides-own-truck / provides-own-trailer remain Driver-specific relationship/equipment attributes. They should not become Person roles.

This distinction matters because the compliance package can remain nearly identical while financial/tax requirements change.

Example:

```text
Role: DRIVER
Scope: CROSS_BORDER_US + OTR
Relationship: COMPANY_EMPLOYEE
  -> employee payroll/tax setup

Role: DRIVER
Scope: CROSS_BORDER_US + OTR
Relationship: OWNER_OPERATOR
  -> business/remittance/insurance/contract setup
```

Both can still require the same driving qualification evidence.

---

## 6. Recommended requirement definition

Do not create one database column for every future checklist item. Define reusable requirement records/configuration.

Conceptual shape:

```text
onboarding_requirement {
  id
  code
  name
  category
  description

  applicability_mode
  role_tags[]
  scope_tags[]
  jurisdiction_tags[]
  relationship_tags[]

  data_type
  document_type
  requires_document
  admin_requestable
  expiry_tracking
  verification_required

  first_visible_stage
  blocking_stage

  applicant_visible
  admin_visible
  active
  version
}
```

The exact persistence design should follow a separate implementation report; this is the contract the implementation must support.

### 6.1 Applicability semantics

A rule should be able to express:

- universal for the relevant workforce population;
- any-of role tags;
- any/all required scope tags as explicitly configured;
- jurisdiction match;
- relationship match;
- combinations of the above.

Avoid magical implicit behavior. A requirement definition should make its trigger inspectable by an admin/developer.

---

## 7. Stages and gates

Use a stage/gate model instead of a single `blocking` boolean.

Recommended stages:

```text
application_draft
application_submit
admin_review
approval
work_start
operational_eligible
dispatch_eligible
cross_border_eligible
```

Examples:

```text
Requirement: contact information
blocking_stage: application_submit

Requirement: requested work authorization document
blocking_stage: work_start

Requirement: required driver qualification
blocking_stage: dispatch_eligible

Requirement: cross-border evidence
blocking_stage: cross_border_eligible
```

A person can therefore exist in People without automatically being eligible to perform every operational task.

---

## 8. Requirement status is not document status

Uploading a document does not make the person eligible.

Track requirement state separately from evidence state.

Conceptual requirement status:

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

Conceptual evidence/document status:

```text
UPLOADED
ACTIVE
SUPERSEDED
REJECTED
EXPIRED
```

Eligibility is derived from the applicable requirement set plus verification/gate rules.

Examples:

- DL uploaded but expired -> requirement not satisfied.
- Work permit uploaded but awaiting review -> evidence exists, work-start gate not yet satisfied.
- FAST card uploaded but FAST is optional for this employee -> no blocking effect.

---

## 9. Common Person onboarding data

These are common Person/contact concepts, not Driver concepts:

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

Do not make citizenship, PR status, SIN, or immigration-document upload a mandatory initial-application identity question merely because the eligibility question is universal.

### Common acknowledgements / setup

Depending on lifecycle and relationship:

- employment/contract agreement
- code of conduct / handbook acknowledgement
- safety-policy acknowledgement
- privacy/confidentiality/NDA where required
- Ontario OHSA awareness completion/verification where applicable
- payroll/banking/tax setup for employee relationships

---

## 10. Work authorization: separate question, verification, and payroll identity

Do not bundle these as `Government ID`.

### 10.1 Work eligibility

Common applicant question:

```text
Are you legally entitled to work in Canada?
Yes / No
```

### 10.2 Work-authorization verification

Admin-controlled/requestable after the appropriate stage.

Possible authorization/evidence types include, when applicable:

- proof of permanent resident status
- work permit
- study permit with work authorization
- maintained-status / extension evidence
- other permitted supporting evidence

Useful fields:

```text
authorization_type
document_id/reference
issued_date
expiry_date
conditions/restrictions
verification_status
verified_at
verified_by
```

Document upload should be requestable, not universally mandatory at initial submission.

### 10.3 SIN / payroll identity

Keep SIN separate from work-authorization documents and collect it at the appropriate payroll/employment stage with stricter access controls.

Temporary-resident SINs beginning with `9` have expiry considerations tied to immigration authorization, so expiry/verification logic must not be reduced to a static text field.

---

## 11. Address source-of-truth rule

The current address correction work establishes an important general rule:

```text
Person contact data
  !=
credential/source-document data
```

### Contact/mailing address

- applicant-controlled
- promoted into People
- editable later as normal Person contact data

### Driver-licence address

- sourced from the accepted licence/PDF417 evidence
- stored with Driver licence/profile evidence
- not freely edited through People contact fields
- changes through controlled replace/update of the licence

A `Same as driver licence address` option may copy the current values into contact fields, but the two sources remain distinct.

The same pattern applies to future role credentials: evidence-derived facts stay with the credential/evidence source rather than silently becoming generic Person fields.

---

## 12. Driver's licence is not universal

Split these concepts:

- work eligibility / identity
- driver's licence
- commercial-driver qualification

A driver's licence is required only when the role/scope requires driving.

Typical trigger examples:

```text
DRIVER -> yes
MECHANIC + ROAD_TESTS_COMMERCIAL_VEHICLES -> yes
OFFICE_ADMIN + OPERATES_COMPANY_VEHICLE -> yes if company policy requires
DISPATCHER -> no unless driving scope is added
```

The licence document can therefore use the same DL capture/PDF417 pipeline where applicable without making the whole onboarding application Driver-shaped.

---

## 13. Driving record / abstract is its own requirement

Do not bundle MVR/driving abstract with medical/drug testing.

A driving record can apply to any scope that involves operating or road-testing company/commercial vehicles.

Possible triggers:

- Driver
- Mechanic with road-test scope
- other role with company-vehicle scope
- company/insurer policy

Its evidence, review cycle, expiry/refresh policy, and gate are separate from medical qualification and drug/alcohol requirements.

---

## 14. Commercial-driver qualification package

Driver-specific requirements can include, depending on jurisdiction/scope/company policy:

- licence class and endorsements
- licence status / expiry
- driving abstract / MVR
- regulatory prior-employer/safety-performance history where applicable
- commercial medical qualification
- drug/alcohol program requirements where applicable
- equipment experience
- safety/compliance acknowledgements
- cross-border eligibility where applicable

Do not treat the Driver work-history section as the same structure as generic office employment history. It can have regulatory lookback/evidence requirements and should be its own requirement/section while still sharing reusable employer/contact primitives.

---

## 15. Cross-border is a scope, not a role

Use a scope such as:

```text
CROSS_BORDER_US
```

Potential requirements selected by that scope may include:

- required travel/admissibility evidence
- company-specific border program requirements
- cross-border training/compliance
- medical/qualification rules applicable to Canadian commercial drivers operating in the U.S.

### FAST

FAST is a trusted-traveller/commercial-clearance program that provides expedited processing/dedicated-lane benefits where conditions are met. Do not make `FAST card = legal cross-border eligibility`.

Model separately:

```text
Cross-border eligible / required travel documentation
FAST membership/card (optional unless carrier/customer/lane policy requires it)
```

Track FAST expiry when present.

### Canadian commercial medical qualification

Do not model the generic requirement as simply `USDOT medical`. Canadian and U.S. commercial-driver qualification rules interact through reciprocity. Use a neutral requirement such as:

```text
COMMERCIAL_DRIVER_MEDICAL_QUALIFICATION
```

and let jurisdiction/scope determine the evidence/rule profile.

---

## 16. Role modules

The UI should render a common shell plus applicable role/scope modules.

### DRIVER

Potential modules:

- commercial licence / DL evidence
- driving history / regulated prior-employer history
- driving abstract/MVR
- equipment experience with years per equipment type
- commercial medical qualification
- safety-sensitive requirements
- cross-border requirements when scope applies
- Driver employment/business relationship
- owner-operator/equipment contribution setup where applicable

### DISPATCHER

Potential modules:

- dispatch experience
- TMS/load-board experience as company-defined requirements
- HOS/compliance/coercion-policy training if company policy/role scope requires it
- border/customs knowledge if scope requires it

Do not show Driver commercial-equipment/medical sections merely because Dispatcher works with drivers.

### MECHANIC

Potential modules:

- mechanic licence/certifications
- trade/specialty experience
- tool/equipment experience
- driver's licence / driving abstract only when road-test/company-vehicle scope applies
- safety-sensitive or shop-specific training when applicable

### SAFETY

Potential modules:

- safety/compliance qualifications
- HOS/compliance training
- audit/recordkeeping competencies
- cross-border compliance knowledge when scope applies
- driving qualification only if the actual scope requires driving

### HR

Potential modules:

- HR experience/credentials as company requires
- privacy/confidentiality acknowledgements
- common employment setup

### PAYROLL

Potential modules:

- payroll/accounting experience as company requires
- confidentiality/privacy requirements
- common employment setup

### OFFICE_ADMIN

Potential modules:

- office/admin experience
- company systems/process training
- driving evidence only when company-vehicle scope applies

### OTHER

`OTHER` is not a dumping ground for owner-operators or known occupations. It is a configurable fallback for uncommon roles until a first-class application type is warranted.

---

## 17. Employment/payroll/tax setup

Do not assume every Person is an employee.

### Employee relationship

Potential post-offer/work-start requirements:

- direct-deposit/banking information
- federal TD1
- provincial/territorial TD1 (e.g. TD1ON for Ontario)
- payroll/SIN setup
- employment agreement

### Contractor / owner-operator relationship

Use a different financial/setup package, for example:

- legal business name
- business entity/type
- business number where applicable
- GST/HST registration where applicable
- remittance/payment banking information
- insurance evidence
- contractor/owner-operator agreement
- truck/trailer/equipment contribution information

Do not force employee TD1/payroll requirements onto an owner-operator merely because both have role `DRIVER`.

---

## 18. Document/evidence model

A requirement may be satisfied by zero, one, or multiple evidence items.

Conceptual evidence link:

```text
requirement_instance
  -> evidence/document(s)
  -> review decision
  -> expiry / renewal
  -> audit history
```

Uploads remain optional unless the evaluated requirement and lifecycle stage make them required.

TruckERP already has a document-request/resume mechanism. The requirements engine should drive that mechanism rather than inventing a separate upload flow for every role.

Admin must be able to:

- request a specific missing document/evidence item;
- provide a reason/instructions;
- reopen the applicant's secure resume link;
- see provided/missing/verified/expired state;
- accept/reject evidence;
- preserve superseded documents/history;
- audit who requested, supplied, accepted, rejected, waived, or replaced evidence.

---

## 19. Requirement instances: freeze what applied

Do not rely only on live requirement definitions after an application has begun.

When requirements are evaluated for an application/person, create/freeze enough of the applicable requirement instance to preserve history.

Reason:

- company policy may change;
- a requirement may be renamed;
- a role/scope may change;
- jurisdiction rules may evolve;
- an old application must still show what was actually requested and approved at that time.

A definition can be versioned while each application requirement records the definition/version that produced it.

---

## 20. Re-evaluation when role or scope changes

Role/scope can change after initial invitation.

Examples:

- Mechanic later receives road-test authorization.
- Driver changes from local-only to cross-border.
- Dispatcher becomes Safety + Dispatcher.
- Company driver becomes owner-operator or vice versa.

Re-evaluation must:

1. calculate newly applicable requirements;
2. preserve already satisfied reusable evidence;
3. mark no-longer-applicable requirements without deleting history;
4. never silently delete documents;
5. recalculate operational gates.

A role/scope change should not require creating a duplicate Person.

---

## 21. Multiple roles

People may hold multiple PersonRoles. Requirement evaluation should operate across the person's active roles/scopes rather than assuming exactly one permanent role.

The effective requirement set is the union of applicable requirements, deduplicated by requirement code/definition according to explicit rules.

Example:

```text
Person roles: DISPATCHER + SAFETY

Common requirements
+ Dispatcher requirements
+ Safety requirements
+ any shared scope requirements
```

Do not ask for the same document twice when one verified evidence item satisfies the same requirement for both roles.

---

## 22. Suggested scope tags

These are starting vocabulary, not a final hard-coded enum list:

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

Add tags because a real requirement needs them, not because they sound useful.

---

## 23. Applicant UX

The applicant should experience one coherent application, not the rules engine.

Desired behavior:

```text
Welcome
  -> common identity/contact
  -> applicable common requirements
  -> role/scope sections
  -> requested documents
  -> review & submit
```

UI rules:

- hide irrelevant sections entirely;
- explain why a conditional item is requested when helpful;
- distinguish optional, requested, and required-before-stage items;
- save/resume safely;
- do not ask the applicant to understand internal tags such as `CROSS_BORDER_US`;
- retain accessible validation and mobile-first behavior;
- use admin-request flow for sensitive/supporting documents that are not needed on initial submission.

---

## 24. Admin UX

The admin should see both the person's data and **why** each requirement applies.

Recommended review grouping:

```text
Common / Person
Role-specific
Scope-specific
Employment / pay setup
Documents / evidence
Eligibility / gates
```

For each requirement show:

- requirement name
- trigger/reason (e.g. Driver + Cross-border US)
- current status
- evidence
- expiry when applicable
- verifier/reviewer
- blocking stage
- actions: request / accept / reject / waive where allowed

Avoid a giant flat checklist with no explanation of why an item exists.

---

## 25. Eligibility outputs

The requirements engine should produce explicit capability/gate outputs rather than one generic `approved` flag.

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

These are operational results of verified requirements, not substitute document fields.

A Person can be approved but not yet `DISPATCH_ELIGIBLE`.

---

## 26. Regulatory vs company-policy requirements

Every requirement should identify its source class:

```text
REGULATORY
INSURANCE
CUSTOMER
COMPANY_POLICY
CONTRACTUAL
```

Where useful, keep a human-readable authority/reference field.

This matters because requirements that look similar can have different authority and waiver rules.

Example:

- statutory safety awareness training
- insurer-requested driving abstract
- company-required FAST membership for certain lanes

Do not describe a company policy as a legal requirement.

---

## 27. Security and privacy

Onboarding will contain highly sensitive personal information. Apply least-privilege access.

Particularly sensitive examples:

- SIN
- banking information
- immigration/work-authorization documents
- background-check results
- medical/compliance evidence

Design expectations:

- RBAC by data category and job function;
- encrypted transport/storage using existing platform controls;
- no sensitive values in normal logs;
- audit view/download/change actions where appropriate;
- redact/mask values in broad People views;
- evidence retention/supersession instead of casual deletion;
- do not expose payroll/immigration data simply because someone can view Driver operations.

---

## 28. Seed requirement matrix

This is a design seed, not a permanent hard-coded matrix. The requirements engine should generate equivalent behavior from triggers.

| Requirement / section | DRIVER | DISPATCHER | MECHANIC | SAFETY | HR | PAYROLL | OFFICE_ADMIN | OTHER |
|---|---|---|---|---|---|---|---|---|
| Contact / mailing information | Common | Common | Common | Common | Common | Common | Common | Common |
| Emergency contact | Common | Common | Common | Common | Common | Common | Common | Common |
| Legally entitled to work in Canada? | Common | Common | Common | Common | Common | Common | Common | Common |
| Work-authorization evidence | Admin/request/condition | Same | Same | Same | Same | Same | Same | Same |
| Employment/contract acknowledgements | Relationship/stage | Same | Same | Same | Same | Same | Same | Same |
| OHSA awareness (where applicable) | Jurisdiction/stage | Same | Same | Same | Same | Same | Same | Same |
| Banking / payroll / tax | Relationship/stage | Same | Same | Same | Same | Same | Same | Configurable |
| Driver's licence | Yes | Scope only | Road-test/scope | Scope only | Scope only | Scope only | Scope only | Scope only |
| Driving abstract / MVR | Yes/policy | Scope/policy | Road-test/scope | Scope/policy | Scope/policy | Scope/policy | Scope/policy | Scope/policy |
| Commercial DL details | Yes | No | Scope only | Scope only | No | No | No | Scope only |
| Driver equipment experience | Yes | No | Mechanic experience instead | No | No | No | No | Role-specific |
| Commercial-driver medical | Driver/scope/jurisdiction | No | No unless actual driving scope requires | Scope only | No | No | No | Scope only |
| Drug/alcohol/safety-sensitive program | Scope/jurisdiction | Scope only | Scope only | Scope only | No unless scope | No unless scope | No unless scope | Scope only |
| Cross-border requirements | Scope only | Scope only if job requires | Scope only if job requires | Scope only | No | No | No | Scope only |
| Dispatch experience | No | Yes | No | Crossover scope | No | No | No | Role-specific |
| Mechanic licences/certifications | No | No | Yes | No | No | No | No | Role-specific |
| Safety/compliance credentials | No | Scope/company policy | No | Yes | No | No | No | Role-specific |
| Generic work history/references | Driver uses specialized variant | Yes | Yes | Yes | Yes | Yes | Yes | Configurable |

The matrix is not a database schema. It is a readable cross-check against requirement definitions.

---

## 29. Important design corrections from current onboarding

Future work must avoid these known failure patterns:

1. **Do not combine government/work eligibility with driver's licence.** Different triggers and lifecycle.
2. **Do not combine MVR with medical/drug testing.** Different triggers, evidence, refresh cycles, and gates.
3. **Do not make cross-border a role.** It is work scope.
4. **Do not make owner-operator a role.** It is a Driver relationship/business arrangement.
5. **Do not equate FAST with legal border eligibility.** FAST is a separate trusted-traveller/commercial-clearance credential.
6. **Do not equate Canadian commercial-driver medical qualification with a generic `USDOT medical` checkbox.** Rules depend on licence class/jurisdiction/reciprocity.
7. **Do not treat Driver work history as generic references.** It can require a specialized regulatory structure.
8. **Do not promote credential-derived facts into generic People contact fields.**
9. **Do not require every applicable item at application submission.** Use stage gates and admin requests.
10. **Do not infer compliance from document upload alone.** Verification and eligibility are separate.
11. **Do not hard-code role branches throughout frontend/backend.** Centralize requirement evaluation.
12. **Do not delete history when requirements, roles, scopes, or evidence change.** Preserve audit/version history.

---

## 30. Recommended implementation sequence

Do not attempt the whole engine in one migration.

### Phase A — foundation report / schema lock

Before implementation, audit current:

- `PersonApplication`
- `Person`
- `PersonRole`
- driver profile/extension
- application files/documents
- document-request/resume flow
- current admin review
- approval/promotion mapping
- current application-type gates

Then propose the minimum tables/contracts for:

- requirement definitions
- requirement instances
- applicability tags/conditions
- evidence links
- verification/status
- stage gates

### Phase B — common onboarding contract

Move common Person/contact/work-eligibility concepts behind a shared onboarding section contract.

### Phase C — Driver requirements as first full rule set

Use the existing Driver flow as the first complete consumer of the requirement engine without making the engine Driver-specific.

### Phase D — Dispatcher / Mechanic / Safety

Add their role-specific definitions using the same engine.

### Phase E — HR / Payroll / Office Admin / Other

Add remaining role-specific and relationship-specific definitions.

### Phase F — operational gates and renewal monitoring

Connect verified/expired requirements to operational eligibility and later expiry notifications.

---

## 31. Acceptance tests for the architecture

The design is working only if these scenarios can be expressed without adding a new hard-coded form branch:

1. Company Driver, Ontario, local-only.
2. Company Driver, Ontario, cross-border U.S.
3. Owner-Operator Driver, Ontario, cross-border U.S.
4. Dispatcher who never drives.
5. Dispatcher who later receives company-vehicle scope.
6. Mechanic who does not road-test.
7. Mechanic who road-tests commercial vehicles.
8. Safety employee handling cross-border compliance but not driving.
9. Office Admin with no driving responsibility.
10. Office Admin later authorized to use a company vehicle.
11. One Person with Dispatcher + Safety roles.
12. Temporary work authorization with expiry and admin-requested evidence.
13. Applicant whose contact address differs from driver's-licence address.
14. Existing Person gaining a new role without a duplicate Person record.
15. A requirement definition changing after an older application was already approved, while old history remains intact.

---

## 32. Reference notes for policy/rule authors

These references are for architecture grounding and future requirement-definition review. They are not a substitute for legal/compliance review before labeling a rule as mandatory.

- Ontario OHSA worker awareness training guidance and O. Reg. 297/13: https://www.ontario.ca/document/guide-occupational-health-and-safety-act-requirements-basic-awareness-training/worker and https://www.ontario.ca/laws/regulation/130297
- CRA TD1 Ontario information: https://www.canada.ca/en/revenue-agency/services/forms-publications/td1-personal-tax-credits-returns/td1-forms-pay-received-on-january-1-later/td1on.html
- Service Canada temporary-resident SIN guidance: https://www.canada.ca/en/employment-social-development/services/sin/temporary-residents.html
- IRCC maintained-status/work-permit extension guidance: https://www.canada.ca/en/immigration-refugees-citizenship/services/work-canada/extend/expired-permit.html
- FMCSA U.S./Canada commercial-driver licence reciprocity: https://www.fmcsa.dot.gov/international-programs/reciprocity-and-recognition-united-states-and-canadian-commercial-drivers
- FMCSA Canadian cross-border medical qualification guidance: https://www.fmcsa.dot.gov/international-programs/medical-qualification-requirements
- CBSA FAST program: https://www.cbsa-asfc.gc.ca/prog/fast-expres/menu-eng.html

---

## 33. Locked architecture summary

```text
ONE ONBOARDING ENGINE

Person/common data
  + Role(s)
  + Work scope(s)
  + Jurisdiction(s)
  + Employment/business relationship
        |
        v
Requirement evaluation
        |
        +-> data/questions
        +-> acknowledgements
        +-> admin-requestable evidence
        +-> documents/credentials
        +-> expiry/renewal
        +-> verification
        |
        v
Stage/eligibility gates
        |
        +-> Person approval
        +-> Work-start readiness
        +-> Company-vehicle eligibility
        +-> Commercial-driver / dispatch eligibility
        +-> Cross-border eligibility
```

The goal is not to make every role use the Driver form. The goal is to make every person use the same onboarding **engine**, with requirements selected by explicit reusable rules.
