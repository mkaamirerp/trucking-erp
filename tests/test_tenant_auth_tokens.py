"""JWT session_version (sv) claim."""
from __future__ import annotations

from app.utils.jwt_auth import TokenType, create_access_token, decode_token, extract_sv


def test_access_and_refresh_include_sv() -> None:
    a = create_access_token(
        user_id="u1",
        tenant_id=1,
        tenant_slug="demo",
        roles=["TENANT_ADMIN"],
        sv=7,
    )
    pa = decode_token(a, expected_type=TokenType.ACCESS)
    assert extract_sv(pa) == 7
