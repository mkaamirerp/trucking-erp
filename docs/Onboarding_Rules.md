# TruckERP Onboarding Rules

Status: architecture / foundation design

Purpose: define one onboarding engine for every person entering TruckERP while keeping Person data, role, work scope, jurisdiction, employment/business relationship, business/company facts, physical equipment, evidence, verification, payment classification, and operational eligibility separate.

This document is the design source for future onboarding work. It is intentionally broader than Driver onboarding. Driver is the first mature consumer of the engine, not the shape of the engine.

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

The application is the pre-approval working record. `Person` is the canonical approved human/contact identity. Role-specific, business-specific, equipment-specific, payroll-specific, and credential-derived facts must not be collapsed into generic Person fields merely because they were collected during onboarding.

Examples:

- Contact/mailing address -> Person.
- Driver-licence address -> driver credential/profile evidence, not editable People contact address.
- Mechanic certification -> mechanic credential/evidence, not a generic Person field.
- Owner-operator corporation data -> business/company domain, not Person name/address columns.
- Truck VIN/registration/inspection -> Truck asset domain, not Person fields.
- Pay classification -> Payee/compensation domain, not Driver role.

The system must not become a collection of copied forms such as `DriverForm`, `MechanicForm`, and `DispatcherForm` that duplicate common identity/contact fields. It should be one onboarding shell that renders reusable requirement sections according to explicit rules.

---

## 2. Role, application workflow, relationship, pay classification, and scope are different axes

These concepts must remain distinct even when the UI presents them together.

### 2.1 PersonRole = what the person does

Current application/role vocabulary includes:

```text
DRIVER
DISPATCHER
HR
MECHANIC
PAYROLL
SAFETY
OFFICE_ADMIN
OTHER
```

`requested_role_code` is the proposed PersonRole on approval.

Admin may change the requested role during review when the hiring decision differs from the original invitation, but the change must be explicit, audited, and must re-evaluate requirements before final approval.

### 2.2 application_type = which onboarding workflow/track is being used

Current code uses the same list above for `application_type`.

A future **Owner-Operator onboarding track** is valid because it needs Driver requirements plus additional business/equipment/contract review. If introduced, it should be modeled as a workflow/application track such as:

```text
application_type = OWNER_OPERATOR        # future workflow track
requested_role_code = DRIVER            # approved occupation remains Driver
employment_relationship_type = owner_operator
```

This does **not** create an `OWNER_OPERATOR` PersonRole.

The implementation must decide whether this is a new `application_type` value or a Driver application profile/template. The architectural rule is locked: the workflow may be different; the PersonRole remains `DRIVER`.

### 2.3 Driver employment relationship = how the Driver is engaged

TruckERP already implements this concept in `driver_person_extensions.employment_relationship_type`.

Current implemented values are:

```text
company_driver
owner_operator
```

Existing Driver foundation documentation intentionally reserved `contractor` as a possible later value but did not implement it in v1.

Do **not** create a second competing relationship enum for onboarding. Onboarding must seed/reconcile with the existing Driver extension relationship.

### 2.4 Payee.worker_type = payment/settlement classification

TruckERP already has a separate Payee classification:

```text
EMPLOYEE_DRIVER
CONTRACTOR_COMPANY_DRIVER
OWNER_OPERATOR_LEASED_ON
THIRD_PARTY_CARRIER
```

These are real pay/settlement classifications. They are not PersonRoles and must not be silently repurposed as the universal onboarding relationship taxonomy.

Existing behavior already maps Driver relationship into pay classification in compensation setup. Future onboarding work must integrate with that contract rather than inventing parallel worker types.

### 2.5 Work scope = what the person will actually do

Scope is orthogonal to role and relationship.

Examples:

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

A Driver can be:

```text
Role = DRIVER
Relationship = owner_operator
Operating subtype = long_haul
Scope = CROSS_BORDER_US + COMMERCIAL_DRIVER
```

The Driver rules still apply in full. Owner-operator requirements are additive, not a replacement.

---

## 3. The owner-operator principle: union, never switch

Owner-operator status does not replace Driver qualification.

Conceptually:

```text
applicable_requirements(person) =
    common_person_requirements
  UNION role_requirements
  UNION scope_requirements
  UNION jurisdiction_requirements
  UNION relationship_requirements
  UNION business_requirements_when_linked
  UNION asset_requirements_when_linked
```

For an owner-operator Driver:

```text
COMMON PERSON
+ DRIVER ROLE
+ OWNER_OPERATOR RELATIONSHIP
+ OWNER-OPERATOR BUSINESS
+ OWNER-OPERATOR EQUIPMENT
+ CROSS-BORDER / OTHER SCOPES
+ JURISDICTION RULES
```

A company Driver and an owner-operator Driver are both Drivers and are subject to the same applicable Driver/company safety rules. The owner-operator gets **additional** business, insurance, contract, equipment, and settlement requirements.

---

## 4. Applicability is not timing

Every requirement needs two independent answers:

1. **Does this requirement apply?**
2. **At what stage must it be satisfied?**

A requirement can apply to a person without being mandatory on the initial application.

Example:

```text
Work eligibility question
  applies: every hire
  visible: application

Work-authorization evidence
  applies: when verification is needed
  requested by: admin/system rule
  blocking stage: work_start

Owner-operator incorporation document
  applies: owner_operator relationship
  visible: optionally during application
  admin requestable: yes
  blocking stage: business_approved / contract_activation

SIN
  applies: employee/payroll setup
  collected: post-offer/payroll stage
  not an initial recruiting identity field
```

Do not use one global `required=true` or `blocking=true` boolean to represent the whole lifecycle.

---

## 5. Applicability dimensions

Requirements are selected by reusable dimensions, not hard-coded role pages.

### 5.1 Common / universal

Examples:

- legal name/core identity
- contact information
- contact/mailing address
- emergency contact
- legal entitlement to work in Canada question
- common agreements/policies where applicable
- Ontario health-and-safety awareness where applicable

Universal does **not** mean every supporting document is mandatory at application submission.

### 5.2 Role

Examples:

- Driver qualification for `DRIVER`
- dispatch experience for `DISPATCHER`
- mechanic credentials for `MECHANIC`
- safety/compliance credentials for `SAFETY`

### 5.3 Scope

Scope describes the actual work assignment and capabilities required.

A Mechanic can gain road-test requirements without becoming a Driver role. An Office Admin can gain company-vehicle requirements without changing occupational role.

### 5.4 Jurisdiction

Initial useful tags:

```text
CA
ON
US
```

A rule can require Driver + Cross-border U.S. + U.S. jurisdiction.

### 5.5 Employment/business relationship

For Driver, use the existing implemented relationship axis first:

```text
company_driver
owner_operator
```

Do not add `CONTRACTOR`, `EMPLOYEE_OF_CONTRACTED_BUSINESS`, or other new relationship values merely to make onboarding convenient until Phase A proves they are not already represented by existing Driver extension + Payee + carrier/business structures.

### 5.6 Policy profile

Company policy, insurer rules, and customer rules must be explicit inputs, not hidden `if` statements.

### 5.7 Business/entity context

A requirement can attach to a linked business/company rather than the Person.

### 5.8 Asset context

A requirement can attach to a Truck or Trailer rather than the Person.

---

## 6. Applicability rule model: explicit DNF

Applicability must be explicit and deterministic.

Use **disjunctive normal form (DNF)**:

- every requirement contains one or more clauses;
- predicates inside one clause are **AND**;
- clauses are combined with **OR**.

Example:

```text
Requirement: DRIVER_LICENCE

Clause 1:
  role_any = [DRIVER]

OR

Clause 2:
  role_any = [MECHANIC]
  AND scope_all = [ROAD_TESTS_COMMERCIAL_VEHICLES]

OR

Clause 3:
  scope_all = [OPERATES_COMPANY_VEHICLE]
  AND policy_profile requires licence evidence
```

Conceptual clause:

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
  policy_any[]
  business_context_predicates[]
  asset_context_predicates[]
}
```

Do not use ambiguous bare arrays where AND/OR semantics have to be guessed.

---

## 7. Requirement definition contract

Conceptual definition:

```text
onboarding_requirement_definition {
  id
  code
  name
  category
  description
  version
  active

  subject_type              # PERSON | BUSINESS | TRUCK | TRAILER | ASSIGNMENT
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
  blocking_gate

  waivable
  waivable_by[]

  applicant_visible
  admin_visible
}
```

### 7.1 Authority class

Use explicit authority/source classes:

```text
REGULATORY
INSURANCE
CUSTOMER
COMPANY_POLICY
CONTRACTUAL
```

Never label company policy as a legal requirement.

### 7.2 Waiver rules

`WAIVED` is valid only when the requirement definition allows waiver.

- Regulatory requirements default to non-waivable unless a lawful exception is explicitly represented.
- Insurance/customer/company-policy/contractual rules can be waived only when the definition permits it.
- `waivable_by` controls permission.
- Waiver requires reason, actor, timestamp, and audit event.
- UI must not expose Waive when `waivable = false`.

---

## 8. Scope determination: who sets it and when

Some scope facts are known before invitation; others are discovered during onboarding.

### 8.1 Scope sources

```text
ADMIN_ASSIGNED
APPLICANT_ANSWER_DERIVED
SYSTEM_DERIVED
POLICY_DERIVED
```

Store source, actor where applicable, timestamp, and rule/version.

### 8.2 Precedence

Recommended precedence:

1. explicit admin-approved scope;
2. system/policy-derived mandatory scope;
3. applicant-answer-derived provisional scope.

Applicant answers can propose scope but cannot silently override an admin-approved job assignment.

### 8.3 Re-evaluation

Whenever role, scope, relationship, jurisdiction, policy profile, linked business, or linked equipment changes:

1. re-evaluate the requirement set;
2. create newly applicable requirement instances;
3. preserve satisfied reusable evidence;
4. mark no-longer-applicable instances without deleting history;
5. re-evaluate all affected gates;
6. audit the change.

---

## 9. Policy profiles

Use explicit policy/version inputs.

Conceptually:

```text
tenant_policy_profile
  -> requirement definitions / overrides
  -> effective date/version
```

For example, `OPERATES_COMPANY_VEHICLE` is a fact about the assignment. Whether that requires a fresh abstract every 12 months may come from an insurer or company-policy requirement.

Policy changes must not rewrite historical applications. They can create current requirement instances for active People when necessary.

---

## 10. Common Person onboarding data

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

At applicant stage use a neutral question:

> Are you legally entitled to work in Canada?

Do not bundle citizenship, PR status, SIN, immigration evidence, and Driver licence into one `Government ID` field.

---

## 11. Work eligibility, work authorization, identity evidence, and SIN are separate

### 11.1 Work eligibility

Applicant-stage question:

```text
Are you legally entitled to work in Canada?
Yes / No
```

### 11.2 Work-authorization verification

Admin/system-requestable when applicable.

Possible evidence types can include, when appropriate:

- proof of permanent resident status
- work permit
- study permit with work authorization
- maintained-status/extension evidence
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

### 11.3 Identity evidence

Government identity documents are their own evidence category and are not synonymous with immigration/work authorization.

### 11.4 SIN / payroll identity

Keep SIN separate and protect it with stricter RBAC. Collect it at the appropriate payroll/employment stage, not as a generic applicant ID upload.

---

## 12. Address source-of-truth rule

The current address correction establishes a general architectural rule:

```text
Person contact data
  !=
credential/source-document data
```

### Contact/mailing address

- applicant-controlled;
- promoted into People;
- editable as normal Person contact data.

### Driver-licence address

- sourced from accepted DL/PDF417 evidence;
- stored with Driver credential/profile evidence;
- not freely edited through People contact fields;
- changes through controlled DL replacement/update.

`Same as driver licence address` may copy values into contact fields, but the two sources remain distinct.

The same principle applies to future credential-derived facts for other roles.

---

## 13. Driver licence, driving abstract, medical qualification, and safety-sensitive testing are separate requirements

Do not bundle them.

### Driver licence

Can apply through:

- Driver role;
- Mechanic + road-test scope;
- another role + company-vehicle scope.

### Driving abstract / MVR

Separate requirement with its own refresh period, evidence, verification, and insurer/company-policy trigger.

### Commercial-driver medical qualification

Use a neutral code such as:

```text
COMMERCIAL_DRIVER_MEDICAL_QUALIFICATION
```

Do not use `USDOT_MEDICAL` as the universal requirement code. Canadian/U.S. cross-border qualification rules are jurisdiction-specific.

### Drug/alcohol or other safety-sensitive requirements

Trigger from the applicable regulatory/company scope, not simply `role == DRIVER`.

---

## 14. Cross-border is scope, not role

Use a scope such as:

```text
CROSS_BORDER_US
```

Potential requirements include travel/admissibility evidence, cross-border training, and applicable qualification evidence.

### FAST

FAST is a trusted-traveller/commercial-clearance credential. It is not equivalent to legal U.S. admissibility.

Model separately:

```text
CROSS_BORDER_TRAVEL_ELIGIBILITY
FAST_MEMBERSHIP
```

FAST may be optional unless a carrier/customer/lane policy requires it.

---

## 15. Driver work history is not generic work history

Generic employment references and Driver regulated/safety-performance history are different structures.

Shared employer/contact primitives can be reused, but Driver history may require role/jurisdiction-specific lookback, verification, and employer-response evidence.

Do not force the Driver regulatory workflow into the generic HR reference form.

---

## 16. Existing Driver commercial relationship model must be reused

TruckERP already implemented a Driver extension layer.

Current `driver_person_extensions` includes the Driver's operational/commercial setup, including:

```text
employment_relationship_type = company_driver | owner_operator
provides_own_truck
provides_own_trailer
team-related fields
insurance/commercial approval
```

The onboarding requirements engine must not duplicate these as a new Person relationship subsystem.

Desired flow:

```text
Application/admin review
  -> collect/propose Driver commercial relationship
  -> approval/configuration
  -> seed/reconcile driver_person_extensions
```

The Driver remains Role `DRIVER` regardless of whether relationship is `company_driver` or `owner_operator`.

---

## 17. Payee/compensation classification is already a separate domain

Current `WorkerType` values are:

```text
EMPLOYEE_DRIVER
CONTRACTOR_COMPANY_DRIVER
OWNER_OPERATOR_LEASED_ON
THIRD_PARTY_CARRIER
```

Current Payee supports `payee_type = DRIVER | CARRIER` and carries carrier-oriented fields such as MC/DOT/tax identifiers.

Rules:

1. Do not replace `driver_person_extensions.employment_relationship_type` with `Payee.worker_type`.
2. Do not create a duplicate onboarding worker-type enum that shadows `WorkerType`.
3. On approval/configuration, reconcile the Driver relationship with the correct Payee/Compensation setup through an explicit mapping.
4. If a future owner-operator business with multiple Drivers needs a shared payee/carrier record, reuse or extend the existing Payee/carrier concept where appropriate rather than creating an overlapping settlement identity.
5. Phase A must inspect the live Payee model before designing any new Business/payment relationship schema.

Conceptually:

```text
PersonRole DRIVER
    |
    +-> DriverPersonExtension relationship
    |
    +-> Driver operational roster
    |
    +-> Payee / CompensationProfile
           pay classification / settlement
```

These are related, but they are not the same field.

---

## 18. Owner-operator onboarding track

An owner-operator applicant is a Driver plus additional commercial/business requirements.

The UI may offer a dedicated Owner-Operator invitation/application track because the form and admin review are materially richer.

Conceptual invitation:

```text
Application track: Owner-Operator
Requested PersonRole: DRIVER
Driver relationship: owner_operator
```

The Owner-Operator application inherits all applicable Driver requirements and adds the owner-operator layers.

### 18.1 Person/Driver layer

Examples:

- common Person/contact information
- Driver licence/qualification
- Driver history
- abstract/MVR
- medical qualification when applicable
- equipment experience
- work eligibility
- cross-border scope requirements
- policy acknowledgements

### 18.2 Business/company layer

Examples:

- legal company name
- operating name if different
- entity type
- business number
- GST/HST registration where applicable
- company contact/address
- authorized representative
- remittance/payment setup
- insurance evidence
- owner-operator/carrier agreement

### 18.3 Equipment contribution/asset layer

Examples:

- provides own truck?
- provides own trailer?
- truck year/make/model/VIN
- trailer year/make/model/VIN/type
- bill of sale / ownership or lease evidence
- registration
- insurance association
- inspection/compliance evidence

Documents need not all be mandatory at initial submission. Admin can request missing applicable evidence during review using the existing secure document-resume flow.

---

## 19. Business/company is a first-class concept, but do not duplicate existing Payee blindly

The owner-operator use case proves that company information cannot live as loose Person fields.

A company can have:

- one owner/primary representative;
- several Drivers;
- several Trucks/Trailers;
- one contract with the carrier;
- shared insurance/business documents;
- one settlement/payee relationship;
- company-level approval/readiness.

Conceptually the domain needs a business/company identity:

```text
Business / ContractedCarrierEntity
  legal identity
  contacts
  tax/business identifiers
  company documents
  insurance
  contracts
  people affiliations
  equipment affiliations
  settlement/payee link
  approval/readiness
```

**Important existing-system constraint:** TruckERP already has `Payee` with `payee_type = CARRIER` and `WorkerType` values including `THIRD_PARTY_CARRIER` and `OWNER_OPERATOR_LEASED_ON`.

Therefore Phase A must answer:

- Is Payee sufficient as the financial/business identity?
- Does TruckERP need a separate operational `Business` entity linked 1:1 or 1:N to Payee?
- Can company documents/insurance/contracts live on Payee safely, or would that overload a payment-domain object?
- How will multiple Persons and multiple assets link to the same business?

Do **not** introduce a new Business table until this boundary report is complete. But the architecture is locked that business facts are **not Person fields**.

---

## 20. Person-to-business affiliation

A multi-truck owner-operator company introduces a distinction between:

1. the owner/authorized representative; and
2. other Drivers working through that business.

Do not invent a Driver-specific relationship value such as `DRIVER_FOR_OWNER_OPERATOR_COMPANY` until existing Payee/carrier affiliation is audited.

The desired generic concept is an affiliation/link:

```text
Person
  -> affiliation/membership/employment link
  -> Business/Carrier entity
```

Possible semantics later may include owner, officer, authorized representative, employee/driver, contractor, etc.

The exact enum/table is **not locked** yet because current Payee/carrier structures may already cover part of it.

What is locked:

- the Driver remains Role `DRIVER`;
- their Driver qualification is evaluated independently;
- company-level requirements are evaluated once per company where reusable;
- shared company documents must not be uploaded again for every Driver;
- no duplicate Person is created merely because a Driver changes business affiliation.

---

## 21. Equipment experience and physical equipment are different domains

### 21.1 EquipmentExperience = Person/Driver qualification

Examples:

```text
Dry Van: 2 years
Reefer: 4 years
Flatbed: 1 year
```

This belongs to Driver qualification/onboarding and describes what the person knows how to operate.

### 21.2 Truck/Trailer = physical assets

TruckERP already has first-class `trucks` and `trailers` tables with ownership concepts.

Current ownership values include:

```text
company
owner_operator
leased
```

Current ownership linkage is Person-oriented (`owner_person_id`).

The owner-operator company use case may require future business ownership/affiliation because a corporation with five Trucks should not require all assets to be semantically owned by one Person.

Do **not** create a generic duplicate `EquipmentAsset` table over existing Truck/Trailer models. Instead Phase A should report whether Truck/Trailer need an additive business-owner link or generalized owner entity.

Physical asset evidence belongs to the asset lifecycle:

- bill of sale/lease
- registration
- insurance association
- inspection
- permits
- approval/readiness

Driver experience belongs to the Person lifecycle. Never conflate them.

---

## 22. Evidence and requirements are many-to-many

A requirement can be satisfied by multiple evidence items, and one verified evidence item can satisfy multiple compatible requirement instances.

Model conceptually:

```text
evidence_item
  -> evidence_satisfaction
       -> requirement_instance
```

Evidence reuse is allowed only when compatibility checks pass:

- evidence/document type accepted;
- not expired/superseded/rejected;
- verification level sufficient;
- subject identity matches (Person/Business/Truck/Trailer as appropriate);
- jurisdiction/issuer constraints match;
- target requirement definition permits reuse.

Company evidence must be reusable across affiliated Drivers when the requirement subject is the company, without pretending the document belongs to each Driver personally.

Asset evidence must follow the asset, not the currently assigned Driver.

---

## 23. Requirement instances freeze what applied

Requirement definitions are versioned. Requirement instances freeze:

```text
definition_id
definition_version
subject_type
subject_id
trigger context
policy version
blocking gate
authority class
```

Rules:

- historical instances remain distinct across definition versions;
- active checklist dedupe is primarily by stable business requirement `code` and subject;
- evidence may satisfy a newer version only if the newer definition explicitly accepts it;
- a material semantic change should receive a new requirement code rather than silently changing meaning under an old code.

---

## 24. Requirement status is not evidence status

Requirement status examples:

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

Evidence status examples:

```text
UPLOADED
ACTIVE
SUPERSEDED
REJECTED
EXPIRED
```

Uploading a file does not make the requirement verified.

Examples:

- expired DL uploaded -> evidence exists, Driver gate remains blocked;
- insurance certificate uploaded but under review -> business/asset readiness not yet approved;
- FAST card uploaded but optional for the lane -> no blocking effect.

---

## 25. Expiry data belongs in Phase A

Automated renewal alerts can come later. The data cannot.

Phase A must support:

```text
issued_at
expires_at
expiry_source
verified_at
renewal_window_days
status derived from expiry
```

Expiry can invalidate the relevant gate immediately even before reminder automation exists.

---

## 26. Two gate axes: person capability vs business/asset readiness

Do not collapse everything into `approved`.

### 26.1 Person-capability gates

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

Suggested dependencies:

| Gate | Parent dependencies | Additional requirements |
|---|---|---|
| `PERSON_APPROVED` | none | approval-stage common/role requirements |
| `WORK_AUTHORIZED` | none | applicable work-authorization verification |
| `WORK_START_READY` | `PERSON_APPROVED` + `WORK_AUTHORIZED` when applicable | employment setup, agreements, safety orientation |
| `COMPANY_VEHICLE_ELIGIBLE` | `WORK_START_READY` | DL, abstract/MVR, insurer/company policy |
| `COMMERCIAL_DRIVER_ELIGIBLE` | `WORK_START_READY` | commercial Driver qualification |
| `SAFETY_SENSITIVE_CLEARED` | `WORK_START_READY` | applicable testing/clearance |
| `DISPATCH_ELIGIBLE` | for Driver: `COMMERCIAL_DRIVER_ELIGIBLE`; for office Dispatcher: `WORK_START_READY` | role/scope dispatch rules |
| `CROSS_BORDER_ELIGIBLE` | role-appropriate operational gate | border/travel/jurisdiction requirements |

### 26.2 Business/relationship readiness gates

Owner-operator/company relationships add a second axis:

```text
BUSINESS_APPROVED
BUSINESS_INSURANCE_APPROVED
CONTRACT_COMPLETE
OWNER_OPERATOR_SETTLEMENT_READY
```

These gates attach to the business/relationship, not to Driver qualification.

### 26.3 Asset readiness gates

Physical assets have their own readiness:

```text
TRUCK_APPROVED
TRAILER_APPROVED
```

Possible subrequirements include registration, inspection, insurance linkage, permits, ownership/lease evidence, and carrier approval.

### 26.4 Why the separation matters

If a Truck inspection expires:

```text
Driver.COMMERCIAL_DRIVER_ELIGIBLE = true
Truck.TRUCK_APPROVED = false
```

Do not mark the Driver unqualified.

If the Driver licence expires:

```text
Driver.COMMERCIAL_DRIVER_ELIGIBLE = false
Business.BUSINESS_APPROVED = true
Truck.TRUCK_APPROVED = true
```

Do not invalidate the corporation or Truck.

---

## 27. Assignment readiness is the intersection

The final operational question is not merely “Is the Driver dispatchable?” It is whether the proposed combination is valid for this work.

Conceptually:

```text
ASSIGNMENT_READY(
  person,
  business,
  truck,
  trailer,
  trip_scope
)
=
  person capability gates
  AND applicable business/relationship gates
  AND truck readiness
  AND trailer readiness when required
  AND trip-specific scope/jurisdiction gates
```

Example:

```text
Driver qualified                   YES
Cross-border eligible              YES
Owner-operator business approved   YES
Insurance approved                 YES
Contract complete                  YES
Truck approved                     YES
Trailer approved                   YES
--------------------------------------
Assignment ready                   YES
```

Swap in an expired trailer:

```text
Driver qualified                   YES
Business approved                  YES
Truck approved                     YES
Trailer approved                   NO
--------------------------------------
Assignment ready                   NO
```

This fits TruckERP's Trip/Dispatch direction: Driver + Truck + Trailer + Trip scope are evaluated together without corrupting each entity's independent status.

---

## 28. Owner-operator admin review is additive and multi-gate

A company Driver review can primarily focus on Person + Driver qualification.

An Owner-Operator review must show separate blocks:

```text
PERSON
DRIVER QUALIFICATION
OWNER-OPERATOR RELATIONSHIP
BUSINESS / PAYEE-CARRIER
INSURANCE
TRUCK(S)
TRAILER(S)
CONTRACT
SETTLEMENT READINESS
```

Admin decisions may be independent:

```text
Driver qualified?       yes/no
Business approved?      yes/no
Insurance approved?     yes/no
Truck approved?         yes/no per truck
Trailer approved?       yes/no per trailer
Contract complete?      yes/no
Settlement ready?       yes/no
```

Admin should be able to request specific missing evidence from review without requiring every owner-operator document on the first applicant screen.

---

## 29. Multi-truck owner-operator company scenario

The architecture must support a contracted owner-operator company with several assets and several Drivers.

Example:

```text
ABC Transport Inc.
  Business/payee-carrier context
  Company documents
  Insurance
  Contract
  Settlement setup

  People / Drivers
    Driver A
    Driver B
    Driver C

  Assets
    Truck 101
    Truck 102
    Truck 103
    Truck 104
    Truck 105
    Trailer 201
    Trailer 202
```

Rules:

- each Driver is evaluated under Driver rules independently;
- business documents are evaluated once at business level when reusable;
- each Truck/Trailer has its own asset readiness;
- assignment readiness evaluates the chosen Driver + business + Truck + Trailer + trip scope;
- a company insurance lapse can block business/assignment readiness without erasing Driver qualifications;
- changing which Driver operates a Truck does not transfer ownership documents into the Person record.

---

## 30. Owner-operator portal direction

Future Owner-Operator Portal should be business-centered, not merely a Driver-detail skin.

Potential workspace:

```text
Company
  legal/business identity
  contacts
  tax/business registration
  contract
  insurance

People / Drivers
  qualifications
  requirements
  affiliations

Equipment
  trucks
  trailers
  documents
  inspections
  readiness

Financial
  loads
  settlements
  deductions
  fuel
  tolls
  invoices/remittances

Compliance
  expiring business docs
  expiring driver docs
  expiring asset docs
```

This future portal strengthens the rule that Person, Business/Payee, and equipment assets must remain separate domains.

---

## 31. Role modules

The UI renders a common shell plus applicable rule-driven modules.

### DRIVER

Potential modules:

- commercial licence/DL evidence
- Driver history/regulatory prior-employer history
- abstract/MVR
- equipment experience
- commercial medical qualification
- safety-sensitive requirements
- cross-border requirements
- Driver commercial relationship
- team setup

### OWNER-OPERATOR WORKFLOW ADD-ON

Not a PersonRole. Adds to Driver:

- business identity
- owner-operator company documents
- insurance
- contract
- equipment ownership/contribution
- bill of sale/lease evidence
- settlement/payee setup
- business/asset approval gates

### DISPATCHER

- dispatch experience
- TMS/load-board knowledge where required
- HOS/compliance/coercion-policy training where applicable
- border/customs knowledge if scope requires it

### MECHANIC

- mechanic licences/certifications
- trade/specialty experience
- tool/equipment experience
- DL/abstract only when road-test/company-vehicle scope applies
- shop/safety-sensitive rules as applicable

### SAFETY

- compliance qualifications
- HOS knowledge
- audit/recordkeeping competency
- cross-border compliance scope where applicable
- driving evidence only if their actual scope requires driving

### HR / PAYROLL / OFFICE_ADMIN

- role-specific experience/credentials where company policy requires
- appropriate privacy/confidentiality requirements
- common Person/employment setup

### OTHER

Configurable fallback for uncommon roles until a first-class application type is justified. Do not use `OTHER` as a dumping ground for Owner-Operator.

---

## 32. Employment/payroll/tax setup

Do not assume every Person is an employee.

### Employee relationship

Potential post-offer/work-start requirements:

- direct-deposit/banking information
- TD1 federal
- applicable provincial/territorial TD1
- SIN/payroll setup
- employment agreement

### Owner-operator / carrier relationship

Potential requirements:

- legal business identity
- business number/tax registration
- GST/HST where applicable
- remittance/payment banking
- insurance
- owner-operator/carrier agreement
- equipment contribution/ownership evidence
- Payee/CompensationProfile setup

Do not force employee payroll/tax forms onto an owner-operator merely because the PersonRole is `DRIVER`.

---

## 33. Applicant UX

The applicant should experience a coherent application, not the rules engine.

```text
Welcome
  -> common Person/contact
  -> applicable role questions
  -> applicable relationship/business questions
  -> applicable scope questions
  -> requested documents
  -> review & submit
```

Rules:

- hide irrelevant sections;
- explain conditional requests when useful;
- distinguish optional, requested, and blocking-before-stage items;
- save/resume safely;
- do not expose internal tag names;
- use the admin document-request flow for sensitive/supporting documents not needed initially;
- Owner-Operator applicant may enter business and equipment basics up front while admin requests additional evidence later.

---

## 34. Admin UX

Admin review should group requirements by subject and reason:

```text
Person / common
Role-specific
Scope-specific
Relationship
Business/company
Truck(s)
Trailer(s)
Documents/evidence
Eligibility/readiness gates
```

For each requirement show:

- name
- subject
- why it applies
- current state
- evidence
- expiry
- reviewer/verifier
- blocking gate
- actions allowed by policy

Avoid one giant flat checklist.

---

## 35. Existing document-request flow should be reused

TruckERP already has a secure document-resume/request path. The requirements engine should drive it.

Admin can:

- request a specific missing document;
- provide reason/instructions;
- send/reissue secure resume link;
- see missing/provided/verified/expired state;
- accept/reject evidence;
- preserve superseded evidence/history;
- audit request/supply/accept/reject/waive/replace actions.

Do not create one upload subsystem per role.

---

## 36. Multiple roles and changing relationships

People can hold multiple PersonRoles.

The effective requirement set is the union of all applicable definitions, deduplicated by stable requirement code + subject according to the frozen version rules.

Examples:

- Dispatcher + Safety -> both role sets, shared evidence reused.
- Mechanic later gains road-test scope -> driving requirements added.
- Driver moves local -> cross-border -> cross-border requirements added.
- company_driver -> owner_operator -> Driver role remains; business/equipment/contract requirements are added.
- owner_operator -> company_driver -> historical OO evidence is preserved but current OO-specific requirements become not applicable.

Never create a duplicate Person merely because role, scope, or commercial relationship changes.

---

## 37. Seed matrix is illustrative only

A matrix is useful for humans, but it must never become the rules engine.

| Requirement / section | DRIVER | DISPATCHER | MECHANIC | SAFETY | HR | PAYROLL | OFFICE_ADMIN | OTHER |
|---|---|---|---|---|---|---|---|---|
| Contact / mailing | Common | Common | Common | Common | Common | Common | Common | Common |
| Emergency contact | Common | Common | Common | Common | Common | Common | Common | Common |
| Work eligibility question | Common | Common | Common | Common | Common | Common | Common | Common |
| Work-authorization evidence | Request/condition | Same | Same | Same | Same | Same | Same | Same |
| Driver licence | Yes | Scope only | Road-test/scope | Scope only | Scope only | Scope only | Scope only | Scope only |
| Driving abstract/MVR | Driver/policy | Scope/policy | Road-test/policy | Scope/policy | Scope/policy | Scope/policy | Scope/policy | Scope/policy |
| Commercial qualification | Yes | No | Scope only | Scope only | No | No | No | Scope only |
| Driver equipment experience | Yes | No | Mechanic experience instead | No | No | No | No | Role-specific |
| Cross-border requirements | Scope | Scope if job requires | Scope if job requires | Scope | No | No | No | Scope |
| Dispatch experience | No | Yes | No | Crossover scope | No | No | No | Role-specific |
| Mechanic credentials | No | No | Yes | No | No | No | No | Role-specific |
| Safety credentials | No | Policy/scope | No | Yes | No | No | No | Role-specific |

Owner-Operator is an additive Driver workflow/relationship, not a separate PersonRole column in this matrix.

Any matrix cell containing words such as `scope`, `policy`, `conditional`, or `request` must be represented as an actual requirement definition/DNF clause, not encoded as a matrix switch.

---

## 38. Regulatory vs insurer vs customer vs company policy

Every requirement identifies its authority source.

Examples:

```text
REGULATORY
INSURANCE
CUSTOMER
COMPANY_POLICY
CONTRACTUAL
```

This determines waiver behavior, audit wording, and why the requirement appears.

Do not hard-code broad assertions such as “background check is mandatory for all Drivers” unless the active authority/policy definition actually says so.

---

## 39. Security and privacy

Sensitive onboarding information requires least-privilege access.

Examples:

- SIN
- banking
- immigration/work-authorization evidence
- background-check results
- medical/compliance evidence
- business banking/tax identifiers

Expectations:

- RBAC by data category/job function;
- no sensitive values in ordinary logs;
- masking/redaction in broad People/Dispatch views;
- audit view/download/change actions where appropriate;
- retention/supersession rather than casual deletion;
- Driver operations access does not automatically grant payroll/immigration/business-banking access.

---

## 40. Current-system constraints that Phase A must respect

Before creating schema, Phase A must inspect and reconcile these existing models:

```text
PersonApplication
Person
PersonRole
DriverProfile
DriverPersonExtension
Driver operational roster
Payee
CompensationProfile
Truck
Trailer
Person/document models
Document request/resume flow
Trip/Dispatch assignment
```

Known current contracts:

1. `DriverPersonExtension.employment_relationship_type` already implements `company_driver | owner_operator`.
2. `Payee.worker_type` already implements `EMPLOYEE_DRIVER`, `CONTRACTOR_COMPANY_DRIVER`, `OWNER_OPERATOR_LEASED_ON`, `THIRD_PARTY_CARRIER`.
3. `Driver.payee_id` links operational Driver to Payee.
4. Trucks/Trailers already have `ownership_type = company | owner_operator | leased` and `owner_person_id`.
5. Payee supports `CARRIER`, so a carrier/business identity partially exists in the payment domain.
6. These existing structures must be extended/reconciled, not duplicated.

---

## 41. Phase A foundation report: required answers before migration

Phase A must be a report/schema lock first.

It must answer:

### Requirements engine

- definition table(s)
- DNF clause persistence
- requirement instance table
- version freezing
- evidence satisfaction joins
- expiry semantics
- gate state/derivation
- waiver/audit model

### Driver/owner-operator relationship

- how onboarding seeds `driver_person_extensions`
- mapping from relationship to `Payee.worker_type`
- whether a dedicated Owner-Operator application type or Driver workflow profile is cleaner in current code
- how company_driver -> owner_operator conversion works without a duplicate Person

### Business/carrier entity

- whether existing `Payee(type=CARRIER)` can be extended to serve as business root;
- whether a separate Business entity is required and how it links to Payee;
- how multiple Persons affiliate with one business;
- where business documents, insurance, contract, and approval state live.

### Equipment

- how owner-operator company ownership maps onto existing Truck/Trailer `owner_person_id`;
- whether an additive business owner FK/generalized owner reference is required;
- where bill-of-sale/registration/inspection evidence attaches;
- how asset approval is stored.

### Dispatch

- how person gates + business gates + Truck/Trailer readiness combine into `ASSIGNMENT_READY`;
- no current Driver/Trip behavior should be silently changed until this contract is explicit.

No implementation migration should begin until these boundaries are reviewed.

---

## 42. Implementation sequence

### Phase A — foundation report/schema lock

Reconcile the rules engine with existing DriverPersonExtension, Payee, Truck/Trailer, documents, onboarding approval, and Dispatch.

### Phase B — common onboarding contract

Common Person/contact/work-eligibility sections and shared requirement evaluation.

### Phase C — Driver as first complete consumer

Use existing Driver onboarding while moving requirement selection to the engine.

### Phase D — Owner-Operator additive workflow

Layer business, insurance, contract, equipment, and settlement requirements over Driver without changing the Driver role.

### Phase E — Dispatcher / Mechanic / Safety

Add role/scope definitions without copied forms.

### Phase F — HR / Payroll / Office Admin / Other

Complete remaining role modules.

### Phase G — operational gate integration and renewal monitoring

Connect verified/expired requirements to People/Dispatch/business/asset readiness and automate renewal alerts.

---

## 43. Acceptance scenarios

The architecture is accepted only if these scenarios work without introducing a new hard-coded form branch for each case:

1. Company Driver, Ontario, local-only.
2. Company Driver, Ontario, cross-border U.S.
3. Individual Owner-Operator Driver with one Truck.
4. Owner-Operator Driver providing Truck + Trailer.
5. Owner-Operator business with 5 Trucks, multiple Trailers, and 3 Drivers.
6. Business company documents verified once and reused for all affiliated Drivers where applicable.
7. Each affiliated Driver remains independently qualified under Driver rules.
8. Each Truck/Trailer remains independently approved under asset rules.
9. Driver qualified but Truck inspection expired -> Driver capability remains true, assignment blocked.
10. Truck approved but Driver licence expired -> Truck remains approved, assignment blocked.
11. Business insurance expires -> business/assignment readiness fails, Driver qualifications remain intact.
12. Company Driver converts to Owner-Operator without a duplicate Person.
13. Owner-Operator converts to company_driver while historical business evidence remains.
14. Dispatcher who never drives.
15. Dispatcher later gains company-vehicle scope.
16. Mechanic who never road-tests.
17. Mechanic who gains road-test scope.
18. Safety employee handles cross-border compliance but does not drive.
19. Office Admin later authorized to operate a company vehicle.
20. Person holds Dispatcher + Safety roles.
21. Temporary work authorization expires and work-start gate updates.
22. Applicant contact address differs from DL address.
23. Applicant/admin changes scope mid-application and requirements re-evaluate without data loss.
24. Requirement definition changes after approval while old history remains frozen.
25. One valid evidence item satisfies multiple compatible requirement instances.
26. FAST expires but is optional for the assigned lane -> cross-border eligibility follows actual policy rather than a hard-coded FAST rule.
27. Owner-Operator business has approved Driver A and Driver B; Driver A can be paired with Truck 1 and Driver B with Truck 2 without copying company documents into either Person.

---

## 44. Architecture anti-patterns

Do not:

1. build one copied form per role;
2. model Owner-Operator as a replacement for Driver role;
3. create a second Driver employment relationship enum alongside `driver_person_extensions`;
4. use `Payee.worker_type` as if it were the Person role;
5. put business name/HST/company insurance directly on Person as the canonical business model;
6. put Truck VIN/bill of sale/inspection directly on Person;
7. create a duplicate generic Equipment table over Truck/Trailer without a proven need;
8. make FAST synonymous with U.S. admissibility;
9. call every commercial medical requirement `USDOT medical`;
10. bundle MVR with medical/drug testing;
11. bundle SIN/PR/work permit/DL into `Government ID`;
12. use one static `blocking` boolean;
13. treat uploaded evidence as automatically verified;
14. delete historical requirements/evidence on role/scope/relationship changes;
15. let an asset failure erase a Person qualification;
16. let a Person qualification failure erase a Business or asset approval;
17. add `EMPLOYEE_OF_CONTRACTED_BUSINESS` or `DRIVER_FOR_OWNER_OPERATOR_COMPANY` before checking existing Payee/carrier relationships;
18. scatter `if role == ...` logic throughout frontend/backend instead of central requirement evaluation.

---

## 45. Reference notes

These references are architecture grounding only. Compliance/legal owners must confirm exact regulatory triggers before a requirement is labelled legally mandatory.

- Ontario worker health/safety awareness: https://www.ontario.ca/document/guide-occupational-health-and-safety-act-requirements-basic-awareness-training/worker
- Ontario O. Reg. 297/13: https://www.ontario.ca/laws/regulation/130297
- CRA TD1 Ontario: https://www.canada.ca/en/revenue-agency/services/forms-publications/td1-personal-tax-credits-returns/td1-forms-pay-received-on-january-1-later/td1on.html
- Service Canada temporary-resident SIN: https://www.canada.ca/en/employment-social-development/services/sin/temporary-residents.html
- IRCC work-permit extension/maintained status: https://www.canada.ca/en/immigration-refugees-citizenship/services/work-canada/extend/expired-permit.html
- FMCSA U.S./Canada CDL reciprocity: https://www.fmcsa.dot.gov/international-programs/reciprocity-and-recognition-united-states-and-canadian-commercial-drivers
- FMCSA Canadian cross-border medical qualification: https://www.fmcsa.dot.gov/international-programs/medical-qualification-requirements
- CBSA FAST: https://www.cbsa-asfc.gc.ca/prog/fast-expres/menu-eng.html

`USDOT medical` is intentionally **not** the generic TruckERP requirement code. Use `COMMERCIAL_DRIVER_MEDICAL_QUALIFICATION` and let jurisdiction/rule definitions specify required evidence.

---

## 46. Locked architecture summary

```text
ONE ONBOARDING ENGINE

Person/common data
  + PersonRole(s)
  + Work scope(s)
  + Jurisdiction(s)
  + Driver employment relationship (existing DriverPersonExtension)
  + Policy profile
  + linked Business/Payee context where applicable
  + linked Truck/Trailer assets where applicable
        |
        v
Requirement evaluation (DNF)
        |
        +-> questions/data
        +-> acknowledgements
        +-> admin-requestable evidence
        +-> documents/credentials
        +-> verification
        +-> expiry/renewal
        |
        v
Independent readiness axes
        |
        +-> Person capability
        +-> Business/relationship readiness
        +-> Truck/Trailer readiness
        |
        v
Assignment/trip evaluation
        |
        +-> Driver + Business + Truck + Trailer + Trip scope
        +-> ASSIGNMENT_READY
```

For Owner-Operator specifically:

```text
Role = DRIVER                          # always Driver rules
Driver relationship = owner_operator  # existing extension concept
Pay classification = existing Payee/WorkerType mapping
Business/carrier context = shared company-level requirements
Truck/Trailer = existing physical asset records
Owner-Operator workflow = Driver requirements + additive business/equipment/contract requirements
```

The goal is not to make every role use the Driver form. The goal is one onboarding **engine** whose rules compose correctly across People, roles, relationships, businesses, assets, jurisdictions, and operational scope without duplicating existing TruckERP domains.
