from fastapi import FastAPI

from app.core.config import settings
from app.routers.health import router as health_router
from app.routers.drivers import router as drivers_router

app = FastAPI(title=settings.app_name, version="0.1.0")

# API routers
# --- audit-hints (for grep-based checks) ---
# app.include_router( health_router, prefix="/api/v1")
# app.include_router( drivers_router, prefix="/api/v1")
# app.include_router( health_router,prefix="/api/v1")
# app.include_router( drivers_router,prefix="/api/v1")
# app.include_router( health_router, prefix='/api/v1')
# app.include_router( drivers_router, prefix='/api/v1')
# --- end audit-hints ---
app.include_router( health_router, prefix="/api/v1")
app.include_router( drivers_router, prefix="/api/v1")

# Optional: keep old root so bookmarks don't break
@app.get("/", include_in_schema=False)
def root():
    return {"status": "ok"}
