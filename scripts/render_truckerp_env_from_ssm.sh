#!/usr/bin/env bash
set -euo pipefail

SSM_PATH="${SSM_PATH:-}"
OUT_FILE="${OUT_FILE:-/home/admin/trucking_erp/runtime/rendered/truckerp.env}"
AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-}}"

if [[ -z "$SSM_PATH" ]]; then
  echo "SSM_PATH is required (e.g. /truckerp/prod)." >&2
  exit 1
fi

if [[ -z "$AWS_REGION" ]]; then
  AWS_REGION="$(aws configure get region 2>/dev/null || true)"
fi

if [[ -z "$AWS_REGION" ]]; then
  echo "AWS_REGION is required." >&2
  exit 1
fi

tmp_json="$(mktemp)"
trap 'rm -f "$tmp_json"' EXIT

aws ssm get-parameters-by-path \
  --with-decryption \
  --recursive \
  --path "$SSM_PATH" \
  --region "$AWS_REGION" \
  --output json >"$tmp_json"

python - "$tmp_json" "$OUT_FILE" <<'PY'
import json
import os
import sys

src = sys.argv[1]
dst = sys.argv[2]

with open(src, "r", encoding="utf-8") as f:
    data = json.load(f)

params = data.get("Parameters", [])
env = {}
for p in params:
    name = p.get("Name", "")
    key = name.rsplit("/", 1)[-1]
    if not key:
        continue
    env[key] = p.get("Value", "")

required = {"DATABASE_URL", "TENANT_DATABASE_URL", "POSTGRES_ADMIN_URL", "JWT_SECRET"}
missing = sorted(required - set(env))
if missing:
    sys.stderr.write("Missing required SSM parameters: " + ", ".join(missing) + "\n")
    sys.exit(2)

os.makedirs(os.path.dirname(dst), exist_ok=True)
with open(dst, "w", encoding="utf-8") as f:
    for key in sorted(env):
        f.write(f"{key}={env[key]}\n")

os.chmod(dst, 0o600)
print(f"Wrote {dst}")
PY
