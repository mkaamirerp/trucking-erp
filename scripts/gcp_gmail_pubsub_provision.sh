#!/usr/bin/env bash
# Run from a workstation or Cloud Shell with: gcloud auth login (or SA key).
# Uses the Google Cloud project tied to your Gmail OAuth client (project number often matches client_id prefix).
set -euo pipefail

PROJECT_REF="${GCP_PROJECT_REF:-573894656155}"
TOPIC_ID="${GMAIL_TOPIC_ID:-truckerp-gmail-push}"
SUB_ID="${GMAIL_SUBSCRIPTION_ID:-truckerp-gmail-push-sub}"
PUSH_URL="${GMAIL_PUSH_URL:-https://truckerp.me/api/v1/webhooks/gmail/pubsub}"
# Service account Pub/Sub uses to sign OIDC JWTs for push (create in same project).
PUSH_SA="${GMAIL_PUSH_SA:?Set GMAIL_PUSH_SA e.g. pubsub-push@PROJECT_ID.iam.gserviceaccount.com}"

echo "==> Enable APIs"
gcloud services enable pubsub.googleapis.com --project="$PROJECT_REF"

echo "==> Topic"
gcloud pubsub topics create "$TOPIC_ID" --project="$PROJECT_REF" 2>/dev/null || true

echo "==> Allow Gmail to publish (consumer mailbox)"
gcloud pubsub topics add-iam-policy-binding "$TOPIC_ID" \
  --project="$PROJECT_REF" \
  --member="serviceAccount:gmail-api-push@system.gserviceaccount.com" \
  --role="roles/pubsub.publisher"

echo "==> Push subscription (OIDC to TruckERP)"
gcloud pubsub subscriptions delete "$SUB_ID" --project="$PROJECT_REF" --quiet 2>/dev/null || true
gcloud pubsub subscriptions create "$SUB_ID" \
  --project="$PROJECT_REF" \
  --topic="$TOPIC_ID" \
  --push-endpoint="$PUSH_URL" \
  --push-auth-service-account="$PUSH_SA" \
  --push-auth-token-audience="$PUSH_URL"

echo "==> Set SSM (same topic resource name Gmail watch uses)"
TOPIC_RESOURCE="projects/${PROJECT_REF}/topics/${TOPIC_ID}"
echo "Put these in AWS SSM (dev/prod platform paths):"
echo "  GMAIL_PUBSUB_TOPIC_NAME=$TOPIC_RESOURCE"
echo "  GMAIL_PUBSUB_PUSH_AUDIENCE=$PUSH_URL"
echo "Ensure \$PUSH_SA has roles/iam.serviceAccountTokenCreator for the Pub/Sub service agent if prompted by gcloud."
