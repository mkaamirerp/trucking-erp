# 🚛 Trucking ERP Blueprint (Canonical)
**Type:** Multi-tenant SaaS (B2B)  
**Status:** Active blueprint (v1.0)  
**Canonical Rule:** If it’s not in this blueprint or a decision record, it is not considered agreed.

## 1. Purpose
Build an industry-grade Trucking ERP that supports:
- Driver + employee management
- Operations/dispatch + mileage capture
- IFTA compliance automation
- Payroll for company drivers and owner-operators (settlements)
- Document management with storage abstraction and OCR
- Integrations (ELD, maps, accounting, fuel cards)
- Multi-tenant SaaS readiness (phased rollout)

## 2. Target Users
- Small fleets (5–15 trucks)
- Medium fleets (15–100 trucks)
- Large fleets (100+ trucks)

## 3. Key Differentiators
- Multi-tenant platform with tenant-selectable ELD vendors
- Automated IFTA from trip/ELD mileage data
- Correct settlement logic for owner-operators vs company drivers
- Preventive maintenance automation and reminders
- Employee (non-driver) support (future module)

## 4. Architecture Overview
### 4.1 Backend Style
**Modular monolith** (one FastAPI service, one Postgres) with clear module boundaries.
- Fast to build and deploy
- Clean separation by module to allow future split-out if needed

### 4.2 Data Layer
- PostgreSQL (primary system of record)
- Alembic migrations for schema evolution
- Async SQLAlchemy + asyncpg for API
- Autogenerate is “locked down” to avoid schema drift during MVP development

### 4.3 Background Work (Planned)
- Redis + Celery for background tasks:
  - OCR processing
  - ELD sync schedules
  - report generation
  - reminders and notifications

### 4.4 File Storage (Decision-backed)
- Development: local storage
- Production: single S3 bucket with per-tenant prefixes (NOT separate buckets)
- Storage abstraction layer in code
- DB stores storage_key + metadata

## 5. Multi-Tenant Strategy (Phased)
**Target:** Schema-per-tenant in Postgres.
- Platform schema: tenants, users, connectors, subscriptions, audit logs
- Tenant schemas: operational tables (drivers, trips, payroll, etc.)

**Rollout plan:**
- Phase 1 (MVP): single-tenant, single schema (simplest)
- Phase 2: introduce platform schema + tenant middleware
- Phase 3: tenant schema-per-tenant + subdomain routing

## 6. Core Modules
### Module 1: Driver Management (MVP focus)
- Driver identity + contact
- Multiple phones (table)
- Emergency contacts (table)
- License architecture (country-aware, CA/US)
- Documents + OCR pipeline
- Active/inactive soft deactivate

### Module 2: Employee Management (future)
- Non-driver employees (separate model)
- Payroll extension

### Module 3: Equipment Management (future)
- Trucks, trailers, assignments, odometer

### Module 4: Shop & Maintenance (future)
- Preventive maintenance schedules
- Work orders, parts, reminders

### Module 5: Operations & Dispatch (MVP+)
- Trips/loads, driver-truck assignments
- Miles and jurisdiction breakdown

### Module 6: IFTA & Compliance (after ops stable)
- Quarterly reporting
- Miles by jurisdiction
- Fuel purchases (later)
- Audit-ready exports

### Module 7: Payroll & Settlements (after ops stable)
- Company driver payroll rules
- Owner-operator settlements
- Pay periods, statements

### Module 8: Document Management (in-progress)
- Upload, storage, metadata
- OCR extraction as background job

### Module 9: Integrations (future)
- ELD vendors (selectable per tenant)
- Maps for mileage
- Accounting exports
- Fuel/maintenance APIs

### Module 10: Accounting Integration (future)
- Exports and sync (QuickBooks/Xero etc.)

### Module 11: Customer & Load Management (future)
- Customers, contracts, loads, billing

### Module 12: Reporting & Analytics (future)
- Dashboards
- Aggregations and exports
- Timeseries (TimescaleDB optional later)

## 7. Technology Stack (Current + Planned)
**Current**
- Python 3.13 (venv)
- FastAPI + Uvicorn
- SQLAlchemy (async) + asyncpg
- Alembic migrations
- PostgreSQL (Docker container)
- systemd for API process

**Planned (when needed)**
- Docker Compose for full stack services (API, DB, Redis, workers)
- Redis + Celery workers
- Nginx/Traefik reverse proxy with SSL
- S3 storage in production

## 8. Implementation Phases (Practical)
1) Lock driver module schema + core endpoints (MVP)
2) Add trip + mile capture (Operations)
3) Add IFTA read-only reporting from trip data
4) Add payroll/settlements from approved trip data
5) Add background workers + OCR + integrations
6) Introduce multi-tenant platform schema + middleware
7) Expand modules (maintenance, accounting, customers, reporting)

