from pydantic_settings import BaseSettings, SettingsConfigDict

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
    # Tenant alembic target revision for provisioning
    tenant_alembic_target_rev: str = "f2d5b4be0ac2"
    # Auth
    jwt_secret: str = "dev-change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_minutes: int = 30
    jwt_refresh_days: int = 14
    cookie_domain: str | None = None
    secure_cookies: bool = False
    jwt_same_site: str = "lax"
    base_domain: str = "truckerp.me"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
