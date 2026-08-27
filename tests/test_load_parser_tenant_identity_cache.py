"""Slice 1B: in-process TTL cache for load_parser_tenant_identity exclusion."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.services import load_parser_tenant_identity_exclusion as mod
from app.services.load_parser_tenant_identity_exclusion import (
    DEFAULT_TTL_SECONDS,
    cache_key_for_tenant,
    get_load_parser_tenant_identity_exclusion,
    invalidate_load_parser_tenant_identity_cache,
)


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _clear_cache():
    invalidate_load_parser_tenant_identity_cache()
    yield
    invalidate_load_parser_tenant_identity_cache()


def test_cache_key_format() -> None:
    assert cache_key_for_tenant(53) == "load_parser_tenant_identity:53"
    assert DEFAULT_TTL_SECONDS == 30 * 60


def test_first_lookup_calls_loader_second_is_hit() -> None:
    calls: list[int] = []

    async def loader(_db: Any, tenant_id: int) -> dict[str, Any]:
        calls.append(tenant_id)
        return {
            "names": [f"Tenant {tenant_id}"],
            "mc_numbers": [],
            "usdot_numbers": [],
            "phones": [],
            "emails": [],
            "email_domains": [],
            "addresses": [],
        }

    clock = {"t": 1000.0}

    a = _run(
        get_load_parser_tenant_identity_exclusion(
            None, tenant_id=53, loader=loader, now_fn=lambda: clock["t"]
        )
    )
    b = _run(
        get_load_parser_tenant_identity_exclusion(
            None, tenant_id=53, loader=loader, now_fn=lambda: clock["t"]
        )
    )
    assert calls == [53]
    assert a["names"] == ["Tenant 53"]
    assert b["names"] == ["Tenant 53"]
    assert a is not b


def test_different_tenant_ids_are_independent() -> None:
    calls: list[int] = []

    async def loader(_db: Any, tenant_id: int) -> dict[str, Any]:
        calls.append(tenant_id)
        return {
            "names": [f"T{tenant_id}"],
            "mc_numbers": [str(tenant_id)],
            "usdot_numbers": [],
            "phones": [],
            "emails": [],
            "email_domains": [],
            "addresses": [],
        }

    clock = {"t": 1.0}
    a = _run(
        get_load_parser_tenant_identity_exclusion(
            None, tenant_id=10, loader=loader, now_fn=lambda: clock["t"]
        )
    )
    b = _run(
        get_load_parser_tenant_identity_exclusion(
            None, tenant_id=20, loader=loader, now_fn=lambda: clock["t"]
        )
    )
    a2 = _run(
        get_load_parser_tenant_identity_exclusion(
            None, tenant_id=10, loader=loader, now_fn=lambda: clock["t"]
        )
    )
    assert calls == [10, 20]
    assert a["names"] == ["T10"]
    assert b["names"] == ["T20"]
    assert a2["mc_numbers"] == ["10"]


def test_explicit_invalidation_forces_reload() -> None:
    calls: list[int] = []

    async def loader(_db: Any, tenant_id: int) -> dict[str, Any]:
        calls.append(tenant_id)
        return {
            "names": [f"v{len(calls)}"],
            "mc_numbers": [],
            "usdot_numbers": [],
            "phones": [],
            "emails": [],
            "email_domains": [],
            "addresses": [],
        }

    clock = {"t": 50.0}
    first = _run(
        get_load_parser_tenant_identity_exclusion(
            None, tenant_id=7, loader=loader, now_fn=lambda: clock["t"]
        )
    )
    assert first["names"] == ["v1"]
    invalidate_load_parser_tenant_identity_cache(7)
    second = _run(
        get_load_parser_tenant_identity_exclusion(
            None, tenant_id=7, loader=loader, now_fn=lambda: clock["t"]
        )
    )
    assert second["names"] == ["v2"]
    assert calls == [7, 7]


def test_ttl_expiration_causes_reload() -> None:
    calls: list[int] = []

    async def loader(_db: Any, tenant_id: int) -> dict[str, Any]:
        calls.append(tenant_id)
        return {
            "names": [f"n{len(calls)}"],
            "mc_numbers": [],
            "usdot_numbers": [],
            "phones": [],
            "emails": [],
            "email_domains": [],
            "addresses": [],
        }

    clock = {"t": 0.0}
    _run(
        get_load_parser_tenant_identity_exclusion(
            None,
            tenant_id=99,
            loader=loader,
            ttl_seconds=10.0,
            now_fn=lambda: clock["t"],
        )
    )
    clock["t"] = 9.9
    _run(
        get_load_parser_tenant_identity_exclusion(
            None,
            tenant_id=99,
            loader=loader,
            ttl_seconds=10.0,
            now_fn=lambda: clock["t"],
        )
    )
    assert calls == [99]
    clock["t"] = 10.1
    third = _run(
        get_load_parser_tenant_identity_exclusion(
            None,
            tenant_id=99,
            loader=loader,
            ttl_seconds=10.0,
            now_fn=lambda: clock["t"],
        )
    )
    assert calls == [99, 99]
    assert third["names"] == ["n2"]


def test_caller_mutation_does_not_contaminate_cache() -> None:
    async def loader(_db: Any, tenant_id: int) -> dict[str, Any]:
        return {
            "names": ["Safe Co"],
            "mc_numbers": ["123"],
            "usdot_numbers": [],
            "phones": [],
            "emails": ["a@safe.example"],
            "email_domains": ["safe.example"],
            "addresses": [{"city": "Toronto"}],
        }

    clock = {"t": 0.0}
    first = _run(
        get_load_parser_tenant_identity_exclusion(
            None, tenant_id=1, loader=loader, now_fn=lambda: clock["t"]
        )
    )
    first["names"].append("MUTATED")
    first["mc_numbers"][0] = "999"
    first["addresses"][0]["city"] = "Hacked"
    first["emails"].clear()

    second = _run(
        get_load_parser_tenant_identity_exclusion(
            None, tenant_id=1, loader=loader, now_fn=lambda: clock["t"]
        )
    )
    assert second["names"] == ["Safe Co"]
    assert second["mc_numbers"] == ["123"]
    assert second["addresses"] == [{"city": "Toronto"}]
    assert second["emails"] == ["a@safe.example"]


def test_invalidate_all_clears_every_tenant() -> None:
    async def loader(_db: Any, tenant_id: int) -> dict[str, Any]:
        return {
            "names": [str(tenant_id)],
            "mc_numbers": [],
            "usdot_numbers": [],
            "phones": [],
            "emails": [],
            "email_domains": [],
            "addresses": [],
        }

    clock = {"t": 0.0}
    _run(
        get_load_parser_tenant_identity_exclusion(
            None, tenant_id=1, loader=loader, now_fn=lambda: clock["t"]
        )
    )
    _run(
        get_load_parser_tenant_identity_exclusion(
            None, tenant_id=2, loader=loader, now_fn=lambda: clock["t"]
        )
    )
    assert len(mod._CACHE) == 2
    invalidate_load_parser_tenant_identity_cache(None)
    assert len(mod._CACHE) == 0
