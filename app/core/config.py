from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# .env path from repo root so it's found when running in Docker (CWD may vary)
_env_path = Path(__file__).resolve().parents[2] / ".env"


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
    # Auth (policy via ENV/SSM; no admin panel yet)
    auth_password_login_enabled: bool = True
    auth_mfa_required: bool = False
    jwt_secret: str = "dev-change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_minutes: int = 30
    jwt_refresh_days: int = 14
    cookie_domain: str | None = None
    secure_cookies: bool = False
    jwt_same_site: str = "lax"
    base_domain: str = "truckerp.me"

    model_config = SettingsConfigDict(
        env_file=str(_env_path) if _env_path.exists() else None,
        extra="ignore",
    )

settings = Settings()
