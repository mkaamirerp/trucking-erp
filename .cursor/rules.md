# TruckERP – Cursor Rules (AUTHORITATIVE)

## ROLE
You are assisting on a multi-tenant SaaS ERP for trucking companies.
The system uses strict platform DB vs tenant DB separation.

## ABSOLUTE RULES (DO NOT VIOLATE)
- Never modify Alembic migrations unless explicitly instructed
- Never assume tenant DB == platform DB
- Never mix platform tables into tenant DB
- Never create or edit migrations silently
- Never auto-edit multiple files without confirmation
- Never refactor schemas without explaining impact
- **Config/infra:** Never modify docker-compose.yml, .env*, nginx config, or scripts/start_api_with_ssm.sh without explicit user request; suggest options and ask first (see .cursor/rules/05_config_and_infra_safety.md)
- **Signup/setup/forms:** Strict on input (signup, setup, OCR); permissive on read (lists, dashboards). Never hide data; never weaken validation (see .cursor/rules/25_signup_setup_strict_input_permissive_read.md)
- **Onboarding payload:** Step-1 data stored in platform_onboarding_payloads; Setup page prefill read-only from payload; Complete Setup writes profile once and consumes payload (see .cursor/rules/26_onboarding_payload_flow.md)
- **Database-backed entity fields:** use the TruckERP searchable type-ahead/select standard; one visible entity field, top 10 on focus, live search while typing, selection stores entity ID. Do not use duplicate snapshot fields as normal UI inputs (see .cursor/rules/41_entity_typeahead_fields.md).

## DATABASE RULES
- Platform DB = control plane only (tenants, users, plans, registry)
- Tenant DB = all business data
- Tenant routing must be registry-driven
- Tenant-safe queries only

## ALEMBIC RULES
- Alembic platform uses `alembic/`
- Alembic tenant uses `alembic_tenant/`
- Migrations must be idempotent
- No stamping unless explicitly approved

## EDITING STYLE
- Small changes only
- One concern at a time
- Prefer explanation + diff before edits
- Ask before touching critical files

## DEV / REBUILD (MANDATORY)
- **You must run the rebuild when backend/API changes need to be applied** (same turn when safe). Do not ask the user to run it.
- **Public / production-shaped hosts:** `./scripts/reload_api.sh` or `docker compose -f docker-compose.yml build truckerp-api && docker compose -f docker-compose.yml up -d truckerp-api`. Use **`docker-compose.yml` only** (no overlay compose files).
- **`./scripts/dev-up.sh`** brings up **`docker-compose.yml` only** (prod-shaped stack on a dev machine).
- Exception: if the user said they will handle deployment/restart, you may skip running commands.

## ASSUMED STACK
- FastAPI
- SQLAlchemy
- Alembic (dual-track)
- Docker Compose
- Postgres
- AWS (SSM, EC2)

## COMMUNICATION
- Explain reasoning before proposing changes
- Call out risks explicitly
- Respect anchor points and locked decisions
