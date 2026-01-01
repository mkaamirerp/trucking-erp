# Engineering Playbook Checklist
- [ ] Read docs/ENGINEERING_PLAYBOOK.md before changes
- [ ] App boots on 8000 & /api/v1/health returns 200
- [ ] Tenant middleware enforced (X-Tenant-ID required)
- [ ] Models match migrations (Alembic applied)
- [ ] New routes use app.core.database.get_db
- [ ] No default/guessed tenant_id
- [ ] Smoke tests updated & passing
- [ ] Logs inspected after start/restart
