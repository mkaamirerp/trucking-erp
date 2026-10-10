# TruckERP — Agent Instructions (AGENTS.md)

## Mission and non-negotiable rule
TruckERP is one proprietary application with a shared core (FastAPI routers/APIs, authentication, tenant isolation, PostgreSQL, React, shared services) and multiple business modules. **A new module must not break existing modules.** Making the assigned feature work is NOT permission to change another module's behavior.

## Scope first — mandatory before editing
1. Read the relevant module documentation, current code, tests, migrations and repository instructions. Respect locked business rules and existing contracts.
2. Record the intended module, allowed files, dependencies, affected APIs/tables, and baseline tests. Inspect callers and consumers, not just the new feature.
3. Work on `main` only, following the repository's existing change controls. Do not deploy, migrate production, or change production configuration without explicit authorization.

## Load / Trip architecture — read before write
Before changing code, schema, APIs, UI, migrations, or business rules that touch **Load**, **Trip**, **TripLoad**, **Dispatch**, Trip Container, Load/Trip Workspace, assignment, `Load.status`, `Trip.status`, trip number, `dispatch_trips`, `active_trip_id`, custody, terminal/yard, handoff, recovery/repower, operational board/planning queue, or payroll/read-models that depend on Load/Trip:

1. Read **`docs/load_trip/MASTER.md`** first (architecture **and** implementation work order).
2. If another document conflicts with that master: **STOP and report**. Do not choose the older or newer file yourself.
3. Do not implement an architecture change until the master has been **owner-approved and updated**.

That file is the **sole** canonical Load/Trip architecture and remediation tracker. Do not reintroduce competing Decision/Phase/index MDs for this domain.

## STOP / REPORT / INVESTIGATE / WAIT
**STOP before making a change** if the task requires, or unexpectedly causes, any of the following outside the approved module scope:
- Changing an existing table, column, foreign key, relationship, constraint, enum, or migration owned by another module.
- Changing shared People/Driver/Asset/Load models, tenant identity, authentication, permissions, or financial schemas.
- Changing shared API routes, request/response schemas, event contracts, common services, framework/router registration behavior, or consumers of an existing interface.
- Altering existing module behavior, financial calculations, reconciliation, posting, historical records, or previously locked rules.
- Modifying another module's files, removing or weakening tests, or introducing a dependency that couples modules.
- Discovering unclear ownership, contradictory requirements, or a failing baseline relevant to the task.

**Before any such edit**, provide a STOP report:
1. The exact proposed files, symbols, schema objects and current versus proposed behavior.
2. Why the new module needs the change, with evidence from existing code.
3. All known callers/consumers and affected modules; search references and migrations.
4. Compatibility risks, including tenant isolation, data integrity, security, financial history, and deployment.
5. At least one alternative that avoids changing the shared contract, if feasible.
6. A specific regression-test, migration/backfill, and rollback plan.
7. An explicit approval request.

**WAIT for user approval.** Do not silently implement the change, bypass this gate through a workaround, or assume that passing new-module tests grants approval. If the task cannot proceed safely, stop with a useful report.

## Module boundaries
- Modules own their internal logic and data; use documented stable interfaces for cross-module interactions.
- Prefer additive, backward-compatible changes; never silently repurpose existing fields or relationships.
- Preserve immutable posted financial history and tenant scoping. Never perform silent money edits.
- A module failure should be contained as far as the architecture allows. Separate routers alone do not guarantee runtime isolation.
- No opportunistic refactors or unrelated cleanup during a feature task.

## Test and release gates
1. Capture baseline status before editing; do not hide pre-existing failures.
2. Test the new module and every affected existing module, including API contracts, shared models, authorization, tenant isolation and database migrations as applicable.
3. For financial modules, test reconciliation, duplicate handling, sign rules, posting, immutable history and rollback/compensation.
4. Inspect the final diff for unexpected cross-module or core changes. If found, STOP and report.
5. Report tests executed, pass/fail/skip counts, untested risks, exact changed files and whether a commit/deployment occurred.
6. Do not claim compatibility without evidence. Never delete, weaken or skip tests just to get a green result.
7. Obtain required approval before production migration/deployment or any protected configuration change.

## Working style
- Investigate first, implement second. Favor the smallest safe change.
- Keep reports concise, precise, and evidence-based.
- When uncertain, ask rather than inventing requirements.
- Follow more specific module docs where they do not weaken these safety gates.
- These instructions apply to new modules, enhancements, bug fixes, refactors, and AI-generated changes alike.
