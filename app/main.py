import logging
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from app.routers.fleet import router as fleet_router

from app.core.config import settings
from app.routers.health import router as health_router
from app.routers.drivers import router as drivers_router
from app.routers.driver_phones import router as driver_phones_router
from app.routers.driver_documents import router as driver_documents_router
from app.routers.admin_onboarding import router as admin_onboarding_router
from app.routers.driver_onboarding import router as driver_onboarding_router
from app.routers.public_signup import router as public_signup_router
from app.routers.workspace_intake import router as workspace_intake_router
from app.routers.platform_tenants import router as platform_tenants_router
from app.routers.platform_diagnostics import router as platform_diagnostics_router
from app.routers.onboarding import router as onboarding_router
from app.routers.meta import router as meta_router
from app.routers.payroll import router as payroll_router
from app.routers.pay_runs import router as pay_runs_router
from app.routers.me import router as me_router
from app.routers.auth import router as auth_router
from app.routers.brokers import router as brokers_router
from app.routers.loads import router as loads_router
from app.routers.dispatch import router as dispatch_router
from app.routers.trucks import router as trucks_router
from app.routers.trailers import router as trailers_router
from app.routers.dashboard import router as dashboard_router
from app.routers.dev_tools import router as dev_tools_router
from app.routers.dev_tools_db import router as dev_tools_db_router
from app.routers.tenant_admin import router as tenant_admin_router
from app.routers.admin_email_config import router as admin_email_config_router
from app.routers.email_threads import router as email_threads_router
from app.routers.gmail_pubsub import router as gmail_pubsub_router
from app.middleware.tenant_context import TenantContextMiddleware, tenant_middleware_allow_paths

def _startup_banner() -> None:
    parsed = urlparse(settings.database_url)
    platform_host = parsed.hostname or "(no hostname)"
    env = getattr(settings, "environment", "?")
    base = getattr(settings, "base_domain", "?")
    logger.info(
        "TruckERP starting | Environment: %s | Platform DB: %s | Tenant routing: enabled | Base domain: %s",
        env,
        platform_host,
        base,
    )


app = FastAPI(title=settings.app_name, version="0.1.0")
logger = logging.getLogger("trucking_erp")


@app.on_event("startup")
def _log_startup():
    _startup_banner()


app.add_middleware(
    TenantContextMiddleware,
    allow_paths=tenant_middleware_allow_paths(),
)

# API routers
app.include_router(health_router, prefix="/api/v1")
app.include_router(public_signup_router)
app.include_router(workspace_intake_router, prefix="/api/v1/public")
app.include_router(platform_tenants_router)
app.include_router(platform_diagnostics_router)
app.include_router(drivers_router, prefix="/api/v1")
app.include_router(fleet_router, prefix="/api/v1")
app.include_router(driver_phones_router, prefix="/api/v1")
app.include_router(driver_documents_router, prefix="/api/v1")
app.include_router(admin_onboarding_router)
app.include_router(driver_onboarding_router)
app.include_router(onboarding_router)
app.include_router(meta_router)
app.include_router(payroll_router)
app.include_router(pay_runs_router)
app.include_router(me_router)
app.include_router(auth_router)
app.include_router(brokers_router, prefix="/api/v1")
app.include_router(loads_router, prefix="/api/v1")
app.include_router(dispatch_router, prefix="/api/v1")
app.include_router(trucks_router, prefix="/api/v1")
app.include_router(trailers_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1")
# Dev-only: password + cookie auth; no tenant RBAC. Omitted in production/staging (routes do not exist → 404).
if settings.allows_dev_tenant_resolution_shortcuts():
    app.include_router(dev_tools_router)
    app.include_router(dev_tools_db_router)
app.include_router(tenant_admin_router)
app.include_router(admin_email_config_router)
app.include_router(email_threads_router, prefix="/api/v1")
app.include_router(gmail_pubsub_router, prefix="/api/v1")

# Static assets and dashboard UI (reference layout: sidebar, KPIs, drivers, loads, alerts, chat)
_static_dir = Path(__file__).resolve().parent / "static"
if _static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")
_dashboard_html = Path(__file__).resolve().parent / "static" / "dashboard" / "index.html"


@app.get("/dashboard", include_in_schema=False)
def serve_dashboard():
    """Serve the dispatch dashboard UI (sidebar, KPIs, drivers, loads). Requires auth + tenant cookie."""
    if _dashboard_html.is_file():
        return FileResponse(_dashboard_html, media_type="text/html")
    return JSONResponse(status_code=404, content={"detail": "Dashboard UI not found"})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("unhandled_exception path=%s method=%s", request.url.path, request.method)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# Optional: keep old root so bookmarks don't break
@app.get("/", include_in_schema=False)
def root():
    return {"status": "ok"}


@app.get("/healthz", include_in_schema=False)
async def healthz():
    return {"status": "ok", "service": "trucking-erp-api"}


@app.get("/api/v1/healthz", include_in_schema=False)
async def healthz_v1():
    return {"status": "ok", "service": "trucking-erp-api"}
