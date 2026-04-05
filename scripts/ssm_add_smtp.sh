#!/usr/bin/env bash
# Add SMTP parameters to SSM so the API can send invite and OTP emails.
# Run in AWS Console CloudShell (or any shell with AWS CLI configured).
# 1) Set your SMTP values below (or export them before running).
# 2) Set SSM_PREFIX to your shared path: /truckerp/prod/shared or /truckerp/dev/shared
# 3) Run: bash scripts/ssm_add_smtp.sh

set -e
REGION="${AWS_REGION:-us-east-1}"

# ----- EDIT THESE -----
# Amazon SES example: endpoint email-smtp.us-east-1.amazonaws.com, STARTTLS on 587
SSM_PREFIX="${SSM_PREFIX:-/truckerp/prod/shared}"
SMTP_HOST="${SMTP_HOST:-email-smtp.us-east-1.amazonaws.com}"
SMTP_FROM_ADDRESS="${SMTP_FROM_ADDRESS:-noreply@truckerp.me}"   # Must be verified in SES (domain truckerp.me = *@truckerp.me)
SMTP_PORT="${SMTP_PORT:-587}"
SMTP_USERNAME="${SMTP_USERNAME:-}"   # SES SMTP username (from SES console, not AWS login)
SMTP_PASSWORD="${SMTP_PASSWORD:-}"   # SES SMTP password
# SMTP_USE_TLS=true and SMTP_USE_SSL=false are app defaults (STARTTLS on 587)
# ----------------------

echo "Using SSM prefix: $SSM_PREFIX"
echo "SMTP_HOST=$SMTP_HOST SMTP_FROM_ADDRESS=$SMTP_FROM_ADDRESS SMTP_PORT=$SMTP_PORT"
echo ""

aws ssm put-parameter --name "${SSM_PREFIX}/SMTP_HOST" --value "$SMTP_HOST" --type String --overwrite --region "$REGION"
aws ssm put-parameter --name "${SSM_PREFIX}/SMTP_FROM_ADDRESS" --value "$SMTP_FROM_ADDRESS" --type String --overwrite --region "$REGION"
aws ssm put-parameter --name "${SSM_PREFIX}/SMTP_PORT" --value "$SMTP_PORT" --type String --overwrite --region "$REGION"

if [ -n "$SMTP_USERNAME" ]; then
  aws ssm put-parameter --name "${SSM_PREFIX}/SMTP_USERNAME" --value "$SMTP_USERNAME" --type String --overwrite --region "$REGION"
  echo "SMTP_USERNAME set."
fi
if [ -n "$SMTP_PASSWORD" ]; then
  aws ssm put-parameter --name "${SSM_PREFIX}/SMTP_PASSWORD" --value "$SMTP_PASSWORD" --type SecureString --overwrite --region "$REGION"
  echo "SMTP_PASSWORD set (SecureString)."
fi

echo "Done. Restart the API so it picks up the new env."
