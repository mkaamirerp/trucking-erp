#!/usr/bin/env sh
# Fail if deprecated DB URL helper names reappear (use app.core.db_url.to_async_pg_url / to_sync_pg_url).
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Build pattern without storing the deprecated names as contiguous literals in this file.
P1="_ensure"
P2="_asyncpg"
SUF="_url"
PATTERN="${P1}${P2}${SUF}|ensure${P2}${SUF}"

if command -v rg >/dev/null 2>&1; then
  if rg -n --hidden --glob '!.git/*' "$PATTERN" .; then
    echo "❌ Found deprecated DB URL helper symbol(s). Use app.core.db_url.to_async_pg_url / to_sync_pg_url."
    exit 1
  fi
else
  # grep -R fallback (exclude .git)
  if grep -R -n -E "$PATTERN" --exclude-dir=.git .; then
    echo "❌ Found deprecated DB URL helper symbol(s). Use app.core.db_url.to_async_pg_url / to_sync_pg_url."
    exit 1
  fi
fi

echo "✅ DB URL helper name guard passed."
