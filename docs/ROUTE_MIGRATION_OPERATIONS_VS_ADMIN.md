# Route Migration: Operations vs Admin

**Locked:** 2026-03-15

## Convention

- **Operations** (`/operations/*`, `/dashboard`, `/loads`, `/payroll/*`, `/driver-onboarding`) — Day-to-day execution. Dispatch, loads, review queue, payroll execution.
- **Admin** (`/admin/*`) — Company setup and configuration only. Profile, users, roles, payroll settings, integrations, onboarding settings, document rules.

**Do not add operations pages under `/admin/*`.**

## Migration completed

| Old route | New route |
|-----------|-----------|
| `/admin/driver-onboarding` | `/operations/driver-onboarding-review` |
| `/admin/driver-onboarding/:id` | `/operations/driver-onboarding-review/:id` |

Legacy `/admin/driver-onboarding` and `/admin/driver-onboarding/:id` redirect to the new paths.

## Future Admin Home

`/admin` currently redirects to `/admin/company-profile`. Structure is ready for a true Admin Home:

- Add `<Route index element={<AdminHomePage />} />` (or similar) when built
- Admin Home can show: system health, config completion, missing setup alerts, tiles to Company Profile, Users, etc.

## Route map (current)

### Operations
- `/dashboard`
- `/operations/driver-onboarding-review`
- `/operations/driver-onboarding-review/:id`
- `/driver-onboarding`
- `/loads`, `/loads/:id`
- `/payroll/pay-periods`, `/payroll/pay-runs`, `/payroll/pay-runs/new`, `/payroll/pay-runs/:id`, `/payroll/documents`

### Admin (tenant config)
- `/admin` → redirects to `/admin/company-profile`
- `/admin/company-profile`
- `/admin/users`
- `/admin/roles`
- `/admin/payroll`
- `/admin/integrations/smtp`, `/admin/integrations/eld`, `/admin/integrations/fuel`
- `/admin/onboarding`
- `/admin/documents`
