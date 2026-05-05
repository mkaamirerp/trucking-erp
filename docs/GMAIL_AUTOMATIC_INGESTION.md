# Gmail automatic ingestion — definition of done

This document is the **product bar** for the Gmail intake feature. Do not mark the feature complete until **all** items below are true for the target environment.

## Health warning: `CONNECTED` vs automatic ingestion

A mailbox row may still show **`CONNECTED`** even when **automatic ingestion** is broken. **`CONNECTED`** only proves the account was connected previously — not that Google will still accept the **stored refresh token**.

If watch renewal or any Gmail API call fails with **`invalid_grant`**, treat the refresh token as **invalid**. The tenant admin must **reconnect Gmail** through OAuth (new refresh token). A **renewal timer** or **`renew-watch`** job only helps **after** refresh works; it **cannot** repair an invalid refresh token by itself.

## Definition of done

1. **Mailbox connects** — OAuth completes; refresh token stored; tenant can sign in without errors.
2. **Automatic watch** — After connect (or explicit admin action), Gmail `users.watch` is registered against the platform Pub/Sub topic; `gmail_watch_expiration_at` is set and in the future.
3. **Pub/Sub → webhook** — Push subscription delivers to `POST /api/v1/webhooks/gmail/pubsub` with configured auth (OIDC audience and/or `X-TruckERP-Gmail-Push-Token`).
4. **Webhook → delta sync** — On each valid push, the server runs `sync_gmail_delta_for_tenant`; `last_gmail_webhook_at` updates.
5. **New mail in TruckERP** — A test message to the connected inbox appears in Email load / threads **without** clicking manual sync.
6. **Watch renewal** — `scripts/renew_gmail_watches.sh` (or `python -m app.scripts.renew_gmail_watches`) is scheduled so watches renew before expiry (default threshold: `gmail_watch_renew_within_hours`, typically 48h before expiry).
7. **Admin UI** — Email settings show **Automatic mail: Live** only when server-side checks pass; blockers list what is missing; manual tools live under **Advanced**.

## Proof checklist (E2E)

Use tenant admin UI **or** authenticated API:

- `GET /api/v1/admin/email-config/gmail/ingestion-health` — must return `automatic_ingestion_ready: true` and empty `blockers` after setup.
- Send an external test email to the connected address.
- Within a few minutes: `last_webhook_at` updates, inbox shows the message.

## Explicit blockers (not “done enough”)

| State | Blocker |
|--------|---------|
| OAuth only | Automatic path not registered |
| Manual sync works | Push/watch not proven |
| Watch button exists | Watch not registered or Pub/Sub not verified |
| `CONNECTED` status | Does **not** imply automatic ingestion |

## Operations references

- Env: `GMAIL_PUBSUB_TOPIC_NAME`, `GMAIL_PUBSUB_PUSH_AUDIENCE`, `GMAIL_PUBSUB_PUSH_TOKEN` (see `app/core/config.py`).
- Renewal: `app/scripts/renew_gmail_watches.py`, shell wrapper `scripts/renew_gmail_watches.sh`.
