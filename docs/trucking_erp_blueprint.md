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

ruckERP – Technical Defense Pack (Engineer-Level)
Runtime Stack

Language

Python 3.11 (FastAPI stack, async-first design)

Async IO model (asyncpg, async SQLAlchemy)

Framework

FastAPI

Pydantic schemas

Async SQLAlchemy ORM

API Layer

REST APIs

Tenant-aware routing

OpenAPI auto-generated docs (/openapi.json)

Database Layer

Primary DB

PostgreSQL 15 (containerized)

Async access via asyncpg

Architecture

Control plane DB: trucking_erp

Data plane DBs: per-tenant databases (tenant_xxx)

This is true physical separation, not just tenant_id columns.

Migrations

Alembic

Dual migration tracks:

alembic/ → platform

alembic_tenant/ → tenant

Database Layer — ADD (new content only)

DB Communication Mechanism

API talks to Postgres using SQLAlchemy (async) with the asyncpg driver.

Connection style: async connection pool per database URL.

Pattern:

Platform routes create sessions bound to platform DB URL

Tenant routes create sessions bound to tenant DB URL (resolved at request time)

How the API Chooses Which Database to Use

Platform DB (trucking_erp) is used for:

tenant registry lookup (e.g., tenant status, db_name)

plans/platform users/signup/OTP/reserved slugs

Tenant DB (e.g., tenant_smoke_active) is used for:

all business tables (drivers, loads, payroll, docs, dispatch, etc.)

Tenant DB URL is built dynamically from registry data (db_name) and the Postgres host inside the docker network (e.g., truckerp-postgres:5432).

Where DB Secrets Live

DB credentials and URLs are stored in AWS SSM Parameter Store as SecureString (KMS encrypted).

At runtime, the API loads secrets by fetching SSM parameters with decryption, then starts Uvicorn using an env file (example path used: /run/secrets/truckerp.env).

Guardrail: docker-compose should NOT hardcode DB URLs for the API if SSM is source of truth (to prevent override/mismatch).

DB Inventory (Proof of Separation)

Cluster contains:

trucking_erp (platform/control plane)

tenant_smoke_active (tenant/business data)

plus Postgres defaults: postgres, template0, template1

Connection Reliability / Safety

No host access to Postgres; all DB connections occur inside Docker network (truckerp_net).

Tenant routing enforcement prevents silent fallback:

missing tenant → 400

invalid tenant → 403

tenant not READY → blocked (safety gate)

Migrations — Critical Guardrails (ADD — new content only)

Dual Migration System (Hard Rule)

Two completely separate migration systems:

alembic/ → platform DB only (trucking_erp)

alembic_tenant/ → tenant DBs only (tenant_*)

These tracks must never cross.

Platform migrations must never create business tables.

Tenant migrations must never create platform/control tables.

Migration Ownership Rules

Platform migrations may include:

tenants registry

plans

subscriptions

platform users

signup / OTP

slug registry

security / audit tables

Tenant migrations may include:

drivers

loads

payroll

documents

dispatch

maintenance

compliance

operational tables

No mixed ownership allowed.

Execution Rules

Platform migrations run against:

trucking_erp

Tenant migrations run against:

tenant_<slug> databases only

Tenant migrations must be executed per tenant DB.

Provisioning Rule
New tenant flow:

CREATE DATABASE tenant_<slug>

Run alembic_tenant migrations on that DB

Mark tenant as READY in platform_tenants

Only then allow routing to that tenant

No tenant can be routable before migrations complete.

Idempotency Rule

Tenant migrations must be idempotent:

safe re-runs

safe partial failures

safe retries

No migration should assume a clean DB state.

No migration should depend on manual SQL fixes.

Stamping Rule (Emergency Only)

alembic stamp is last-resort only.

Stamping is allowed only for:

disaster recovery

emergency state repair

Normal flow = real migrations, not stamping.

No Manual Schema Drift Rule

No manual ALTER TABLE in production paths.

No manual schema edits outside Alembic.

All schema changes must be:

versioned

reviewable

reproducible

migratable

Drift Detection Guardrails

Platform DB must never contain tenant tables.

Tenant DB must never contain platform tables.

Schema separation must be continuously verifiable.

Coder Safety Rules

Coders must not:

write migrations without specifying target DB

reuse revision IDs across tracks

copy migrations between tracks

modify old migrations after deployment

merge platform + tenant schema logic

Failure Containment

Broken tenant migration affects only that tenant DB.

Broken platform migration affects registry only, not tenant data.

No migration should ever affect multiple tenants at once.

CI/Automation Targets (Design Contract)

CI should enforce:

no platform tables in alembic_tenant

no tenant tables in alembic

no raw SQL in migrations without explicit review

no mixed metadata imports

no shared Base between tracks

Infrastructure

Containerization

Docker

Docker Compose

Network Model

Private Docker network: truckerp_net

Internal service-to-service communication only

No host exposure for DB or API

Public Access

Nginx container only

Reverse proxy → API

SSL termination via Certbot

Wildcard cert: *.truckerp.me

Security Model

Network Security

DB not accessible from host

API not accessible from host

Only Nginx exposed on 80/443

Secrets

AWS SSM Parameter Store

SecureString (KMS encrypted)

Loaded at runtime

No secrets in repo

No secrets in Docker images

Tenant Isolation

Resolver-based tenant routing

Registry-driven DB resolution

Hard-fail if tenant DB not provisioned

Missing tenant header → 400

Invalid tenant → 403

Environment Types

Dev

Docker Compose

Local volumes

Internal networking

Prod (current model)

EC2

Docker Compose

Nginx front

SSM secrets

Isolated network model

(Future: ECS/EKS possible, but not required yet)

Capacity & Scaling Model (Honest + defensible)

Current capacity model

Vertical scaling on EC2

Horizontal scaling via:

Multiple API containers

Nginx load balancing

DB scaling via Postgres replication later

Tenant scaling

Tenants are isolated by DB

Heavy tenant ≠ impact on others

Can move large tenants to dedicated DB instances

Design choice

Scaling unit = tenant database
This is enterprise-grade SaaS design.

Failure Isolation

One tenant DB failure does not crash platform

One tenant DB corruption does not leak into others

Platform DB failure does not corrupt tenant data

Tenant DB failure does not kill platform registry

CI / Quality Controls (in progress but designed)

Planned:

Tenant safety enforcement scripts

Forbidden SQL patterns

CI grep gates

Migration idempotency checks

Smoke tests for tenant routing

Already:

Network isolation checks

Tenant routing smoke tests

Schema separation guards

Observability (honest answer)

Current

Container logs

API logs

Nginx logs

DB logs

Planned

Structured logging

Centralized logging (ELK / Loki)

Metrics (Prometheus/Grafana)

Health checks

Alerting

Tooling

Dev Tools

VS Code

Docker

GitHub

Alembic

Postgres

Nginx

AI Tooling (internal productivity, not production dependency)

AI-assisted coding (Cursor/Codex-style tooling)

Used for speed, not runtime dependency

Killer Technical Answers (Use these lines)
Q: What Python version?

A: Python 3.11, async-first stack using FastAPI and async SQLAlchemy.

Q: How is tenant isolation enforced?

A: Physical DB separation per tenant + registry-driven routing + tenant middleware + DB session binding.

Q: Where are secrets stored?

A: AWS SSM Parameter Store, SecureString with KMS encryption — injected at runtime, not stored in repo or images.

Q: How is infra built?

A: Dockerized microservices, private Docker network, Nginx reverse proxy, EC2 host, internal-only DB/API.

Q: How do you scale?

A: API horizontally, DB vertically per tenant, and tenant-level sharding by database — scaling unit is the tenant DB.

Q: What happens if one tenant grows huge?

A: They get a dedicated DB instance without affecting others.

Q: How do you handle migrations safely?

A: Dual Alembic tracks + idempotent migrations + platform/tenant separation.

Q: What’s the weakest area right now?

A: Observability stack (metrics/log aggregation) — planned but not fully deployed yet.

Driver Onboarding Rules (ADD — new section only)

Onboarding Flow Model

Driver onboarding supports staged submission, not instant activation.

A driver can submit profile data and optional documents.

Submission ≠ activation.

Data is treated as pending until admin approval.

Admin-Gated Activation

All driver records enter a pending state after submission.

Admin review is mandatory before:

driver becomes active

driver is assignable to loads

driver appears in dispatch workflows

driver appears in payroll

Required vs Optional Documents

Documents are categorized as:

Required

Optional

Driver is allowed to submit without all required documents.

System must:

show missing required docs after submission

flag driver as incomplete

block activation until requirements are met

Approval Rules

Only admin can:

approve driver

activate driver

assign driver to truck

enable dispatch eligibility

enable payroll eligibility

Approval is a state transition, not just a flag change.

Data Persistence Rules

Driver-submitted data is stored as pending data.

After approval:

data is promoted to official driver record

driver profile expands to full master schema (assignments, payroll links, compliance, etc.)

Document Handling Rules

Document uploads are optional at submission time.

System shows missing required documents post-submit.

File listing behavior:

default API responses return active files only

inactive files are hidden

future admin-only option may expose inactive files for audit/history

Operational Guardrails

Driver cannot:

be dispatched

be assigned to a load

appear in payroll

appear in safety/compliance workflows
unless admin-approved.

Role Separation

Driver role: submit data + upload docs

Admin role: review + approve + activate + assign + enable workflows

State Model

submitted

pending_review

approved

active

inactive

suspended

State transitions are admin-controlled only.

Additional Technical Areas for Meeting Defense (ADD — new section only)
API Request Lifecycle

Request flow:

Nginx → FastAPI → middleware → tenant resolver → DB session binding → router → service → repository → response

Middleware handles:

tenant resolution

tenant validation

tenant readiness checks

No endpoint executes business logic before tenant context is resolved.

Session & Connection Management

DB connections use async connection pooling.

Sessions are request-scoped (not global/static sessions).

No shared global DB sessions.

Each request gets a fresh async session bound to the correct DB.

Transaction Handling

SQLAlchemy session lifecycle:

begin transaction on request

commit on success

rollback on exception

No auto-commit patterns.

Prevents partial writes across requests.

API Boundary Rules

Platform routers cannot import tenant services.

Tenant routers cannot import platform DB sessions.

Registry lookup is the only allowed cross-plane interaction.

Schema Ownership Rules

Platform DB schema:

tenants

plans

subscriptions

users

signup/OTP/security events

slug registry

Tenant DB schema:

drivers

loads

payroll

documents

dispatch

maintenance

compliance

operational data

No mixed ownership tables allowed.

Error Isolation Model

Platform errors do not crash tenant DB connections.

Tenant DB failures do not corrupt platform registry.

Resolver failures stop request before DB access.

Tenant DB connection failure returns controlled error.

Config Management

Config sources:

SSM (prod)

env file (runtime)

docker-compose (infra only, not secrets)

No secrets in:

Git

Docker images

Compose files

CI configs

Infrastructure Boundaries

API container cannot access host network directly.

Postgres container not exposed to host.

Internal DNS resolution only (truckerp-postgres hostname).

No localhost DB connections in production path.

Version Control Discipline

Migrations versioned.

Schema changes tracked.

Dual alembic histories maintained.

No manual DB edits in prod path (except emergency recovery scenarios).

Data Integrity Model

No cross-tenant joins possible (physical DB separation).

No cross-tenant foreign keys possible.

No shared business tables.

Registry DB never holds business records.

Extensibility Model

New modules plug into:

tenant router

tenant services

tenant DB

Platform layer remains unchanged when adding business modules.

Failure Domains

Failure domains are isolated by:

container

database

tenant

service layer

One failure does not cascade system-wide.

Deployment Safety Model

Build → containerize → deploy

No live-code mutation

No SSH-editing containers

Controlled restarts

Auditability

Platform DB is audit plane.

Tenant DB is operational plane.

Events can be logged at:

routing

tenant resolution

DB binding

approval flows

admin actions
