#!/usr/bin/env bash
# Dev playground API reload — same guards as reload_api.sh (main branch, clean worktree).
# Canonical checkout: /home/admin/trucking_erp
set -euo pipefail
exec /home/admin/trucking_erp/scripts/reload_api.sh
