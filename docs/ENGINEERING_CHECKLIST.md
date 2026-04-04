# Engineering Playbook Checklist
- [ ] Read docs/ENGINEERING_PLAYBOOK.md before changes
- [ ] App boots on 8000 & /api/v1/health returns 200
- [ ] **After code change (deploy to truckerp.me):**  
  1. Rebuild API image: `docker compose build truckerp-api`  
  2. Restart API: `docker compose up -d truckerp-api`  
  3. Rebuild frontend: `cd apps/web && npm run build`  
  4. Deploy the new `apps/web/dist/` (or repo) to the server.  
  (Saves having to remember these steps; API + frontend must both be updated.)
- [ ] **DB Inspector** (`/tools/diagnostics`): Your tool to see the database in the browser (tables, schema, sample rows) — no terminal. Password: `devtools123`. To use from main domain (truckerp.me) without a tenant subdomain, set `TOOLS_DEFAULT_TENANT_SLUG` or `TOOLS_DEFAULT_TENANT_ID` in env so the tools/db endpoints know which tenant DB to show.
- [ ] **Frontend live reload (local):** Run `./scripts/dev-web.sh` (or `cd apps/web && npm run dev`), open http://localhost:5173 — changes reflect without rebuilding; API must be on port 8000. Optional: local dev overlay (`docker-compose.dev.yml`) if your machine uses bind mounts; standard deploy uses `docker-compose.yml` only.
- [ ] Tenant middleware enforced (X-Tenant-ID required)
- [ ] Models match migrations (Alembic applied)
- [ ] New routes use app.core.database.get_db
- [ ] No default/guessed tenant_id
- [ ] Smoke tests updated & passing
- [ ] Logs inspected after start/restart
- [ ] New tenant seed / demo data: validation-safe emails (e.g. @demo.test not @demo.local), driver list/summary use DriverListOut (see docs/driver-list-root-cause-and-prevention.md)