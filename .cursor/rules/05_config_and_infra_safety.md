# Config and infrastructure safety (ALWAYS)

## AI behavior (this app)
- **Never modify** `docker-compose.yml`, `docker-compose.*.yml`, `.env*`, database URLs, `infra/nginx/*`, `scripts/start_api_with_ssm.sh`, or other critical YAML/config without **explicit user request**.
- These files affect the whole stack; one change can break other services or other people’s setups.
- **Do not** “fix” a problem by editing config to suit the immediate need if it can break something else.
- **If a fix might need a config change:** describe the option, trade-offs, and risk; **ask** before editing. Let the human decide.
- When the user reports “container vs local” or “changes not taking effect,” suggest options (e.g. “rebuild image” vs “add volume”) and **do not** edit YAML unless the user explicitly says to do it.

## Enforceable guardrails (local + CI)
- **Protected files:** docker-compose.yml, docker-compose.*.yml, .env* (except .env.example), infra/nginx/*, scripts/start_api_with_ssm.sh, scripts/*ssm*.sh, scripts/render_truckerp_env_from_ssm.sh, scripts/with_env.sh, run/secrets (if tracked).
- **Layer A (pre-commit):** `scripts/check_protected_files.sh` blocks commits touching protected files unless `APPROVED_CONFIG_CHANGE=1`. Install once: `scripts/install_protected_files_hook.sh`. Bypass: `APPROVED_CONFIG_CHANGE=1 git commit -m "CONFIG-CHANGE: <reason>"`.
- **Layer B (CI):** `.github/workflows/config_guard.yml` fails the run if protected files change unless PR title or a commit message contains `CONFIG-CHANGE:` or `docs/CONFIG_CHANGE_APPROVAL.md` is updated.
- **Layer C (runtime):** Standard deployment = `docker-compose.yml` only (image-based `/app`, no dev bind mounts on the server). Never put dev-only mounts in `docker-compose.yml`.

Full reference: `docs/config-and-infra-guardrails.md`.
