# Config change approval

When a PR or push changes **protected files** (e.g. `docker-compose.yml`, nginx config, `.env*`, `scripts/start_api_with_ssm.sh`), CI requires explicit approval.

**Ways to approve:**

1. **PR title** contains `CONFIG-CHANGE: <reason>`
2. **Any commit message** in the PR/push contains `CONFIG-CHANGE: <reason>`
3. **Update this file** in the same change set with a short justification

Example for (3): add a line below with date and reason.

---

<!-- Example: 2026-02-02 Add dev-only nginx dist mount in docker-compose.dev.yml for local iteration -->
