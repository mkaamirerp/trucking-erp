from fastapi import FastAPI

from app.core.config import settings
from app.routers.health import router as health_router
from app.routers.drivers import router as drivers_router
from app.routers.driver_phones import router as driver_phones_router
from app.routers.driver_documents import router as driver_documents_router
from app.routers.public_signup import router as public_signup_router
from app.routers.platform_tenants import router as platform_tenants_router

app = FastAPI(title=settings.app_name, version="0.1.0")

# API routers
app.include_router(health_router, prefix="/api/v1")
app.include_router(public_signup_router)
app.include_router(platform_tenants_router)
app.include_router(drivers_router, prefix="/api/v1")
app.include_router(driver_phones_router, prefix="/api/v1")
app.include_router(driver_documents_router, prefix="/api/v1")

# Optional: keep old root so bookmarks don't break
@app.get("/", include_in_schema=False)
def root():
    return {"status": "ok"}
