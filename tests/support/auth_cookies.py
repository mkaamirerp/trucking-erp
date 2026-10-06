"""Parse auth cookies from login/signup responses without depending on JSON token fields."""

from __future__ import annotations

from typing import Any


def _set_cookie_headers(response: Any) -> list[str]:
    headers = getattr(response, "headers", None)
    if headers is None:
        return []
    get_list = getattr(headers, "get_list", None) or getattr(headers, "getlist", None)
    if callable(get_list):
        return list(get_list("set-cookie"))
    raw = headers.get("set-cookie")
    if not raw:
        return []
    if isinstance(raw, (list, tuple)):
        return [str(x) for x in raw]
    return [str(raw)]


def cookie_value_from_response(response: Any, name: str) -> str | None:
    cookies = getattr(response, "cookies", None)
    if cookies is not None:
        try:
            val = cookies.get(name)
        except Exception:
            val = None
        if val:
            return str(val)
    prefix = f"{name}="
    for directive in _set_cookie_headers(response):
        first = directive.split(";", 1)[0].strip()
        if first.startswith(prefix):
            return first[len(prefix) :]
    return None


def cookie_path_from_response(response: Any, name: str) -> str | None:
    prefix = f"{name}="
    for directive in _set_cookie_headers(response):
        first = directive.split(";", 1)[0].strip()
        if not first.startswith(prefix):
            continue
        for part in directive.split(";"):
            p = part.strip()
            if p.lower().startswith("path="):
                return p.split("=", 1)[1]
        return None
    return None


def access_token_from_login_response(response: Any) -> str:
    token = cookie_value_from_response(response, "access_token")
    assert token, "login must set HttpOnly access_token cookie"
    return token
