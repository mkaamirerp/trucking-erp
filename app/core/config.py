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
    tenant_alembic_target_rev: str = "5b013e5ac73d"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
