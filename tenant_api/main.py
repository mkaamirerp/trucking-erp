from fastapi import FastAPI
from tenant_api.resolver import TenantResolverMiddleware

app = FastAPI(title="Tenant API")
app.add_middleware(TenantResolverMiddleware)

@app.get("/api/v1/drivers")
async def get_drivers():
    return {"status": "ok", "drivers": []}
