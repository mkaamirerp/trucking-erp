from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict


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
