"""
Temporary dev-only diagnostics router. Password-protected via cookie.
No RBAC, no DB. Will be removed later.
"""
import os
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from app.core.config import settings
from app.tools.dev_tools_auth import (
    COOKIE_NAME,
    verify_tools_password,
    make_cookie_value,
    require_tools_unlocked,
)

router = APIRouter(prefix="/api/v1/tools", tags=["Dev Tools"])


class UnlockBody(BaseModel):
    password: str


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
