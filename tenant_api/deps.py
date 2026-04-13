async def get_tenant_db():
    """Placeholder dependency used by CI / signature tests for the ``tenant_api`` package.

    Runtime tenant DB access lives in ``app.deps.tenant_db.get_tenant_db`` inside
    the main FastAPI app — do not assume this stub participates in production
    request handling.
    """
    pass
