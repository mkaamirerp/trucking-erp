"""
Temporary dev-only diagnostics router. Password-protected via cookie.
No RBAC, no DB. Will be removed later.
"""
import os
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, EmailStr

from app.core.config import settings
from app.utils.email import send_test_email
from app.tools.dev_tools_auth import (
    COOKIE_NAME,
    verify_tools_password,
    make_cookie_value,
    require_tools_unlocked,
)

router = APIRouter(prefix="/api/v1/tools", tags=["Dev Tools"])


class UnlockBody(BaseModel):
    password: str


class SendTestEmailBody(BaseModel):
    to: EmailStr


@router.post("/send-test-email")
async def send_test_email_endpoint(request: Request, body: SendTestEmailBody):
    """Send a test email to verify SMTP/Mailpit. Requires tools unlock."""
    require_tools_unlocked(request)
    await send_test_email(to=body.to)
    return {"ok": True, "message": f"Test email sent to {body.to}"}


@router.post("/unlock")
async def unlock(body: UnlockBody, response: Response):
    if not verify_tools_password(body.password):
        return {"ok": False}
    value = make_cookie_value()
    max_age = int(os.environ.get("TOOLS_DEV_MAX_AGE_SECONDS", "3600"))
    response.set_cookie(
        COOKIE_NAME,
        value,
        max_age=max_age,
        httponly=True,
        secure=bool(settings.secure_cookies),
        samesite=settings.jwt_same_site or "lax",
        path="/",
    )
    return {"ok": True}


@router.get("/ping")
async def ping(request: Request):
    require_tools_unlocked(request)
    return {"ok": True}
