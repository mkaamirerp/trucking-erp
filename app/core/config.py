import os
from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict

# ENVIRONMENT values where tenant-resolution shortcuts may be enabled (requires ALLOW_TENANT_RESOLUTION_SHORTCUTS).
TENANT_RESOLUTION_SHORTCUT_SAFE_ENVIRONMENTS: frozenset[str] = frozenset(
    {"dev", "development", "test", "testing", "ci", "local"}
)


def _validate_database_url(url: str, name: str) -> None:
    if not url:
        raise RuntimeError(f"{name} is empty")

    parsed = urlparse(url)

    if not parsed.hostname:
        raise RuntimeError(
            f"{name} has no hostname. Bad URL: {url}\n"
            "Example expected: postgresql://user:pass@host:5432/db"
        )

    if parsed.hostname in ("localhost", "127.0.0.1", "::1"):
        raise RuntimeError(
            f"{name} points to localhost which is forbidden in Docker runtime.\n"
            f"URL: {url}"
        )


class Settings(BaseSettings):
    app_name: str = "Trucking ERP API"
    environment: str = "dev"

    # Opt-in: JWT-without-subdomain resolution, TOOLS_DEFAULT_*, tools routes, TEST_BYPASS_AUTH.
    # Must also set ENVIRONMENT to a value in TENANT_RESOLUTION_SHORTCUT_SAFE_ENVIRONMENTS.
    allow_tenant_resolution_shortcuts: bool = False

    def is_production(self) -> bool:
        return (self.environment or "").lower() in ("production", "prod", "prd")

    def allows_tenant_resolution_shortcuts(self) -> bool:
        """
        Explicit allow flag AND environment allowlist only. Never implicit “not prod”.
        Used for: /api/v1/tools routes, JWT tenant without host slug, TOOLS_DEFAULT_TENANT_*,
        and TEST_BYPASS_AUTH (middleware) together with startup checks.
        """
        if not self.allow_tenant_resolution_shortcuts:
            return False
        e = (self.environment or "").lower().strip()
        return e in TENANT_RESOLUTION_SHORTCUT_SAFE_ENVIRONMENTS

    # Canonical DB URL (loaded from .env as DATABASE_URL)
    database_url: str
    # Privileged Postgres URL to create tenant DBs; falls back to database_url if unset
    postgres_admin_url: str | None = None
    # Tenant DB app user credentials (shared, no per-tenant secrets stored in DB)
    tenant_db_app_user: str | None = None
    tenant_db_app_password: str | None = None
    # Tenant alembic target revision for provisioning; use "head" to always run current migrations
    tenant_alembic_target_rev: str = "head"
    # Auth
    jwt_secret: str = "dev-change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_minutes: int = 30
    jwt_refresh_days: int = 14
    cookie_domain: str | None = None
    secure_cookies: bool = False
    jwt_same_site: str = "lax"
    base_domain: str = "truckerp.me"

    # Cloudflare Turnstile (optional). When unset, login human-verification step is skipped (dev).
    # When set, POST /auth/login may require a valid site token after repeated password failures.
    turnstile_secret_key: str | None = None
    # Public site key (safe for browsers). Set alongside turnstile_secret_key in prod; also exposed via GET /public/tenant/{slug}.
    turnstile_site_key: str | None = None

    # Emergency/test only: force login step-up for every attempt (bypass armed-streak rule). Product uses per-attempt rule in login_step_up_otp.py.
    login_step_up_otp_required: bool = False

    # HMAC secret for httpOnly trk_login_trust cookie (familiar-device UX only). Set in production/staging via SSM (e.g. LOGIN_TRUST_COOKIE_SECRET).
    # Never use jwt_secret for this in production — see login_trust_cookie.py.
    login_trust_cookie_secret: str | None = None
    # Dev-only explicit escape hatch: if True AND login_trust_cookie_secret is empty AND not production/staging, signing uses jwt_secret for local/docker dev.
    login_trust_cookie_dev_fallback_to_jwt: bool = False

    # Platform control-plane API (/api/v1/platform/*). Required in production/staging when set; enforced when set in dev.
    platform_admin_api_key: str | None = None

    # Integration secrets (email mailbox OAuth/IMAP credentials in platform DB)
    integration_secret_encryption_key: str | None = None

    # Google OAuth for Gmail (fixed platform callback; no wildcard redirect URIs)
    google_client_id: str | None = None
    google_client_secret: str | None = None
    gmail_oauth_callback_url: str | None = None  # e.g. https://truckerp.me/api/v1/admin/email-config/gmail/callback
    gmail_oauth_return_path: str = "/admin/settings/email"  # frontend path for post-OAuth redirect
    # Pub/Sub → POST /api/v1/webhooks/gmail/pubsub
    # OIDC: set to the exact push URL configured as the subscription audience (HTTPS).
    gmail_pubsub_push_audience: str | None = None
    # Optional second factor: header X-TruckERP-Gmail-Push-Token must also match when set.
    gmail_pubsub_push_token: str | None = None
    # Full topic resource: projects/PROJECT_ID/topics/TOPIC (Gmail users.watch topicName).
    gmail_pubsub_topic_name: str | None = None
    # Renew watches when expiring within this many hours (renewal script / renew endpoint).
    gmail_watch_renew_within_hours: int = 48

    # Microsoft 365 / Graph (OAuth + webhooks). Optional until configured.
    microsoft_client_id: str | None = None
    microsoft_client_secret: str | None = None
    # Azure AD tenant: "common", "organizations", or a specific tenant GUID
    microsoft_authority_tenant: str = "common"
    microsoft_oauth_callback_url: str | None = None  # e.g. https://truckerp.me/api/v1/admin/email-config/microsoft/callback
    # Public HTTPS URL Graph will call (validation + notifications). Must match subscription notificationUrl.
    microsoft_webhook_notification_url: str | None = None
    # HMAC secret for Graph subscription clientState and validation (signs tenant_id). Falls back to jwt_secret if unset.
    microsoft_webhook_client_state_secret: str | None = None

    # Storage (S3 or local)
    storage_provider: str = "local"
    aws_region: str = "us-east-1"
    s3_bucket: str = "truckerp-015421055625-us-east-1-an"
    s3_prefix: str = ""
    local_storage_dir: str | None = None
    company_docs_dir: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()

_validate_database_url(settings.database_url, "DATABASE_URL")
if getattr(settings, "postgres_admin_url", None):
    _validate_database_url(settings.postgres_admin_url, "POSTGRES_ADMIN_URL")


def enforce_test_bypass_auth_policy(cfg: Settings | None = None) -> None:
    """
    Fail fast at application startup if TEST_BYPASS_AUTH is set in an unsafe or incomplete configuration.
    """
    if os.environ.get("TEST_BYPASS_AUTH") != "1":
        return
    s = cfg or settings
    e = (s.environment or "").lower().strip()
    if e not in TENANT_RESOLUTION_SHORTCUT_SAFE_ENVIRONMENTS:
        raise RuntimeError(
            "TEST_BYPASS_AUTH=1 is forbidden unless ENVIRONMENT is in "
            f"{sorted(TENANT_RESOLUTION_SHORTCUT_SAFE_ENVIRONMENTS)!r} (got {s.environment!r}). "
            "Remove TEST_BYPASS_AUTH from this deployment."
        )
    if not s.allow_tenant_resolution_shortcuts:
        raise RuntimeError(
            "TEST_BYPASS_AUTH=1 requires ALLOW_TENANT_RESOLUTION_SHORTCUTS=true and ENVIRONMENT in "
            f"{sorted(TENANT_RESOLUTION_SHORTCUT_SAFE_ENVIRONMENTS)!r}. "
            "Enable only on local or CI test runners."
        )
