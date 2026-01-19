
---

## 🔐 Tenant Safety – Forbidden SQL Rules

All developers **must** follow the tenant-safe SQL rules.

See the canonical cheat-sheet:
- `docs/tenant_safety_forbidden_sql.md`

These rules are **mechanically enforced by CI** (grep + pytest).  
PRs that violate them **must fail**.
