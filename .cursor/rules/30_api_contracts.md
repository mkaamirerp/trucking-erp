# API Contracts & FastAPI Patterns (NO SURPRISES)

## Contract
- Do not change request/response fields or status codes silently.
- Any contract change must include: "frontend impact" list.
- Dev-only debug fields must never ship to production responses.
- Prefer small routers, clear schemas, explicit dependencies.
- Return consistent error shapes.## Tenancy
- Tenant routes must enforce tenant resolution (X-Tenant-ID / host subdomain per project).
- Never default tenant_id.