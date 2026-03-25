"""Tenant Admin: primary email mailbox config. One mailbox per tenant in V1.

Secrets are write-only: stored encrypted in platform DB, never in tenant DB,
never returned by GET, never logged. credential_ref enforces tenant ownership
when resolving platform secret records.

Gmail: OAuth-first flow via Connect Gmail.
Other providers: Manual IMAP/SMTP under "Other Email Provider" fallback.

V1 Gmail callback: tenant_email_accounts is the authoritative write target.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.deps.admin import is_tenant_admin
from app.deps.auth import CurrentUser, get_current_user
from app.deps.entitlements import require_entitlement
from app.deps.tenant import require_tenant, require_tenant_slug
from app.deps.tenant_db import get_tenant_db, open_tenant_session_by_id
from app.core.database import get_db
from app.models.email_mailbox import TenantEmailMailbox
from app.models.platform_integration import TenantIntegrationSecret
from app.models.tenant_email_account import TenantEmailAccount
from app.schemas.email_config import EmailConfigOut, EmailConfigUpdate, EmailConfigTestOut
from app.services.gmail_oauth import (
    build_authorize_url,
    exchange_code_for_tokens,
    get_google_userinfo,
    get_user_email,
    make_state,
    parse_state,
    refresh_access_token,
)
from app.services.email_ingestion_gmail import sync_gmail_inbox_for_tenant
from app.utils.encryption import decrypt_secret, encrypt_secret, generate_credential_ref

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["Tenant Admin - Email"],
    dependencies=[Depends(require_entitlement("email_mailbox"))],
)


def _gmail_account_to_out(acc: TenantEmailAccount) -> EmailConfigOut:
    """Map tenant_email_accounts (Gmail OAuth) to EmailConfigOut."""
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
        smtp_host=None,
        smtp_port=None,
        smtp_username=None,
        use_ssl=None,
        use_tls=None,
        oauth_provider="google",
        oauth_account_email=acc.email_address,
        last_tested_at=None,
        last_test_status=None,
        last_error_code=None,
        last_error_message=acc.last_error,
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
        smtp_host=m.smtp_host,
        smtp_port=m.smtp_port,
        smtp_username=m.smtp_username,
        use_ssl=m.use_ssl,
        use_tls=m.use_tls,
        oauth_provider=m.oauth_provider,
        oauth_account_email=m.oauth_account_email,
        last_tested_at=m.last_tested_at,
        last_test_status=m.last_test_status,
        last_error_code=m.last_error_code,
        last_error_message=m.last_error_message,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _build_secret_payload(payload: EmailConfigUpdate) -> dict:
    out: dict = {}
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
        except Exception as e:
            # Keep OAuth connect successful, but store concise identity-fetch diagnostics.
            detail = (str(e) or "Google userinfo request failed").strip()
            identity_fetch_error = f"userinfo_fetch_failed: {detail[:180]}"

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
            if identity_fetch_succeeded:
                existing.email_address = identity_email
                existing.provider_account_id = provider_account_id
                existing.last_error = None
            elif identity_fetch_error:
                existing.last_error = identity_fetch_error
            existing.connected_by_user_id = user_id
            existing.updated_at = datetime.now(timezone.utc)
        else:
            acc = TenantEmailAccount(
                tenant_id=int(tid),
                provider="gmail",
                email_address=identity_email,
                status="CONNECTED",
                access_token_encrypted=access_enc,
                refresh_token_encrypted=refresh_enc,
                token_expiry_at=token_expiry_at,
                scope=scope_str,
                is_primary=True,
                last_error=identity_fetch_error,
                connected_by_user_id=user_id,
                provider_account_id=provider_account_id,
            )
            tenant_db.add(acc)
        await tenant_db.commit()
        return RedirectResponse(url=f"{return_url}?gmail=connected", status_code=302)


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
                platform_db.delete(secret_row)
        tenant_db.delete(row)
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
        tenant_db.delete(gmail_acc)
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
    # Gmail OAuth (V1): check tenant_email_accounts
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
    if payload.connection_mode == "oauth" and payload.mailbox_type != "gmail":
        raise HTTPException(
            status_code=400,
            detail="OAuth is only available for Gmail. Use Connect Gmail button, or manual IMAP/SMTP for other providers.",
        )

    row = await tenant_db.scalar(
        select(TenantEmailMailbox)
        .where(TenantEmailMailbox.tenant_id == tenant_id, TenantEmailMailbox.is_primary == True)
        .limit(1)
    )

    secret_payload = _build_secret_payload(payload)
    new_credential_ref: str | None = None

    if secret_payload:
        plaintext = json.dumps(secret_payload)
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
                secret_row.updated_at = datetime.now(timezone.utc)
            else:
                cred_ref = generate_credential_ref()
                secret_row = TenantIntegrationSecret(
                    tenant_id=tenant_id,
                    integration_type="email_mailbox",
                    provider=payload.mailbox_type or "imap",
                    credential_ref=cred_ref,
                    encrypted_payload=encrypted,
                )
                platform_db.add(secret_row)
                await platform_db.flush()
                new_credential_ref = cred_ref
        else:
            cred_ref = generate_credential_ref()
            secret_row = TenantIntegrationSecret(
                tenant_id=tenant_id,
                integration_type="email_mailbox",
                provider=payload.mailbox_type or "imap",
                credential_ref=cred_ref,
                encrypted_payload=encrypted,
            )
            platform_db.add(secret_row)
            await platform_db.flush()
            new_credential_ref = cred_ref

    user_id = str(current_user.user.id)
    now = datetime.now(timezone.utc)

    if row:
        row.email_address = payload.email_address
        row.display_name = payload.display_name
        row.mailbox_type = payload.mailbox_type or "imap"
        row.provider_name = payload.provider_name
        row.connection_mode = payload.connection_mode
        row.inbound_enabled = payload.inbound_enabled
        row.outbound_enabled = payload.outbound_enabled
        row.imap_host = payload.imap_host
        row.imap_port = payload.imap_port
        row.imap_username = payload.imap_username
        row.smtp_host = payload.smtp_host
        row.smtp_port = payload.smtp_port
        row.smtp_username = payload.smtp_username
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
            email_address=payload.email_address,
            display_name=payload.display_name,
            mailbox_type=payload.mailbox_type or "imap",
            provider_name=payload.provider_name,
            connection_mode=payload.connection_mode,
            inbound_enabled=payload.inbound_enabled,
            outbound_enabled=payload.outbound_enabled,
            imap_host=payload.imap_host,
            imap_port=payload.imap_port,
            imap_username=payload.imap_username,
            smtp_host=payload.smtp_host,
            smtp_port=payload.smtp_port,
            smtp_username=payload.smtp_username,
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
    await tenant_db.commit()
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
            except Exception as e:
                gmail_acc.status = "ERROR"
                gmail_acc.last_error = str(e)[:500]
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
        try:
            import imaplib
            port = row.imap_port or 993
            use_ssl = row.use_ssl if row.use_ssl is not None else (port == 993)
            M = imaplib.IMAP4_SSL if use_ssl else imaplib.IMAP4
            conn = M(row.imap_host, port)
            if not imap_password:
                conn.logout()
                row.last_test_status = "ERROR"
                row.last_error_message = "No password stored for manual IMAP"
                row.status = "ERROR"
            else:
                conn.login(row.imap_username, imap_password)
                conn.logout()
                row.last_test_status = "CONNECTED"
                row.last_error_code = None
                row.last_error_message = None
                row.status = "CONNECTED"
        except Exception as e:
            row.last_test_status = "ERROR"
            row.last_error_message = str(e)[:500]
            row.status = "ERROR"
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
        message=row.last_error_message,
        last_tested_at=row.last_tested_at.isoformat() if row.last_tested_at else None,
    )


@router.post("/email-config/gmail/sync-now")
async def gmail_sync_now(
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    tenant_db: AsyncSession = Depends(get_tenant_db),
    max_threads: int = 30,
):
    """Manual/on-demand Gmail ingestion for current tenant. No scheduler/webhook in this slice."""
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Admin role required")
    if max_threads < 1 or max_threads > 200:
        raise HTTPException(status_code=400, detail="max_threads must be between 1 and 200")
    try:
        result = await sync_gmail_inbox_for_tenant(tenant_db, tenant_id=tenant_id, max_threads=max_threads)
        return {
            "ok": True,
            "tenant_id": result.tenant_id,
            "provider": result.provider,
            "threads_scanned": result.threads_scanned,
            "threads_upserted": result.threads_upserted,
            "messages_upserted": result.messages_upserted,
            "attachments_upserted": result.attachments_upserted,
        }
    except Exception as e:
        # Keep error concise and tenant-scoped diagnostics on account row where possible.
        try:
            acc = await tenant_db.scalar(
                select(TenantEmailAccount)
                .where(TenantEmailAccount.tenant_id == tenant_id, TenantEmailAccount.provider == "gmail")
                .limit(1)
            )
            if acc:
                acc.last_error = f"sync_failed: {(str(e) or 'unknown error')[:240]}"
                await tenant_db.commit()
        except Exception:
            pass
        raise HTTPException(status_code=502, detail="Gmail sync failed") from e
