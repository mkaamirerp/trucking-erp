"""Tenant Admin: primary email mailbox config. One mailbox per tenant in V1.

Secrets are write-only: stored encrypted in platform DB, never in tenant DB,
never returned by GET, never logged. credential_ref enforces tenant ownership
when resolving platform secret records.

Gmail: OAuth-first flow via Connect Gmail.
Other providers: Manual IMAP/SMTP under "Other Email Provider" fallback.

V1 Gmail callback: tenant_email_accounts is the authoritative write target.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.deps.admin import is_tenant_admin
from app.deps.auth import CurrentUser, get_current_user
from app.deps.entitlements import require_entitlement
from app.deps.tenant import require_tenant, require_tenant_slug
from app.deps.tenant_db import get_tenant_db, open_tenant_session_by_id
from app.core.database import AsyncSessionLocal, get_db
from app.models.email_mailbox import TenantEmailMailbox
from app.models.platform_integration import TenantIntegrationSecret
from app.models.tenant_email_account import TenantEmailAccount
from app.schemas.email_config import (
    EmailConfigOut,
    EmailConfigUpdate,
    EmailConfigTestOut,
    GmailIngestionHealthOut,
    MicrosoftOAuthStatusOut,
)
from app.services.email_ingestion_imap import (
    EMAIL_PROVIDER_OTHER,
    imap_test_connection_sync,
    load_mailbox_secret_json,
    smtp_test_connection_sync,
    sync_other_imap_inbox_for_tenant,
)
from app.services.gmail_oauth import (
    build_authorize_url,
    exchange_code_for_tokens,
    get_google_userinfo,
    get_user_email,
    make_state,
    parse_state,
    refresh_access_token,
)
from app.services.email_ingestion_gmail import bootstrap_gmail_history_cursor, sync_gmail_inbox_for_tenant
from app.services.microsoft_graph_sync import (
    PROVIDER_MICROSOFT365,
    ensure_microsoft_subscription,
    renew_microsoft_subscription_if_due,
    stop_microsoft_subscription_safe,
    sync_microsoft_delta_for_tenant,
)
from app.services.microsoft_oauth import (
    build_microsoft_authorize_url,
    exchange_ms_code_for_tokens,
    graph_get_me_profile,
    make_ms_state,
    parse_ms_state,
)
from app.services.gmail_mailbox_platform_index import (
    delete_gmail_mailbox_mappings_for_tenant,
    upsert_gmail_mailbox_tenant_mapping,
)
from app.services.gmail_watch import register_or_renew_gmail_watch_for_tenant, stop_gmail_watch_for_tenant
from app.utils.encryption import decrypt_secret, encrypt_secret, generate_credential_ref

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["Tenant Admin - Email"],
    dependencies=[Depends(require_entitlement("email_mailbox"))],
)

logger = logging.getLogger(__name__)

# Mailbox "test connection" responses and stored diagnostics: stable copy only; use logger.exception for detail.
_MAILBOX_TEST_MSG_OAUTH = (
    "Could not complete mailbox test. Reconnect the account or try again later."
)
_MAILBOX_TEST_MSG_MAIL_SERVER = (
    "Could not connect to the mail server. Check host, port, network, and stored credentials."
)

# TenantEmailAccount.last_error for Gmail admin routes: stable tokens only (details in logs).
_GMAIL_ACCOUNT_LAST_ERROR_WATCH_REJECTED = "gmail_watch_rejected"
_GMAIL_ACCOUNT_LAST_ERROR_SYNC_FAILED = "gmail_sync_failed"

_GMAIL_PROOF_STEPS = [
    "Platform: GMAIL_PUBSUB_TOPIC_NAME, push auth (OIDC or X-TruckERP-Gmail-Push-Token), and Gmail API/Pub/Sub are configured in Google Cloud.",
    "Tenant: Gmail is connected and “Automatic new-mail alerts” shows Active with a future expiry.",
    "Send a test email to the connected inbox from an external address.",
    "Within about 1–3 minutes, “Last automatic signal received” updates (Pub/Sub → webhook).",
    "Email load / inbox in TruckERP shows the new thread without clicking Sync.",
]


def _gmail_ingestion_aux(acc: TenantEmailAccount) -> dict:
    """Compute automatic ingestion readiness (not implied by OAuth CONNECTED)."""
    topic = getattr(settings, "gmail_pubsub_topic_name", None)
    pubsub_ok = bool(topic and str(topic).strip())
    now = datetime.now(timezone.utc)
    exp = acc.gmail_watch_expiration_at
    watch_live = bool(exp and exp > now)
    cursor_ok = bool(acc.gmail_history_id and str(acc.gmail_history_id).strip())
    blockers: list[str] = []
    warnings: list[str] = []
    if not pubsub_ok:
        blockers.append(
            "Server is missing Gmail Pub/Sub topic configuration (GMAIL_PUBSUB_TOPIC_NAME). "
            "Automatic new-mail delivery cannot work until operations finishes Google Cloud setup."
        )
    elif acc.gmail_watch_expiration_at is None:
        blockers.append(
            "Google is not subscribed to send new-mail notifications to TruckERP. "
            "Complete setup: use “Turn on automatic new-mail alerts” (or reconnect Gmail after platform is ready)."
        )
    elif not watch_live:
        blockers.append(
            "The Gmail notification subscription has expired. Renew automatic alerts (Advanced → Extend subscription), "
            "or ask operations to run the Gmail watch renewal job."
        )
    elif not cursor_ok:
        blockers.append(
            "Ingestion bookmark (History ID) is not set. Use “Fetch mail once” in Advanced or trigger a sync so the server can track changes."
        )
    ready = len(blockers) == 0
    if ready and acc.last_gmail_webhook_at is None:
        warnings.append(
            "No push notification recorded yet. After turning alerts on, send a test email and confirm “Last automatic signal received” updates."
        )
    elif ready and acc.last_gmail_webhook_at is not None:
        age_s = (now - acc.last_gmail_webhook_at).total_seconds()
        if age_s > 7 * 24 * 3600:
            warnings.append(
                "No push notification in the last 7 days. If the inbox should have received mail, verify Pub/Sub → webhook delivery."
            )
    return {
        "gmail_pubsub_topic_configured": pubsub_ok,
        "gmail_automatic_ingestion_ready": ready,
        "gmail_automatic_ingestion_blockers": blockers,
        "gmail_automatic_ingestion_warnings": warnings,
    }


def _gmail_account_to_out(acc: TenantEmailAccount) -> EmailConfigOut:
    """Map tenant_email_accounts (Gmail OAuth) to EmailConfigOut."""
    now = datetime.now(timezone.utc)
    exp = acc.gmail_watch_expiration_at
    watch_active = bool(exp and exp > now)
    cursor_present = bool(acc.gmail_history_id and str(acc.gmail_history_id).strip())
    aux = _gmail_ingestion_aux(acc)
    return EmailConfigOut(
        id=acc.id,
        tenant_id=acc.tenant_id,
        email_address=acc.email_address or "",
        display_name=None,
        mailbox_type="gmail",
        provider_name="Gmail / Google Workspace",
        connection_mode="oauth",
        is_primary=acc.is_primary,
        is_active=True,
        inbound_enabled=True,
        outbound_enabled=True,
        status=acc.status,
        imap_host=None,
        imap_port=None,
        imap_username=None,
        imap_security=None,
        smtp_host=None,
        smtp_port=None,
        smtp_username=None,
        reply_to=None,
        smtp_security=None,
        use_ssl=None,
        use_tls=None,
        oauth_provider="google",
        oauth_account_email=acc.email_address,
        connection_status=None,
        last_tested_at=None,
        last_test_status=None,
        last_inbound_test_at=None,
        last_outbound_test_at=None,
        last_error_code=None,
        last_error_message=acc.last_error,
        last_inbound_sync_at=acc.last_sync_at,
        last_sync_status=None,
        last_sync_error=None,
        imap_uidvalidity=None,
        imap_last_seen_uid=None,
        gmail_history_cursor_present=cursor_present,
        gmail_watch_active=watch_active,
        gmail_watch_expires_at=acc.gmail_watch_expiration_at,
        last_gmail_webhook_at=acc.last_gmail_webhook_at,
        gmail_pubsub_topic_configured=aux["gmail_pubsub_topic_configured"],
        gmail_automatic_ingestion_ready=aux["gmail_automatic_ingestion_ready"],
        gmail_automatic_ingestion_blockers=aux["gmail_automatic_ingestion_blockers"],
        gmail_automatic_ingestion_warnings=aux["gmail_automatic_ingestion_warnings"],
        ms_graph_subscription_id=None,
        ms_graph_subscription_status=None,
        ms_graph_subscription_expiration_at=None,
        ms_graph_delta_cursor_present=None,
        ms_graph_last_notification_at=None,
        ms_graph_last_delta_sync_at=None,
        ms_graph_last_sync_status=None,
        ms_graph_last_sync_error=None,
        created_at=acc.created_at,
        updated_at=acc.updated_at,
    )


def _microsoft_account_to_out(acc: TenantEmailAccount) -> EmailConfigOut:
    delta_present = bool(acc.ms_graph_delta_link and str(acc.ms_graph_delta_link).strip())
    return EmailConfigOut(
        id=acc.id,
        tenant_id=acc.tenant_id,
        email_address=acc.email_address or "",
        display_name=None,
        mailbox_type="microsoft365",
        provider_name="Microsoft 365 / Outlook",
        connection_mode="oauth",
        is_primary=acc.is_primary,
        is_active=True,
        inbound_enabled=True,
        outbound_enabled=True,
        status=acc.status,
        imap_host=None,
        imap_port=None,
        imap_username=None,
        imap_security=None,
        smtp_host=None,
        smtp_port=None,
        smtp_username=None,
        reply_to=None,
        smtp_security=None,
        use_ssl=None,
        use_tls=None,
        oauth_provider="microsoft",
        oauth_account_email=acc.email_address,
        connection_status=acc.ms_graph_subscription_status,
        last_tested_at=None,
        last_test_status=None,
        last_inbound_test_at=None,
        last_outbound_test_at=None,
        last_error_code=None,
        last_error_message=acc.last_error,
        last_inbound_sync_at=acc.last_sync_at,
        last_sync_status=acc.ms_graph_last_sync_status,
        last_sync_error=acc.ms_graph_last_sync_error,
        imap_uidvalidity=None,
        imap_last_seen_uid=None,
        gmail_history_cursor_present=None,
        gmail_watch_active=None,
        gmail_watch_expires_at=None,
        last_gmail_webhook_at=None,
        gmail_pubsub_topic_configured=None,
        gmail_automatic_ingestion_ready=None,
        gmail_automatic_ingestion_blockers=None,
        gmail_automatic_ingestion_warnings=None,
        ms_graph_subscription_id=acc.ms_graph_subscription_id,
        ms_graph_subscription_status=acc.ms_graph_subscription_status,
        ms_graph_subscription_expiration_at=acc.ms_graph_subscription_expiration_at,
        ms_graph_delta_cursor_present=delta_present,
        ms_graph_last_notification_at=acc.ms_graph_last_notification_at,
        ms_graph_last_delta_sync_at=acc.ms_graph_last_delta_sync_at,
        ms_graph_last_sync_status=acc.ms_graph_last_sync_status,
        ms_graph_last_sync_error=acc.ms_graph_last_sync_error,
        created_at=acc.created_at,
        updated_at=acc.updated_at,
    )


def _mailbox_to_out(m: TenantEmailMailbox) -> EmailConfigOut:
    return EmailConfigOut(
        id=m.id,
        tenant_id=m.tenant_id,
        email_address=m.email_address,
        display_name=m.display_name,
        mailbox_type=m.mailbox_type,
        provider_name=m.provider_name,
        connection_mode=m.connection_mode,
        is_primary=m.is_primary,
        is_active=m.is_active,
        inbound_enabled=m.inbound_enabled,
        outbound_enabled=m.outbound_enabled,
        status=m.status,
        imap_host=m.imap_host,
        imap_port=m.imap_port,
        imap_username=m.imap_username,
        imap_security=m.imap_security,
        smtp_host=m.smtp_host,
        smtp_port=m.smtp_port,
        smtp_username=m.smtp_username,
        smtp_security=m.smtp_security,
        reply_to=m.reply_to,
        use_ssl=m.use_ssl,
        use_tls=m.use_tls,
        oauth_provider=m.oauth_provider,
        oauth_account_email=m.oauth_account_email,
        connection_status=m.connection_status,
        last_tested_at=m.last_tested_at,
        last_test_status=m.last_test_status,
        last_inbound_test_at=m.last_inbound_test_at,
        last_outbound_test_at=m.last_outbound_test_at,
        last_error_code=m.last_error_code,
        last_error_message=m.last_error_message,
        last_inbound_sync_at=m.last_sync_at,
        last_sync_status=m.last_sync_status,
        last_sync_error=m.last_sync_error,
        imap_uidvalidity=int(m.imap_uidvalidity) if m.imap_uidvalidity is not None else None,
        imap_last_seen_uid=int(m.imap_last_seen_uid) if m.imap_last_seen_uid is not None else None,
        gmail_history_cursor_present=None,
        gmail_watch_active=None,
        gmail_watch_expires_at=None,
        last_gmail_webhook_at=None,
        gmail_pubsub_topic_configured=None,
        gmail_automatic_ingestion_ready=None,
        gmail_automatic_ingestion_blockers=None,
        gmail_automatic_ingestion_warnings=None,
        ms_graph_subscription_id=None,
        ms_graph_subscription_status=None,
        ms_graph_subscription_expiration_at=None,
        ms_graph_delta_cursor_present=None,
        ms_graph_last_notification_at=None,
        ms_graph_last_delta_sync_at=None,
        ms_graph_last_sync_status=None,
        ms_graph_last_sync_error=None,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _merge_secret_payload(payload: EmailConfigUpdate, existing: dict) -> dict:
    out = dict(existing or {})
    if payload.imap_password:
        out["imap_password"] = payload.imap_password
    if payload.smtp_password:
        out["smtp_password"] = payload.smtp_password
    if payload.oauth_access_token:
        out["oauth_access_token"] = payload.oauth_access_token
    if payload.oauth_refresh_token:
        out["oauth_refresh_token"] = payload.oauth_refresh_token
    return out


def _return_url(slug: str) -> str:
    """Build return URL for post-OAuth redirect: https://{slug}.{base}{path}."""
    base = settings.base_domain or "truckerp.me"
    path = (settings.gmail_oauth_return_path or "/admin/settings/email").strip().rstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    return f"https://{slug}.{base}{path}"


def _platform_callback_url() -> str:
    """Fixed platform callback URL (no wildcards; one entry in Google Console)."""
    url = settings.gmail_oauth_callback_url
    if url:
        return url.rstrip("/")
    base = settings.base_domain or "truckerp.me"
    return f"https://{base}/api/v1/admin/email-config/gmail/callback"


def _microsoft_platform_callback_url() -> str:
    url = settings.microsoft_oauth_callback_url
    if url:
        return url.rstrip("/")
    base = settings.base_domain or "truckerp.me"
    return f"https://{base}/api/v1/admin/email-config/microsoft/callback"


@router.get("/email-config/gmail/authorize")
async def gmail_authorize(
    tenant_id: int = Depends(require_tenant),
    tenant_slug: str = Depends(require_tenant_slug),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Start Gmail OAuth flow. Uses fixed platform callback URL; state carries tenant for return."""
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Admin role required")
    if not settings.google_client_id:
        raise HTTPException(
            status_code=503,
            detail="Gmail integration is not configured. Contact your administrator.",
        )
    redirect_uri = _platform_callback_url()
    state = make_state(tenant_id, tenant_slug)
    try:
        url = build_authorize_url(redirect_uri=redirect_uri, state=state)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return RedirectResponse(url=url, status_code=302)


@router.get("/email-config/gmail/ingestion-health", response_model=GmailIngestionHealthOut)
async def gmail_ingestion_health(
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    tenant_db: AsyncSession = Depends(get_tenant_db),
):
    """
    Explicit readiness for the production path: Gmail push → Pub/Sub → webhook → delta sync.
    OAuth "CONNECTED" alone is not sufficient for automatic ingestion.
    """
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Admin role required")
    acc = await tenant_db.scalar(
        select(TenantEmailAccount)
        .where(TenantEmailAccount.tenant_id == tenant_id, TenantEmailAccount.provider == "gmail")
        .limit(1)
    )
    if not acc:
        return GmailIngestionHealthOut(
            oauth_connected=False,
            gmail_pubsub_topic_configured=bool(
                getattr(settings, "gmail_pubsub_topic_name", None) and str(settings.gmail_pubsub_topic_name).strip()
            ),
            history_cursor_present=False,
            watch_registered_and_valid=False,
            watch_expires_at=None,
            last_webhook_at=None,
            last_delta_sync_at=None,
            automatic_ingestion_ready=False,
            blockers=["Gmail is not connected. Use Connect with Google first."],
            warnings=[],
            proof_steps=list(_GMAIL_PROOF_STEPS),
        )
    now = datetime.now(timezone.utc)
    exp = acc.gmail_watch_expiration_at
    watch_ok = bool(exp and exp > now)
    cursor_ok = bool(acc.gmail_history_id and str(acc.gmail_history_id).strip())
    aux = _gmail_ingestion_aux(acc)
    oauth_ok = (acc.status or "").upper() == "CONNECTED" or bool(acc.refresh_token_encrypted)
    return GmailIngestionHealthOut(
        oauth_connected=oauth_ok,
        gmail_pubsub_topic_configured=bool(aux["gmail_pubsub_topic_configured"]),
        history_cursor_present=cursor_ok,
        watch_registered_and_valid=watch_ok,
        watch_expires_at=acc.gmail_watch_expiration_at,
        last_webhook_at=acc.last_gmail_webhook_at,
        last_delta_sync_at=acc.last_sync_at,
        automatic_ingestion_ready=bool(aux["gmail_automatic_ingestion_ready"]),
        blockers=list(aux["gmail_automatic_ingestion_blockers"]),
        warnings=list(aux["gmail_automatic_ingestion_warnings"]),
        proof_steps=list(_GMAIL_PROOF_STEPS),
    )


def _gmail_callback_error_redirect(slug: str | None, error: str) -> RedirectResponse:
    """Redirect to tenant settings or platform root with error."""
    if slug:
        return RedirectResponse(url=f"{_return_url(slug)}?error={error}", status_code=302)
    base = settings.base_domain or "truckerp.me"
    return RedirectResponse(url=f"https://{base}/?gmail_error={error}", status_code=302)


async def _gmail_callback_ctx(
    request: Request,
    state: str | None = None,
):
    """Parse state, set request.state.tenant_id/slug. Returns RedirectResponse on error (short-circuits)."""
    if not state:
        return _gmail_callback_error_redirect(None, "missing_params")
    parsed = parse_state(state)
    if not parsed:
        return _gmail_callback_error_redirect(None, "invalid_state")
    tid, slug = parsed
    request.state.tenant_id = tid
    request.state.tenant_slug = slug
    return {"tenant_id": tid, "tenant_slug": slug}


@router.get("/email-config/gmail/callback")
async def gmail_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    callback_ctx: dict | RedirectResponse = Depends(_gmail_callback_ctx),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Handle Google OAuth callback. V1: writes only to tenant_email_accounts. Tenant DB opened only after state validated."""
    if isinstance(callback_ctx, RedirectResponse):
        return callback_ctx
    if not isinstance(callback_ctx, dict) or "tenant_id" not in callback_ctx or "tenant_slug" not in callback_ctx:
        base = settings.base_domain or "truckerp.me"
        return RedirectResponse(url=f"https://{base}/?gmail_error=invalid_state", status_code=302)
    tid = callback_ctx["tenant_id"]
    slug = callback_ctx["tenant_slug"]
    return_url = _return_url(slug)
    if error:
        return RedirectResponse(url=f"{return_url}?error={error}", status_code=302)
    if not code or not state:
        return RedirectResponse(url=f"{return_url}?error=missing_params", status_code=302)
    if not current_user or not is_tenant_admin(current_user.role):
        return RedirectResponse(url=f"{return_url}?error=unauthorized", status_code=302)
    redirect_uri = _platform_callback_url()
    try:
        tokens = await exchange_code_for_tokens(code=code, redirect_uri=redirect_uri)
    except Exception:
        return RedirectResponse(url=f"{return_url}?error=token_exchange_failed", status_code=302)
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")

    # Open tenant DB only after tenant_id is validated (no dependency-order side effects)
    push_mailbox: str | None = None
    oauth_complete_for_ui = False

    async for tenant_db in open_tenant_session_by_id(int(tid)):
        # Reconnect: Google may not return refresh_token; keep existing if present
        existing = await tenant_db.scalar(
            select(TenantEmailAccount)
            .where(TenantEmailAccount.tenant_id == int(tid), TenantEmailAccount.provider == "gmail")
            .limit(1)
        )
        if not refresh_token and existing:
            try:
                refresh_token = decrypt_secret(existing.refresh_token_encrypted).decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                pass
        if not access_token or not refresh_token:
            return RedirectResponse(url=f"{return_url}?error=no_refresh_token", status_code=302)

        identity_email: str | None = None
        provider_account_id: str | None = None
        identity_fetch_error: str | None = None
        identity_fetch_succeeded = False
        try:
            profile = await get_google_userinfo(access_token)
            identity_fetch_succeeded = True
            raw_email = (profile.get("email") or "").strip()
            if raw_email:
                identity_email = raw_email
            # Google userinfo v2 exposes numeric "id"; OIDC may use "sub"
            raw_pid = (profile.get("id") or profile.get("sub") or "").strip()
            if raw_pid:
                provider_account_id = raw_pid[:255]
        except Exception:
            logger.exception(
                "gmail_oauth_callback userinfo fetch failed tenant_id=%s",
                tid,
            )
            identity_fetch_error = "userinfo_fetch_failed"

        email_from_profile = bool(identity_email and str(identity_email).strip())
        gmail_fully_identified = identity_fetch_succeeded and email_from_profile

        expires_in = tokens.get("expires_in")
        token_expiry_at = None
        if expires_in is not None and isinstance(expires_in, (int, float)):
            token_expiry_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
        scope_str = tokens.get("scope")
        access_enc = encrypt_secret(access_token)
        refresh_enc = encrypt_secret(refresh_token)
        user_id = str(current_user.user.id)
        push_mailbox = identity_email or (existing.email_address if existing else None)
        push_mailbox = (push_mailbox or "").strip() or None
        oauth_complete_for_ui = bool(gmail_fully_identified and push_mailbox)
        resolved_account_status = "CONNECTED" if oauth_complete_for_ui else "CONFIGURED"
        if identity_fetch_succeeded and not email_from_profile and not identity_fetch_error:
            identity_fetch_error = "gmail_identity_incomplete: no email in Google profile"

        if existing:
            existing.access_token_encrypted = access_enc
            existing.refresh_token_encrypted = refresh_enc
            existing.token_expiry_at = token_expiry_at
            existing.scope = scope_str
            existing.status = resolved_account_status
            if identity_fetch_succeeded:
                if identity_email:
                    existing.email_address = identity_email
                if provider_account_id:
                    existing.provider_account_id = provider_account_id
                if gmail_fully_identified:
                    existing.last_error = None
                elif identity_fetch_error:
                    existing.last_error = identity_fetch_error
            elif identity_fetch_error:
                existing.last_error = identity_fetch_error
            existing.connected_by_user_id = user_id
            existing.updated_at = datetime.now(timezone.utc)
        else:
            acc = TenantEmailAccount(
                tenant_id=int(tid),
                provider="gmail",
                email_address=identity_email,
                status=resolved_account_status,
                access_token_encrypted=access_enc,
                refresh_token_encrypted=refresh_enc,
                token_expiry_at=token_expiry_at,
                scope=scope_str,
                is_primary=True,
                last_error=identity_fetch_error
                if (identity_fetch_error or not oauth_complete_for_ui)
                else None,
                connected_by_user_id=user_id,
                provider_account_id=provider_account_id,
            )
            tenant_db.add(acc)
        await tenant_db.commit()
        break

    if push_mailbox:
        async with AsyncSessionLocal() as pdb:
            await upsert_gmail_mailbox_tenant_mapping(pdb, tenant_id=int(tid), gmail_address=push_mailbox)
            await pdb.commit()

    watch_auto_ok = True
    async for tenant_db in open_tenant_session_by_id(int(tid)):
        try:
            await bootstrap_gmail_history_cursor(tenant_db, int(tid))
            await tenant_db.commit()
        except Exception as exc:
            logger.warning("gmail history cursor bootstrap failed: %s", exc)
            try:
                await tenant_db.rollback()
            except Exception:
                pass
            try:
                acc_boot = await tenant_db.scalar(
                    select(TenantEmailAccount)
                    .where(TenantEmailAccount.tenant_id == int(tid), TenantEmailAccount.provider == "gmail")
                    .limit(1)
                )
                if acc_boot:
                    detail = (str(exc) or "unknown").strip()
                    acc_boot.last_error = f"gmail_bootstrap_failed: {detail[:220]}"
                    acc_boot.updated_at = datetime.now(timezone.utc)
                    await tenant_db.commit()
            except Exception:
                try:
                    await tenant_db.rollback()
                except Exception:
                    pass
        break

    topic = getattr(settings, "gmail_pubsub_topic_name", None)
    if topic and str(topic).strip():
        async for tenant_db in open_tenant_session_by_id(int(tid)):
            try:
                await register_or_renew_gmail_watch_for_tenant(
                    tenant_db, int(tid), topic_name=str(topic).strip()
                )
            except Exception as exc:
                watch_auto_ok = False
                logger.exception("gmail watch auto-register after OAuth failed tenant_id=%s", tid)
            break

    q = "gmail=connected" if oauth_complete_for_ui else "gmail=degraded"
    if (topic and str(topic).strip()) and not watch_auto_ok:
        q += "&gmail_watch=failed"
    return RedirectResponse(url=f"{return_url}?{q}", status_code=302)


async def _microsoft_callback_ctx(
    request: Request,
    state: str | None = Query(None),
):
    if not state:
        state = request.query_params.get("state")
    if not state:
        return _gmail_callback_error_redirect(None, "missing_params")
    parsed = parse_ms_state(state)
    if not parsed:
        return _gmail_callback_error_redirect(None, "invalid_state")
    tid, slug = parsed
    request.state.tenant_id = tid
    request.state.tenant_slug = slug
    return {"tenant_id": tid, "tenant_slug": slug}


@router.get("/email-config/microsoft/oauth-status", response_model=MicrosoftOAuthStatusOut)
async def microsoft_oauth_status(
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
):
    """True if MICROSOFT_CLIENT_ID is set on the API — use before starting browser OAuth."""
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Admin role required")
    cid = (settings.microsoft_client_id or "").strip()
    return MicrosoftOAuthStatusOut(oauth_configured=bool(cid))


@router.get("/email-config/microsoft/authorize")
async def microsoft_authorize(
    tenant_id: int = Depends(require_tenant),
    tenant_slug: str = Depends(require_tenant_slug),
    current_user: CurrentUser = Depends(get_current_user),
):
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Admin role required")
    if not settings.microsoft_client_id:
        raise HTTPException(
            status_code=503,
            detail="Microsoft 365 integration is not configured. Contact your administrator.",
        )
    redirect_uri = _microsoft_platform_callback_url()
    state = make_ms_state(tenant_id, tenant_slug)
    try:
        url = build_microsoft_authorize_url(redirect_uri=redirect_uri, state=state)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return RedirectResponse(url=url, status_code=302)


@router.get("/email-config/microsoft/callback")
async def microsoft_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    callback_ctx: dict | RedirectResponse = Depends(_microsoft_callback_ctx),
    current_user: CurrentUser = Depends(get_current_user),
):
    if isinstance(callback_ctx, RedirectResponse):
        return callback_ctx
    if not isinstance(callback_ctx, dict) or "tenant_id" not in callback_ctx or "tenant_slug" not in callback_ctx:
        base = settings.base_domain or "truckerp.me"
        return RedirectResponse(url=f"https://{base}/?ms_error=invalid_state", status_code=302)
    tid = callback_ctx["tenant_id"]
    slug = callback_ctx["tenant_slug"]
    return_url = _return_url(slug)
    if not code:
        code = request.query_params.get("code")
    if not state:
        state = request.query_params.get("state")
    if error:
        return RedirectResponse(url=f"{return_url}?ms_error={error}", status_code=302)
    if not code or not state:
        return RedirectResponse(url=f"{return_url}?ms_error=missing_params", status_code=302)
    if not current_user or not is_tenant_admin(current_user.role):
        return RedirectResponse(url=f"{return_url}?ms_error=unauthorized", status_code=302)
    redirect_uri = _microsoft_platform_callback_url()
    try:
        tokens = await exchange_ms_code_for_tokens(code=code, redirect_uri=redirect_uri)
    except Exception:
        return RedirectResponse(url=f"{return_url}?ms_error=token_exchange_failed", status_code=302)
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")

    async for tenant_db in open_tenant_session_by_id(int(tid)):
        existing = await tenant_db.scalar(
            select(TenantEmailAccount)
            .where(
                TenantEmailAccount.tenant_id == int(tid),
                TenantEmailAccount.provider == PROVIDER_MICROSOFT365,
            )
            .limit(1)
        )
        if not refresh_token and existing:
            try:
                refresh_token = decrypt_secret(existing.refresh_token_encrypted).decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                pass
        if not access_token or not refresh_token:
            return RedirectResponse(url=f"{return_url}?ms_error=no_refresh_token", status_code=302)

        profile = await graph_get_me_profile(access_token)
        mail = (profile.get("mail") or profile.get("userPrincipalName") or "").strip() or None
        oid = str(profile.get("id") or "").strip() or None

        expires_in = tokens.get("expires_in")
        token_expiry_at = None
        if expires_in is not None and isinstance(expires_in, (int, float)):
            token_expiry_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
        scope_str = tokens.get("scope")
        access_enc = encrypt_secret(access_token)
        refresh_enc = encrypt_secret(refresh_token)
        user_id = str(current_user.user.id)
        if existing:
            existing.access_token_encrypted = access_enc
            existing.refresh_token_encrypted = refresh_enc
            existing.token_expiry_at = token_expiry_at
            existing.scope = scope_str
            existing.status = "CONNECTED"
            existing.email_address = mail or existing.email_address
            existing.provider_account_id = oid
            existing.last_error = None
            existing.connected_by_user_id = user_id
            existing.updated_at = datetime.now(timezone.utc)
            acc = existing
        else:
            acc = TenantEmailAccount(
                tenant_id=int(tid),
                provider=PROVIDER_MICROSOFT365,
                email_address=mail,
                status="CONNECTED",
                access_token_encrypted=access_enc,
                refresh_token_encrypted=refresh_enc,
                token_expiry_at=token_expiry_at,
                scope=scope_str,
                is_primary=True,
                connected_by_user_id=user_id,
                provider_account_id=oid,
            )
            tenant_db.add(acc)
        await tenant_db.flush()
        try:
            await ensure_microsoft_subscription(tenant_db, int(tid), acc, access_token=access_token)
        except Exception as exc:
            logger.warning("microsoft subscription create failed: %s", exc)
            acc.ms_graph_last_sync_error = (str(exc) or "subscription_failed")[:2000]
        await tenant_db.commit()
        break

    return RedirectResponse(url=f"{return_url}?microsoft365=connected", status_code=302)


@router.post("/email-config/microsoft/renew-subscription")
async def microsoft_renew_subscription_route(
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    tenant_db: AsyncSession = Depends(get_tenant_db),
    force: bool = Query(False),
):
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Admin role required")
    acc = await tenant_db.scalar(
        select(TenantEmailAccount)
        .where(
            TenantEmailAccount.tenant_id == tenant_id,
            TenantEmailAccount.provider == PROVIDER_MICROSOFT365,
        )
        .limit(1)
    )
    if not acc:
        raise HTTPException(status_code=404, detail="No Microsoft 365 account connected")
    try:
        ok = await renew_microsoft_subscription_if_due(
            tenant_db, tenant_id, acc, renew_within_hours=0 if force else 12, force=force
        )
        return {"ok": True, "renewed": ok}
    except Exception as e:
        logger.exception("microsoft_renew_subscription_failed tenant_id=%s", tenant_id)
        raise HTTPException(
            status_code=502, detail="Microsoft subscription renew failed"
        ) from e


@router.post("/email-config/microsoft/sync-now")
async def microsoft_sync_now(
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    tenant_db: AsyncSession = Depends(get_tenant_db),
    max_pages: int = Query(25, ge=1, le=100),
):
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Admin role required")
    try:
        r = await sync_microsoft_delta_for_tenant(tenant_db, tenant_id, max_pages=max_pages)
        return {
            "ok": True,
            "tenant_id": r.tenant_id,
            "provider": r.provider,
            "messages_processed": r.messages_processed,
            "delta_pages": r.delta_pages,
            "delta_cursor_advanced": r.delta_cursor_advanced,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("microsoft_sync_failed tenant_id=%s", tenant_id)
        raise HTTPException(status_code=502, detail="Microsoft sync failed") from e


@router.post("/email-config/primary/disconnect")
async def disconnect_primary_email_config(
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    tenant_db: AsyncSession = Depends(get_tenant_db),
    platform_db: AsyncSession = Depends(get_db),
):
    """Disconnect primary mailbox. Clears stored credentials; mailbox record removed or reset."""
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Admin role required")

    row = await tenant_db.scalar(
        select(TenantEmailMailbox)
        .where(TenantEmailMailbox.tenant_id == tenant_id, TenantEmailMailbox.is_primary == True)
        .limit(1)
    )
    if row:
        if row.credential_ref:
            secret_row = await platform_db.scalar(
                select(TenantIntegrationSecret).where(
                    TenantIntegrationSecret.credential_ref == row.credential_ref,
                    TenantIntegrationSecret.tenant_id == tenant_id,
                ).limit(1)
            )
            if secret_row:
                await platform_db.delete(secret_row)
        await tenant_db.delete(row)
        await platform_db.commit()
        await tenant_db.commit()
        return {"ok": True, "message": "Mailbox disconnected"}

    ms_acc = await tenant_db.scalar(
        select(TenantEmailAccount)
        .where(TenantEmailAccount.tenant_id == tenant_id, TenantEmailAccount.provider == PROVIDER_MICROSOFT365)
        .limit(1)
    )
    if ms_acc:
        try:
            await stop_microsoft_subscription_safe(tenant_db, ms_acc)
        except Exception as exc:
            logger.warning("microsoft disconnect cleanup: %s", exc)
        await tenant_db.delete(ms_acc)
        await platform_db.commit()
        await tenant_db.commit()
        return {"ok": True, "message": "Mailbox disconnected"}

    # Gmail OAuth (V1): check tenant_email_accounts
    gmail_acc = await tenant_db.scalar(
        select(TenantEmailAccount)
        .where(TenantEmailAccount.tenant_id == tenant_id, TenantEmailAccount.provider == "gmail")
        .limit(1)
    )
    if gmail_acc:
        await delete_gmail_mailbox_mappings_for_tenant(platform_db, tenant_id=tenant_id)
        await stop_gmail_watch_for_tenant(tenant_db, tenant_id)
        await tenant_db.delete(gmail_acc)
        await platform_db.commit()
        await tenant_db.commit()
        return {"ok": True, "message": "Mailbox disconnected"}

    return {"ok": True, "message": "No mailbox to disconnect"}


@router.get("/email-config/primary", response_model=EmailConfigOut | None)
async def get_primary_email_config(
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Get primary mailbox config. Secrets never returned. Surfaces Gmail from tenant_email_accounts when no mailbox row."""
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Admin role required")

    row = await db.scalar(
        select(TenantEmailMailbox)
        .where(TenantEmailMailbox.tenant_id == tenant_id, TenantEmailMailbox.is_primary == True)
        .limit(1)
    )
    if row:
        return _mailbox_to_out(row)
    ms = await db.scalar(
        select(TenantEmailAccount)
        .where(TenantEmailAccount.tenant_id == tenant_id, TenantEmailAccount.provider == PROVIDER_MICROSOFT365)
        .limit(1)
    )
    if ms:
        return _microsoft_account_to_out(ms)
    gmail = await db.scalar(
        select(TenantEmailAccount)
        .where(TenantEmailAccount.tenant_id == tenant_id, TenantEmailAccount.provider == "gmail")
        .limit(1)
    )
    if gmail:
        return _gmail_account_to_out(gmail)
    return None


@router.put("/email-config/primary", response_model=EmailConfigOut)
async def upsert_primary_email_config(
    payload: EmailConfigUpdate,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    tenant_db: AsyncSession = Depends(get_tenant_db),
    platform_db: AsyncSession = Depends(get_db),
):
    """Create or update primary mailbox config. Credentials encrypted in platform DB."""
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Admin role required")
    if payload.connection_mode == "oauth" and payload.mailbox_type not in ("gmail", "microsoft365"):
        raise HTTPException(
            status_code=400,
            detail="OAuth is only available for Gmail or Microsoft 365. Use Connect buttons, or manual IMAP/SMTP for other providers.",
        )

    row = await tenant_db.scalar(
        select(TenantEmailMailbox)
        .where(TenantEmailMailbox.tenant_id == tenant_id, TenantEmailMailbox.is_primary == True)
        .limit(1)
    )
    # Snapshot for split-commit diagnostics (tenant row may be replaced below for first-time create).
    prev_credential_ref: str | None = row.credential_ref if row else None
    secret_platform_action: str = "none"

    mbox_type = (payload.mailbox_type or EMAIL_PROVIDER_OTHER).strip().lower()
    if mbox_type == "imap":
        mbox_type = EMAIL_PROVIDER_OTHER

    existing_json: dict = {}
    if row and row.credential_ref:
        sr0 = await platform_db.scalar(
            select(TenantIntegrationSecret).where(
                TenantIntegrationSecret.credential_ref == row.credential_ref,
                TenantIntegrationSecret.tenant_id == tenant_id,
            ).limit(1)
        )
        if sr0:
            existing_json = load_mailbox_secret_json(sr0)

    merged_secret = _merge_secret_payload(payload, existing_json)
    need_secret_write = bool(
        payload.imap_password
        or payload.smtp_password
        or payload.oauth_access_token
        or payload.oauth_refresh_token
    )
    new_credential_ref: str | None = None

    secret_platform_value = EMAIL_PROVIDER_OTHER if mbox_type == EMAIL_PROVIDER_OTHER else (mbox_type or "imap")

    if need_secret_write and merged_secret:
        plaintext = json.dumps(merged_secret)
        encrypted = encrypt_secret(plaintext)

        if row and row.credential_ref:
            secret_row = await platform_db.scalar(
                select(TenantIntegrationSecret).where(
                    TenantIntegrationSecret.credential_ref == row.credential_ref,
                    TenantIntegrationSecret.tenant_id == tenant_id,
                ).limit(1)
            )
            if secret_row:
                secret_row.encrypted_payload = encrypted
                secret_row.provider = secret_platform_value
                secret_row.updated_at = datetime.now(timezone.utc)
                secret_platform_action = "update_in_place"
            else:
                cred_ref = generate_credential_ref()
                secret_row = TenantIntegrationSecret(
                    tenant_id=tenant_id,
                    integration_type="email_mailbox",
                    provider=secret_platform_value,
                    credential_ref=cred_ref,
                    encrypted_payload=encrypted,
                )
                platform_db.add(secret_row)
                await platform_db.flush()
                new_credential_ref = cred_ref
                secret_platform_action = "insert_new"
        else:
            cred_ref = generate_credential_ref()
            secret_row = TenantIntegrationSecret(
                tenant_id=tenant_id,
                integration_type="email_mailbox",
                provider=secret_platform_value,
                credential_ref=cred_ref,
                encrypted_payload=encrypted,
            )
            platform_db.add(secret_row)
            await platform_db.flush()
            new_credential_ref = cred_ref
            secret_platform_action = "insert_new"

    user_id = str(current_user.user.id)
    now = datetime.now(timezone.utc)

    if row:
        row.email_address = str(payload.email_address)
        row.display_name = payload.display_name
        row.reply_to = payload.reply_to
        row.mailbox_type = mbox_type
        row.provider_name = payload.provider_name
        row.connection_mode = payload.connection_mode
        row.inbound_enabled = payload.inbound_enabled
        row.outbound_enabled = payload.outbound_enabled
        row.is_primary = payload.is_primary
        row.imap_host = payload.imap_host
        row.imap_port = payload.imap_port
        row.imap_username = payload.imap_username
        row.imap_security = payload.imap_security
        row.smtp_host = payload.smtp_host
        row.smtp_port = payload.smtp_port
        row.smtp_username = payload.smtp_username
        row.smtp_security = payload.smtp_security
        row.use_ssl = payload.use_ssl
        row.use_tls = payload.use_tls
        row.oauth_provider = payload.oauth_provider
        row.oauth_account_email = payload.oauth_account_email
        if new_credential_ref:
            row.credential_ref = new_credential_ref
        row.status = "CONFIGURED"
        row.updated_at = now
        row.updated_by = user_id
    else:
        row = TenantEmailMailbox(
            tenant_id=tenant_id,
            credential_ref=new_credential_ref,
            email_address=str(payload.email_address),
            display_name=payload.display_name,
            reply_to=payload.reply_to,
            mailbox_type=mbox_type,
            provider_name=payload.provider_name,
            connection_mode=payload.connection_mode,
            inbound_enabled=payload.inbound_enabled,
            outbound_enabled=payload.outbound_enabled,
            is_primary=payload.is_primary,
            imap_host=payload.imap_host,
            imap_port=payload.imap_port,
            imap_username=payload.imap_username,
            imap_security=payload.imap_security,
            smtp_host=payload.smtp_host,
            smtp_port=payload.smtp_port,
            smtp_username=payload.smtp_username,
            smtp_security=payload.smtp_security,
            use_ssl=payload.use_ssl,
            use_tls=payload.use_tls,
            oauth_provider=payload.oauth_provider,
            oauth_account_email=payload.oauth_account_email,
            status="CONFIGURED",
            created_by=user_id,
            updated_by=user_id,
        )
        tenant_db.add(row)

    await platform_db.commit()
    try:
        await tenant_db.commit()
    except Exception:
        logger.exception(
            "upsert_primary_email_config split_commit_failure: platform DB committed but tenant "
            "mailbox commit failed (possible cross-DB drift). tenant_id=%s "
            "secret_platform_action=%s prev_credential_ref=%s new_credential_ref=%s "
            "need_secret_write=%s",
            tenant_id,
            secret_platform_action,
            prev_credential_ref,
            new_credential_ref,
            need_secret_write,
        )
        # Safe compensation: tenant never persisted a pointer to this ref; remove orphan secret only.
        if new_credential_ref:
            try:
                orphan = await platform_db.scalar(
                    select(TenantIntegrationSecret).where(
                        TenantIntegrationSecret.tenant_id == tenant_id,
                        TenantIntegrationSecret.credential_ref == new_credential_ref,
                    ).limit(1)
                )
                if orphan:
                    await platform_db.delete(orphan)
                    await platform_db.commit()
                    logger.warning(
                        "upsert_primary_email_config: removed orphan TenantIntegrationSecret after "
                        "tenant commit failure tenant_id=%s credential_ref=%s",
                        tenant_id,
                        new_credential_ref,
                    )
            except Exception:
                logger.exception(
                    "upsert_primary_email_config: orphan secret cleanup failed tenant_id=%s "
                    "credential_ref=%s",
                    tenant_id,
                    new_credential_ref,
                )
        try:
            await tenant_db.rollback()
        except Exception:
            logger.exception(
                "upsert_primary_email_config: tenant rollback failed tenant_id=%s",
                tenant_id,
            )
        raise

    await tenant_db.refresh(row)
    return _mailbox_to_out(row)


@router.post("/email-config/primary/test", response_model=EmailConfigTestOut)
async def test_primary_email_config(
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    tenant_db: AsyncSession = Depends(get_tenant_db),
    platform_db: AsyncSession = Depends(get_db),
):
    """Test connection to primary mailbox. Updates last_tested_at and last_test_status."""
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Admin role required")

    now = datetime.now(timezone.utc)
    row = await tenant_db.scalar(
        select(TenantEmailMailbox)
        .where(TenantEmailMailbox.tenant_id == tenant_id, TenantEmailMailbox.is_primary == True)
        .limit(1)
    )
    if not row:
        # Gmail OAuth (V1): check tenant_email_accounts
        gmail_acc = await tenant_db.scalar(
            select(TenantEmailAccount)
            .where(TenantEmailAccount.tenant_id == tenant_id, TenantEmailAccount.provider == "gmail")
            .limit(1)
        )
        if gmail_acc:
            try:
                refresh_token = decrypt_secret(gmail_acc.refresh_token_encrypted).decode("utf-8")
                tok = await refresh_access_token(refresh_token)
                access = tok.get("access_token")
                if access:
                    await get_user_email(access)
                    gmail_acc.status = "CONNECTED"
                    gmail_acc.last_error = None
                else:
                    gmail_acc.status = "ERROR"
                    gmail_acc.last_error = "No OAuth tokens stored"
            except Exception:
                logger.exception(
                    "email_mailbox_test_failed route=test_primary_email_config branch=gmail_oauth "
                    "tenant_id=%s",
                    tenant_id,
                )
                gmail_acc.status = "ERROR"
                gmail_acc.last_error = _MAILBOX_TEST_MSG_OAUTH
            await tenant_db.commit()
            return EmailConfigTestOut(
                ok=gmail_acc.status == "CONNECTED",
                status=gmail_acc.status,
                message=gmail_acc.last_error,
                last_tested_at=now.isoformat(),
            )
        raise HTTPException(status_code=404, detail="No primary mailbox configured")

    row.status = "TESTING"
    row.last_tested_at = now

    imap_password = None
    secret_row = None
    if row.credential_ref:
        secret_row = await platform_db.scalar(
            select(TenantIntegrationSecret).where(
                TenantIntegrationSecret.credential_ref == row.credential_ref,
                TenantIntegrationSecret.tenant_id == tenant_id,
            ).limit(1)
        )
        if secret_row:
            try:
                dec = decrypt_secret(secret_row.encrypted_payload)
                data = json.loads(dec.decode("utf-8"))
                imap_password = data.get("imap_password")
            except ValueError:
                row.last_test_status = "ERROR"
                row.last_error_message = "Failed to decrypt credentials"
                row.status = "ERROR"
                await tenant_db.commit()
                return EmailConfigTestOut(ok=False, status="ERROR", message=row.last_error_message, last_tested_at=now.isoformat())

    if row.connection_mode == "manual" and row.imap_host and row.imap_username:
        if not imap_password:
            row.last_test_status = "ERROR"
            row.last_error_message = "No password stored for manual IMAP"
            row.status = "ERROR"
        else:
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: imap_test_connection_sync(row, imap_password),
                )
                row.last_test_status = "CONNECTED"
                row.last_error_code = None
                row.last_error_message = None
                row.status = "CONNECTED"
                row.last_inbound_test_at = now
                row.connection_status = "CONNECTED"
            except Exception:
                logger.exception(
                    "email_mailbox_test_failed route=test_primary_email_config branch=manual_imap "
                    "tenant_id=%s",
                    tenant_id,
                )
                row.last_test_status = "ERROR"
                row.last_error_message = _MAILBOX_TEST_MSG_MAIL_SERVER
                row.status = "ERROR"
                row.connection_status = "ERROR"
    elif row.connection_mode == "oauth" and row.credential_ref:
        try:
            dec = decrypt_secret(secret_row.encrypted_payload) if secret_row else b"{}"
            data = json.loads(dec.decode("utf-8"))
            refresh = data.get("oauth_refresh_token")
            access = data.get("oauth_access_token")
            if refresh:
                tok = await refresh_access_token(refresh)
                access = tok.get("access_token")
            if access:
                await get_user_email(access)
                row.last_test_status = "CONNECTED"
                row.last_error_code = None
                row.last_error_message = None
                row.status = "CONNECTED"
            else:
                row.last_test_status = "ERROR"
                row.last_error_message = "No OAuth tokens stored"
                row.status = "ERROR"
        except Exception:
            logger.exception(
                "email_mailbox_test_failed route=test_primary_email_config branch=mailbox_oauth_secret "
                "tenant_id=%s",
                tenant_id,
            )
            row.last_test_status = "ERROR"
            row.last_error_message = "OAuth token refresh or validation failed"
            row.status = "ERROR"
    elif row.connection_mode == "oauth":
        row.last_test_status = "ERROR"
        row.last_error_message = "No OAuth credentials stored. Reconnect Gmail."
        row.status = "CONFIGURED"
    else:
        row.last_test_status = "SKIPPED"
        row.last_error_message = "Incomplete manual config (IMAP host and username required)"
        row.status = "CONFIGURED"

    await tenant_db.commit()
    return EmailConfigTestOut(
        ok=row.last_test_status == "CONNECTED",
        status=row.last_test_status,
        direction="inbound" if row.connection_mode == "manual" else None,
        message=row.last_error_message,
        last_tested_at=row.last_tested_at.isoformat() if row.last_tested_at else None,
    )


@router.post("/email-config/primary/test-inbound", response_model=EmailConfigTestOut)
async def test_primary_inbound_only(
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    tenant_db: AsyncSession = Depends(get_tenant_db),
    platform_db: AsyncSession = Depends(get_db),
):
    """Test IMAP (inbound) for manual Other mailbox. Does not test SMTP."""
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Admin role required")

    row = await tenant_db.scalar(
        select(TenantEmailMailbox)
        .where(TenantEmailMailbox.tenant_id == tenant_id, TenantEmailMailbox.is_primary == True)
        .limit(1)
    )
    if not row:
        raise HTTPException(status_code=404, detail="No primary mailbox configured")
    mtype = (row.mailbox_type or "").strip().lower()
    if mtype not in (EMAIL_PROVIDER_OTHER, "imap"):
        raise HTTPException(
            status_code=400,
            detail="Inbound IMAP test applies to Other email provider mailboxes only",
        )
    if row.connection_mode != "manual" or not row.imap_host or not row.imap_username:
        raise HTTPException(status_code=400, detail="IMAP host and username required")

    now = datetime.now(timezone.utc)
    imap_password: str | None = None
    if row.credential_ref:
        secret_row = await platform_db.scalar(
            select(TenantIntegrationSecret).where(
                TenantIntegrationSecret.credential_ref == row.credential_ref,
                TenantIntegrationSecret.tenant_id == tenant_id,
            ).limit(1)
        )
        if secret_row:
            data = load_mailbox_secret_json(secret_row)
            imap_password = data.get("imap_password")

    if not imap_password:
        row.last_inbound_test_at = now
        row.last_error_message = "No IMAP password stored"
        row.connection_status = "ERROR"
        await tenant_db.commit()
        return EmailConfigTestOut(
            ok=False,
            status="ERROR",
            direction="inbound",
            message=row.last_error_message,
            last_tested_at=now.isoformat(),
        )

    try:
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: imap_test_connection_sync(row, imap_password),
        )
        row.last_inbound_test_at = now
        row.last_tested_at = now
        row.last_test_status = "CONNECTED"
        row.last_error_code = None
        row.last_error_message = None
        row.connection_status = "CONNECTED"
        row.status = "CONNECTED"
    except Exception:
        logger.exception(
            "email_mailbox_test_failed route=test_primary_inbound_only branch=imap tenant_id=%s",
            tenant_id,
        )
        row.last_inbound_test_at = now
        row.last_test_status = "ERROR"
        row.last_error_message = _MAILBOX_TEST_MSG_MAIL_SERVER
        row.connection_status = "ERROR"
        row.status = "ERROR"

    await tenant_db.commit()
    return EmailConfigTestOut(
        ok=row.last_test_status == "CONNECTED",
        status=row.last_test_status or "ERROR",
        direction="inbound",
        message=row.last_error_message,
        last_tested_at=now.isoformat(),
    )


@router.post("/email-config/primary/test-outbound", response_model=EmailConfigTestOut)
async def test_primary_outbound_only(
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    tenant_db: AsyncSession = Depends(get_tenant_db),
    platform_db: AsyncSession = Depends(get_db),
):
    """Test SMTP (outbound) for manual Other mailbox."""
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Admin role required")

    row = await tenant_db.scalar(
        select(TenantEmailMailbox)
        .where(TenantEmailMailbox.tenant_id == tenant_id, TenantEmailMailbox.is_primary == True)
        .limit(1)
    )
    if not row:
        raise HTTPException(status_code=404, detail="No primary mailbox configured")
    mtype = (row.mailbox_type or "").strip().lower()
    if mtype not in (EMAIL_PROVIDER_OTHER, "imap"):
        raise HTTPException(
            status_code=400,
            detail="Outbound SMTP test applies to Other email provider mailboxes only",
        )
    if row.connection_mode != "manual" or not row.smtp_host or not row.smtp_username:
        raise HTTPException(status_code=400, detail="SMTP host and username required")

    now = datetime.now(timezone.utc)
    smtp_password: str | None = None
    if row.credential_ref:
        secret_row = await platform_db.scalar(
            select(TenantIntegrationSecret).where(
                TenantIntegrationSecret.credential_ref == row.credential_ref,
                TenantIntegrationSecret.tenant_id == tenant_id,
            ).limit(1)
        )
        if secret_row:
            data = load_mailbox_secret_json(secret_row)
            smtp_password = data.get("smtp_password")

    if not smtp_password:
        row.last_outbound_test_at = now
        row.last_error_message = "No SMTP password stored"
        row.connection_status = "ERROR"
        await tenant_db.commit()
        return EmailConfigTestOut(
            ok=False,
            status="ERROR",
            direction="outbound",
            message=row.last_error_message,
            last_tested_at=now.isoformat(),
        )

    try:
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: smtp_test_connection_sync(row, smtp_password),
        )
        row.last_outbound_test_at = now
        row.last_error_message = None
        row.connection_status = row.connection_status or "CONNECTED"
    except Exception:
        logger.exception(
            "email_mailbox_test_failed route=test_primary_outbound_only branch=smtp tenant_id=%s",
            tenant_id,
        )
        row.last_outbound_test_at = now
        row.last_error_message = _MAILBOX_TEST_MSG_MAIL_SERVER
        row.connection_status = "ERROR"

    await tenant_db.commit()
    ok = row.last_error_message is None
    return EmailConfigTestOut(
        ok=ok,
        status="CONNECTED" if ok else "ERROR",
        direction="outbound",
        message=row.last_error_message,
        last_tested_at=now.isoformat(),
    )


@router.post("/email-config/other/sync-now")
async def other_imap_sync_now(
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    tenant_db: AsyncSession = Depends(get_tenant_db),
    platform_db: AsyncSession = Depends(get_db),
    max_messages: int = 50,
):
    """
    Operator-only incremental IMAP sync for Other / domain mailbox (shared engine; not Gmail/Graph).
    Same ingestion path a future scheduler would call.
    """
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Admin role required")
    if max_messages < 1 or max_messages > 200:
        raise HTTPException(status_code=400, detail="max_messages must be between 1 and 200")
    try:
        result = await sync_other_imap_inbox_for_tenant(
            tenant_db,
            platform_db,
            tenant_id,
            max_messages=max_messages,
        )
        return {
            "ok": True,
            "tenant_id": result.tenant_id,
            "provider": result.provider,
            "threads_upserted": result.threads_upserted,
            "messages_upserted": result.messages_upserted,
            "attachments_upserted": result.attachments_upserted,
            "uids_fetched": result.uids_fetched,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("other_imap_sync_failed tenant_id=%s", tenant_id)
        raise HTTPException(status_code=502, detail="IMAP sync failed") from e


@router.post("/email-config/gmail/register-watch")
async def gmail_register_watch(
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    tenant_db: AsyncSession = Depends(get_tenant_db),
):
    """Register or replace Gmail users.watch for this tenant (requires GMAIL_PUBSUB_TOPIC_NAME)."""
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Admin role required")
    topic = getattr(settings, "gmail_pubsub_topic_name", None)
    if not topic or not str(topic).strip():
        raise HTTPException(
            status_code=503,
            detail="GMAIL_PUBSUB_TOPIC_NAME is not configured (e.g. projects/PROJECT/topics/TOPIC).",
        )
    try:
        return await register_or_renew_gmail_watch_for_tenant(tenant_db, tenant_id, topic_name=str(topic).strip())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except httpx.HTTPStatusError as e:
        body_preview = (e.response.text or "")[:500]
        logger.warning(
            "gmail_register_watch users.watch HTTP error tenant_id=%s status=%s body_preview=%r",
            tenant_id,
            e.response.status_code,
            body_preview,
            exc_info=True,
        )
        try:
            acc = await tenant_db.scalar(
                select(TenantEmailAccount)
                .where(TenantEmailAccount.tenant_id == tenant_id, TenantEmailAccount.provider == "gmail")
                .limit(1)
            )
            if acc:
                acc.last_error = _GMAIL_ACCOUNT_LAST_ERROR_WATCH_REJECTED
                await tenant_db.commit()
        except Exception:
            logger.exception(
                "gmail_register_watch: persist last_error failed tenant_id=%s",
                tenant_id,
            )
        raise HTTPException(status_code=502, detail="Gmail users.watch rejected") from e


@router.post("/email-config/gmail/renew-watch")
async def gmail_renew_watch(
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    tenant_db: AsyncSession = Depends(get_tenant_db),
    force: bool = Query(False, description="If true, call users.watch even if expiration is still far ahead"),
):
    """Renew Gmail watch before expiration (default: only if within gmail_watch_renew_within_hours)."""
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Admin role required")
    topic = getattr(settings, "gmail_pubsub_topic_name", None)
    if not topic or not str(topic).strip():
        raise HTTPException(status_code=503, detail="GMAIL_PUBSUB_TOPIC_NAME is not configured")
    acc = await tenant_db.scalar(
        select(TenantEmailAccount)
        .where(TenantEmailAccount.tenant_id == tenant_id, TenantEmailAccount.provider == "gmail")
        .limit(1)
    )
    if not acc:
        raise HTTPException(status_code=404, detail="No Gmail account connected")
    now = datetime.now(timezone.utc)
    within = max(1, int(getattr(settings, "gmail_watch_renew_within_hours", 48)))
    threshold = now + timedelta(hours=within)
    exp = acc.gmail_watch_expiration_at
    if not force and exp and exp > threshold:
        return {
            "ok": True,
            "skipped": "not_due",
            "gmail_watch_expires_at": exp.isoformat(),
            "renew_within_hours": within,
        }
    try:
        return await register_or_renew_gmail_watch_for_tenant(tenant_db, tenant_id, topic_name=str(topic).strip())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except httpx.HTTPStatusError as e:
        body_preview = (e.response.text or "")[:500]
        logger.warning(
            "gmail_renew_watch users.watch HTTP error tenant_id=%s status=%s body_preview=%r",
            tenant_id,
            e.response.status_code,
            body_preview,
            exc_info=True,
        )
        try:
            acc2 = await tenant_db.scalar(
                select(TenantEmailAccount)
                .where(TenantEmailAccount.tenant_id == tenant_id, TenantEmailAccount.provider == "gmail")
                .limit(1)
            )
            if acc2:
                acc2.last_error = _GMAIL_ACCOUNT_LAST_ERROR_WATCH_REJECTED
                await tenant_db.commit()
        except Exception:
            logger.exception(
                "gmail_renew_watch: persist last_error failed tenant_id=%s",
                tenant_id,
            )
        raise HTTPException(status_code=502, detail="Gmail users.watch rejected") from e


@router.post("/email-config/gmail/sync-now")
async def gmail_sync_now(
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    tenant_db: AsyncSession = Depends(get_tenant_db),
    max_threads: int = 30,
):
    """
    Secondary / operator Gmail delta sync (History API only) — same code path as Pub/Sub push.
    Production ingestion must work without calling this; keep for break-glass and troubleshooting.
    """
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Admin role required")
    if max_threads < 1 or max_threads > 200:
        raise HTTPException(status_code=400, detail="max_threads must be between 1 and 200")
    try:
        result = await sync_gmail_inbox_for_tenant(tenant_db, tenant_id=tenant_id, max_threads=max_threads)
        acc_row = await tenant_db.scalar(
            select(TenantEmailAccount)
            .where(TenantEmailAccount.tenant_id == tenant_id, TenantEmailAccount.provider == "gmail")
            .limit(1)
        )
        last_sync = acc_row.last_sync_at.isoformat() if acc_row and acc_row.last_sync_at else None
        return {
            "ok": True,
            "tenant_id": result.tenant_id,
            "provider": result.provider,
            "threads_scanned": result.threads_scanned,
            "threads_upserted": result.threads_upserted,
            "messages_upserted": result.messages_upserted,
            "attachments_upserted": result.attachments_upserted,
            "history_pages": result.history_pages,
            "last_sync_at": last_sync,
        }
    except Exception as e:
        logger.exception("gmail_sync_now failed tenant_id=%s", tenant_id)
        try:
            acc = await tenant_db.scalar(
                select(TenantEmailAccount)
                .where(TenantEmailAccount.tenant_id == tenant_id, TenantEmailAccount.provider == "gmail")
                .limit(1)
            )
            if acc:
                acc.last_error = _GMAIL_ACCOUNT_LAST_ERROR_SYNC_FAILED
                await tenant_db.commit()
        except Exception:
            logger.exception(
                "gmail_sync_now: persist last_error failed tenant_id=%s",
                tenant_id,
            )
        raise HTTPException(status_code=502, detail="Gmail sync failed") from e
