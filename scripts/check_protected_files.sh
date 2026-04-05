#!/usr/bin/env bash
# Layer A — Protected files guard
# Blocks commits touching protected files unless APPROVED_CONFIG_CHANGE=1.
# Install: run scripts/install_protected_files_hook.sh

set -e

is_allowed() {
  case "$1" in
    .env.example) return 0 ;;
    *) return 1 ;;
  esac
}

is_protected() {
  local f="$1"
  is_allowed "$f" && return 1
  case "$f" in
    docker-compose.yml|docker-compose.*.yml) return 0 ;;
    .env|.env.*) return 0 ;;
    infra/nginx/*) return 0 ;;
    scripts/start_api_with_ssm.sh) return 0 ;;
    scripts/*ssm*.sh) return 0 ;;
    scripts/render_truckerp_env_from_ssm.sh) return 0 ;;
    scripts/with_env.sh) return 0 ;;
    run/secrets|run/secrets/*) return 0 ;;
    *) return 1 ;;
  esac
}

STAGED=$(git diff --cached --name-only --diff-filter=ACMR 2>/dev/null || true)
[[ -z "$STAGED" ]] && exit 0

VIOLATIONS=()
while IFS= read -r f; do
  [[ -z "$f" ]] && continue
  is_protected "$f" && VIOLATIONS+=("$f")
done <<< "$STAGED"

[[ ${#VIOLATIONS[@]} -eq 0 ]] && exit 0

if [[ "$APPROVED_CONFIG_CHANGE" == "1" ]]; then
  exit 0
fi

echo "Protected config changed. Add APPROVED_CONFIG_CHANGE=1 and include a reason in commit message: CONFIG-CHANGE: <reason>"
echo ""
echo "Protected files in this commit:"
printf '  - %s\n' "${VIOLATIONS[@]}"
exit 1
