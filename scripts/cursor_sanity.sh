#!/usr/bin/env bash
set -euo pipefail

echo "== Cursor Sanity: repo root = $(pwd)"
echo "== Git status (short) =="
git status --porcelain || true
echo

echo "== Key folders =="
for d in app alembic alembic_platform alembic_tenant .cursor; do
  if [ -d "$d" ]; then
    echo "OK: $d"
  else
    echo "MISSING: $d"
  fi
done
echo

echo "== Alembic heads (platform DB — alembic_platform.ini) =="
if [ -f alembic_platform.ini ]; then
  alembic -c alembic_platform.ini heads || echo "WARN: platform alembic heads failed"
else
  echo "SKIP: alembic_platform.ini not found"
fi
echo

echo "== Alembic heads (tenant) =="
if [ -f alembic_tenant.ini ]; then
  alembic -c alembic_tenant.ini heads || echo "WARN: tenant alembic heads failed"
else
  echo "SKIP: alembic_tenant.ini not found"
fi
echo

echo "== Done =="
