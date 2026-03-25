TENANT_AUTH_PLATFORM = "platform"
TENANT_AUTH_TENANT = "tenant"


def tenant_uses_tenant_db_auth(mode: str | None) -> bool:
    return (mode or TENANT_AUTH_PLATFORM).lower() == TENANT_AUTH_TENANT
