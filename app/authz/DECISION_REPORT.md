# Casbin permission decision report

Simulated role-gate comparison for owner review. This is not a live HTTP test,
and it does not change authentication, entitlements, or route behavior.

Each cell is `existing role gate → prospective Casbin (status)`.
The existing side assumes each listed entitlement name is granted.
The entitlement column is a display string. It is not itself an entitlement name.
A missing subscription can still deny the live route.
`pending` means owner approval is required. It is not a denial of current admin access.
`OPERATIONAL_FULL_ACCESS` is not a stored invite role.
`TENANT_MEMBER (READ_ONLY)` is the stored membership for a READ_ONLY invite.
READ_ONLY is not a separate role and not a Casbin subject.
Every cell simulates platform and tenant-local membership resolution.
Those results are simulations, not live requests.
`NO_EXPLICIT_ROLE_GATE` means no explicit membership role gate was found.
The existing decision stays UNKNOWN. Other protections may still apply.
The label is not evidence that a route is universally accessible.

## Unresolved decisions

1. **Operational access versus tenant administration.** FULL_ACCESS invites still store TENANT_ADMIN. OPERATIONAL_FULL_ACCESS is simulated only. Live admin gates deny it where the prospective policy would allow: people.directory/manage, people.driver_documents/manage, people.driver_profile/manage.
2. **People and Payroll sensitive reads.** These reads stay pending and are not approved denials. Current admin role gates that remain allow: people.audit/view, people.compensation/view, people.directory/view, people.role_configuration/view. All pending reads: payroll.documents/view, payroll.entries/view, payroll.periods/view, payroll.profiles/view, payroll.runs/view, payroll.settlement/view, people.audit/view, people.compensation/view, people.directory/view, people.driver_documents/view, people.drivers/view, people.role_configuration/view.
3. **Existing ungated operational routes.** No live role gate exists, so the existing side stays UNKNOWN rather than allow. Risk label NO_EXPLICIT_ROLE_GATE. Other protections may still apply. This is not evidence that the routes are universally accessible. Capabilities: assets.fleet/view, assets.trailers/manage, assets.trailers/view, assets.trucks/manage, assets.trucks/view, dispatch.board/view, loads.custody/view, loads.documents/confirm, loads.documents/parse, loads.notes/create, loads.notes/view, loads.records/create, loads.records/mark_ready, loads.records/update, loads.records/view, payroll.documents/view, payroll.entries/manage, payroll.entries/view, payroll.periods/update, payroll.periods/view, payroll.profiles/manage, payroll.profiles/view, payroll.runs/view, payroll.settlement/view, people.drivers/manage, people.drivers/view, tolls.imports/manage, tolls.manual/manage, tolls.records/view, tolls.review/manage, trips.assignment/manage, trips.custody/transition, trips.execution/signal, trips.membership/manage, trips.records/cancel, trips.records/complete, trips.records/create, trips.records/view, trips.schedule/manage.
4. **Mixed route-level decisions.** No capability currently has routes with different simulated outcomes.
5. **Unmapped modules.** Not in the capability catalog: brokers (/api/v1/brokers), customs_brokers (/api/v1/customs-brokers), terminals (/api/v1/terminals), load_lab (/api/v1/load-lab), email_intake (/api/v1/email-threads).
6. **Load Integrity I5 hard deletion.** DELETE /api/v1/loads/{load_id} does not physically delete an existing Load on current main. The Load service returns 409 LOAD_PHYSICAL_DELETE_TEMPORARILY_DISABLED. Casbin has no delete grant. The domain policy remains unresolved.

## Ungated writes

Risk label `NO_EXPLICIT_ROLE_GATE`.
These write routes have no explicit membership role gate in the simulation.
The existing decision stays UNKNOWN.
Authentication, tenant isolation, entitlements, or domain rules may still apply.
This list is not evidence that the routes are universally accessible.

- PATCH /api/v1/drivers/{driver_id} (people.drivers/manage)
- PATCH /api/v1/loads/{load_id} (loads.records/update)
- PATCH /api/v1/payroll/pay-entries/{entry_id} (payroll.entries/manage)
- PATCH /api/v1/payroll/pay-periods/{pay_period_id} (payroll.periods/update)
- PATCH /api/v1/payroll/pay-profiles/{profile_id} (payroll.profiles/manage)
- PATCH /api/v1/tolls/manual-entry/stages/{stage_id} (tolls.manual/manage)
- PATCH /api/v1/tolls/pdf-reviews/{batch_id}/rows/{row_id} (tolls.review/manage)
- PATCH /api/v1/trailers/{trailer_id} (assets.trailers/manage)
- PATCH /api/v1/trucks/{truck_id} (assets.trucks/manage)
- POST /api/v1/drivers (people.drivers/manage)
- POST /api/v1/loads (loads.records/create)
- POST /api/v1/loads/parse-document (loads.documents/parse)
- POST /api/v1/loads/{load_id}/confirm-document-snapshot (loads.documents/confirm)
- POST /api/v1/loads/{load_id}/mark-ready (loads.records/mark_ready)
- POST /api/v1/loads/{load_id}/notes (loads.notes/create)
- POST /api/v1/payroll/pay-entries (payroll.entries/manage)
- POST /api/v1/payroll/pay-entries/{entry_id}/void (payroll.entries/manage)
- POST /api/v1/payroll/pay-profiles (payroll.profiles/manage)
- POST /api/v1/payroll/pay-profiles/{profile_id}/deactivate (payroll.profiles/manage)
- POST /api/v1/tolls/files/csv (tolls.imports/manage)
- POST /api/v1/tolls/files/pdf (tolls.imports/manage)
- POST /api/v1/tolls/files/upload (tolls.imports/manage)
- POST /api/v1/tolls/manual-entry/stages (tolls.manual/manage)
- POST /api/v1/tolls/manual-entry/stages/{stage_id}/discard (tolls.manual/manage)
- POST /api/v1/tolls/manual-entry/stages/{stage_id}/process (tolls.manual/manage)
- POST /api/v1/tolls/manual-entry/stages/{stage_id}/validate (tolls.manual/manage)
- POST /api/v1/tolls/pdf-reviews/{batch_id}/process (tolls.review/manage)
- POST /api/v1/trailers (assets.trailers/manage)
- POST /api/v1/trips (trips.records/create)
- POST /api/v1/trips/{trip_id}/cancel (trips.records/cancel)
- POST /api/v1/trips/{trip_id}/complete (trips.records/complete)
- POST /api/v1/trips/{trip_id}/execution-signal (trips.execution/signal)
- POST /api/v1/trips/{trip_id}/loads (trips.membership/manage)
- POST /api/v1/trips/{trip_id}/loads/{load_id}/accept-custody (trips.custody/transition)
- POST /api/v1/trips/{trip_id}/loads/{load_id}/activate (trips.membership/manage)
- POST /api/v1/trips/{trip_id}/loads/{load_id}/complete (trips.membership/manage)
- POST /api/v1/trips/{trip_id}/loads/{load_id}/remove (trips.membership/manage)
- POST /api/v1/trips/{trip_id}/loads/{load_id}/take-custody (trips.custody/transition)
- POST /api/v1/trips/{trip_id}/loads/{load_id}/yard-handoff (trips.custody/transition)
- POST /api/v1/trucks (assets.trucks/manage)
- PUT /api/v1/trips/{trip_id}/assignment (trips.assignment/manage)
- PUT /api/v1/trips/{trip_id}/schedule (trips.schedule/manage)

## Matrix

### admin

| Capability | Contract | Entitlement | Approval | Admin roles | Operational | TENANT_MEMBER (READ_ONLY) |
|---|---|---|---|---|---|---|
| tenant.admin/access | admin | none | no | allow → allow (match) | deny → deny (match) | deny → deny (match) |
| tenant.full_access/access | full_access_same_as_admin | none | no | allow → allow (match) | deny → deny (match) | deny → deny (match) |
| tenant.users/list | member | admin_sensitive | no | allow → allow (match) | allow → allow (match) | allow → allow (match) |
| tenant.users/invite | full_access_same_as_admin | admin_sensitive | no | allow → allow (match) | deny → deny (match) | deny → deny (match) |
| tenant.users/suspend | full_access_same_as_admin | admin_sensitive | no | allow → allow (match) | deny → deny (match) | deny → deny (match) |
| tenant.users/reactivate | full_access_same_as_admin | admin_sensitive | no | allow → allow (match) | deny → deny (match) | deny → deny (match) |
| tenant.users/resend_invite | full_access_same_as_admin | admin_sensitive | no | allow → allow (match) | deny → deny (match) | deny → deny (match) |
| tenant.users/remove | full_access_same_as_admin | admin_sensitive | no | allow → allow (match) | deny → deny (match) | deny → deny (match) |
| tenant.users/unlock_sign_in | full_access_same_as_admin | admin_sensitive | no | allow → allow (match) | deny → deny (match) | deny → deny (match) |
| tenant.signin_security/view | member | admin_sensitive | no | allow → allow (match) | allow → allow (match) | allow → allow (match) |
| tenant.company/view | admin | admin_sensitive | no | allow → allow (match) | deny → deny (match) | deny → deny (match) |
| tenant.company/manage | admin | admin_sensitive | no | allow → allow (match) | deny → deny (match) | deny → deny (match) |
| tenant.broker_intake/view | admin | admin_sensitive | no | allow → allow (match) | deny → deny (match) | deny → deny (match) |
| tenant.broker_intake/manage | admin | admin_sensitive | no | allow → allow (match) | deny → deny (match) | deny → deny (match) |

### fuel

| Capability | Contract | Entitlement | Approval | Admin roles | Operational | TENANT_MEMBER (READ_ONLY) |
|---|---|---|---|---|---|---|
| fuel.providers/view | admin | admin_sensitive | no | allow → allow (match) | deny → deny (match) | deny → deny (match) |
| fuel.providers/manage | admin | admin_sensitive | no | allow → allow (match) | deny → deny (match) | deny → deny (match) |
| fuel.providers/test_connection | admin | admin_sensitive | no | allow → allow (match) | deny → deny (match) | deny → deny (match) |
| fuel.providers/sync | admin | admin_sensitive | no | allow → allow (match) | deny → deny (match) | deny → deny (match) |
| fuel.review/view | admin | admin_sensitive | no | allow → allow (match) | deny → deny (match) | deny → deny (match) |
| fuel.review/manage | admin | admin_sensitive | no | allow → allow (match) | deny → deny (match) | deny → deny (match) |
| fuel.reconciliation/view | admin | admin_sensitive | no | allow → allow (match) | deny → deny (match) | deny → deny (match) |
| fuel.reconciliation/run | admin | admin_sensitive | no | allow → allow (match) | deny → deny (match) | deny → deny (match) |

### loads

| Capability | Contract | Entitlement | Approval | Admin roles | Operational | TENANT_MEMBER (READ_ONLY) |
|---|---|---|---|---|---|---|
| loads.records/view | ungated | none | no | unknown → allow (unknown) | unknown → allow (unknown) | unknown → allow (unknown) |
| loads.records/create | ungated | none | no | unknown → allow (unknown) | unknown → allow (unknown) | unknown → deny (unknown) |
| loads.records/update | ungated | none | no | unknown → allow (unknown) | unknown → allow (unknown) | unknown → deny (unknown) |
| loads.records/mark_ready | ungated | none | no | unknown → allow (unknown) | unknown → allow (unknown) | unknown → deny (unknown) |
| loads.documents/parse | ungated | none | no | unknown → allow (unknown) | unknown → allow (unknown) | unknown → deny (unknown) |
| loads.documents/confirm | ungated | none | no | unknown → allow (unknown) | unknown → allow (unknown) | unknown → deny (unknown) |
| loads.custody/view | ungated | none | no | unknown → allow (unknown) | unknown → allow (unknown) | unknown → allow (unknown) |
| loads.notes/view | ungated | none | no | unknown → allow (unknown) | unknown → allow (unknown) | unknown → allow (unknown) |
| loads.notes/create | ungated | none | no | unknown → allow (unknown) | unknown → allow (unknown) | unknown → deny (unknown) |

### dispatch

| Capability | Contract | Entitlement | Approval | Admin roles | Operational | TENANT_MEMBER (READ_ONLY) |
|---|---|---|---|---|---|---|
| trips.records/view | ungated | none | no | unknown → allow (unknown) | unknown → allow (unknown) | unknown → allow (unknown) |
| trips.records/create | ungated | none | no | unknown → allow (unknown) | unknown → allow (unknown) | unknown → deny (unknown) |
| trips.records/cancel | ungated | none | no | unknown → allow (unknown) | unknown → allow (unknown) | unknown → deny (unknown) |
| trips.records/complete | ungated | none | no | unknown → allow (unknown) | unknown → allow (unknown) | unknown → deny (unknown) |
| trips.membership/manage | ungated | none | no | unknown → allow (unknown) | unknown → allow (unknown) | unknown → deny (unknown) |
| trips.assignment/manage | ungated | none | no | unknown → allow (unknown) | unknown → allow (unknown) | unknown → deny (unknown) |
| trips.schedule/manage | ungated | none | no | unknown → allow (unknown) | unknown → allow (unknown) | unknown → deny (unknown) |
| trips.execution/signal | ungated | none | no | unknown → allow (unknown) | unknown → allow (unknown) | unknown → deny (unknown) |
| trips.custody/transition | ungated | none | no | unknown → allow (unknown) | unknown → allow (unknown) | unknown → deny (unknown) |
| dispatch.board/view | ungated | none | no | unknown → allow (unknown) | unknown → allow (unknown) | unknown → allow (unknown) |

### tolls

| Capability | Contract | Entitlement | Approval | Admin roles | Operational | TENANT_MEMBER (READ_ONLY) |
|---|---|---|---|---|---|---|
| tolls.records/view | ungated | admin_sensitive | no | unknown → allow (unknown) | unknown → allow (unknown) | unknown → allow (unknown) |
| tolls.imports/manage | ungated | admin_sensitive | no | unknown → allow (unknown) | unknown → allow (unknown) | unknown → deny (unknown) |
| tolls.review/manage | ungated | admin_sensitive | no | unknown → allow (unknown) | unknown → allow (unknown) | unknown → deny (unknown) |
| tolls.manual/manage | ungated | admin_sensitive | no | unknown → allow (unknown) | unknown → allow (unknown) | unknown → deny (unknown) |

### people

| Capability | Contract | Entitlement | Approval | Admin roles | Operational | TENANT_MEMBER (READ_ONLY) |
|---|---|---|---|---|---|---|
| people.directory/view | admin | admin_sensitive | required | allow → pending (pending) | deny → pending (pending) | deny → pending (pending) |
| people.directory/manage | admin | admin_sensitive | no | allow → allow (match) | deny → allow (disagreement) | deny → deny (match) |
| people.drivers/view | ungated | none | required | unknown → pending (pending) | unknown → pending (pending) | unknown → pending (pending) |
| people.drivers/manage | ungated | none | no | unknown → allow (unknown) | unknown → allow (unknown) | unknown → deny (unknown) |
| people.driver_profile/manage | admin | admin_sensitive | no | allow → allow (match) | deny → allow (disagreement) | deny → deny (match) |
| people.driver_documents/view | member | driver_documents | required | allow → pending (pending) | allow → pending (pending) | allow → pending (pending) |
| people.driver_documents/manage | full_access_same_as_admin | driver_documents | no | allow → allow (match) | deny → allow (disagreement) | deny → deny (match) |
| people.compensation/view | admin | admin_sensitive | required | allow → pending (pending) | deny → pending (pending) | deny → pending (pending) |
| people.compensation/manage | admin | admin_sensitive | no | allow → allow (match) | deny → deny (match) | deny → deny (match) |
| people.role_configuration/view | admin | admin_sensitive | required | allow → pending (pending) | deny → pending (pending) | deny → pending (pending) |
| people.role_configuration/manage | admin | admin_sensitive | no | allow → allow (match) | deny → deny (match) | deny → deny (match) |
| people.audit/view | admin | admin_sensitive | required | allow → pending (pending) | deny → pending (pending) | deny → pending (pending) |

### payroll

| Capability | Contract | Entitlement | Approval | Admin roles | Operational | TENANT_MEMBER (READ_ONLY) |
|---|---|---|---|---|---|---|
| payroll.periods/view | ungated | payroll | required | unknown → pending (pending) | unknown → pending (pending) | unknown → pending (pending) |
| payroll.periods/open_close | admin | payroll | no | allow → allow (match) | deny → deny (match) | deny → deny (match) |
| payroll.periods/update | ungated | payroll | no | unknown → allow (unknown) | unknown → allow (unknown) | unknown → deny (unknown) |
| payroll.profiles/view | ungated | payroll | required | unknown → pending (pending) | unknown → pending (pending) | unknown → pending (pending) |
| payroll.profiles/manage | ungated | payroll | no | unknown → allow (unknown) | unknown → allow (unknown) | unknown → deny (unknown) |
| payroll.entries/view | ungated | payroll | required | unknown → pending (pending) | unknown → pending (pending) | unknown → pending (pending) |
| payroll.entries/manage | ungated | payroll | no | unknown → allow (unknown) | unknown → allow (unknown) | unknown → deny (unknown) |
| payroll.runs/view | ungated | payroll | required | unknown → pending (pending) | unknown → pending (pending) | unknown → pending (pending) |
| payroll.runs/manage | admin | payroll | no | allow → allow (match) | deny → deny (match) | deny → deny (match) |
| payroll.documents/view | ungated | payroll | required | unknown → pending (pending) | unknown → pending (pending) | unknown → pending (pending) |
| payroll.settlement/view | ungated | payroll | required | unknown → pending (pending) | unknown → pending (pending) | unknown → pending (pending) |

### assets

| Capability | Contract | Entitlement | Approval | Admin roles | Operational | TENANT_MEMBER (READ_ONLY) |
|---|---|---|---|---|---|---|
| assets.trucks/view | ungated | none | no | unknown → allow (unknown) | unknown → allow (unknown) | unknown → allow (unknown) |
| assets.trucks/manage | ungated | none | no | unknown → allow (unknown) | unknown → allow (unknown) | unknown → deny (unknown) |
| assets.trailers/view | ungated | none | no | unknown → allow (unknown) | unknown → allow (unknown) | unknown → allow (unknown) |
| assets.trailers/manage | ungated | none | no | unknown → allow (unknown) | unknown → allow (unknown) | unknown → deny (unknown) |
| assets.fleet/view | ungated | none | no | unknown → allow (unknown) | unknown → allow (unknown) | unknown → allow (unknown) |

