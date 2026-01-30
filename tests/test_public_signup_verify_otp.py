from __future__ import annotations

import asyncio
import logging

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import Response
from unittest.mock import AsyncMock

from app.routers.public_signup import verify_otp
from app.schemas.signup import VerifyOTPRequest


def _make_request(headers: dict[str, str]) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/public/verify-otp",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": ("127.0.0.1", 12345),
    }
    return Request(scope)


def test_verify_otp_logs_exception_and_returns_500(caplog: pytest.LogCaptureFixture) -> None:
    payload = VerifyOTPRequest(email="user@example.com", otp="123456")
    request = _make_request({"host": "test.local"})
    response = Response()
    db = AsyncMock()
    db.scalar.side_effect = RuntimeError("boom")

    with caplog.at_level(logging.ERROR):
        with pytest.raises(HTTPException) as excinfo:
            asyncio.run(verify_otp(payload, request, response, db))

    assert excinfo.value.status_code == 500
    assert excinfo.value.detail == "OTP verification failed"
    assert any("verify_otp failed" in record.message for record in caplog.records)
