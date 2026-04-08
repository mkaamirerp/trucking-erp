"""Freight broker foundation: isolation, archive cascade, delete guard, identity conflicts, resolver precedence."""
from __future__ import annotations

import os

os.environ["ENVIRONMENT"] = "test"
os.environ["ALLOW_TENANT_RESOLUTION_SHORTCUTS"] = "true"

import uuid
import pytest
from httpx import ASGITransport, AsyncClient

from app.deps.tenant_db import open_tenant_session_by_id
from app.main import app
from app.services.broker_intake_resolve import _result_from_match_rows, resolve_broker_for_intake_from_header
from tests.support.integration_auth import (
    clear_current_user_and_tenant_overrides,
    install_mutable_tenant_current_user_and_tenant,
)
from tests.support.tenant_test_ids import platform_tenant_id_for_slug

REQUIRES_DB = not os.environ.get("DATABASE_URL")
AUTH_HEADERS = {"host": "demo.truckerp.me"}


@pytest.fixture(autouse=True)
def test_bypass_env():
    old = os.environ.get("TEST_BYPASS_AUTH")
    os.environ["TEST_BYPASS_AUTH"] = "1"
    yield
    if old is None:
        os.environ.pop("TEST_BYPASS_AUTH", None)
    else:
        os.environ["TEST_BYPASS_AUTH"] = old


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def tenant_resolver():
    holder = {"tenant_id": 1}
    install_mutable_tenant_current_user_and_tenant(
        app, holder, role="TENANT_ADMIN", user_id="test-user-brokers", email="test@example.com"
    )
    yield holder
    clear_current_user_and_tenant_overrides(app)


@pytest.fixture
async def demo_tid():
    """Platform id for slug=demo (same DB `get_tenant_db` uses under demo.truckerp.me)."""
    return await platform_tenant_id_for_slug("demo")


@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
class TestBrokersTenantIsolation:
    async def test_cross_tenant_cannot_fetch_broker(self, client, tenant_resolver) -> None:
        tenant_resolver["tenant_id"] = 1
        c = await client.post(
            "/api/v1/brokers",
            json={"name": f"Iso Broker {uuid.uuid4().hex[:6]}", "mc_number": None},
            headers=AUTH_HEADERS,
        )
        assert c.status_code == 201
        broker_id = c.json()["id"]

        tenant_resolver["tenant_id"] = 2
        g = await client.get(f"/api/v1/brokers/{broker_id}", headers=AUTH_HEADERS)
        assert g.status_code == 404


@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
class TestBrokerArchiveAndContacts:
    async def test_archive_deactivates_domains_and_aliases_not_contacts(self, client, tenant_resolver) -> None:
        tenant_resolver["tenant_id"] = 1
        suf = uuid.uuid4().hex[:8]
        br = await client.post(
            "/api/v1/brokers",
            json={"name": f"Arch Broker {suf}", "mc_number": None},
            headers=AUTH_HEADERS,
        )
        assert br.status_code == 201
        bid = br.json()["id"]

        dom = await client.post(
            f"/api/v1/brokers/{bid}/domains",
            json={"domain": f"dom-{suf}.example.com"},
            headers=AUTH_HEADERS,
        )
        assert dom.status_code == 201
        domain_id = dom.json()["id"]

        als = await client.post(
            f"/api/v1/brokers/{bid}/aliases",
            json={"alias": f"Alias {suf}"},
            headers=AUTH_HEADERS,
        )
        assert als.status_code == 201
        alias_id = als.json()["id"]

        ct = await client.post(
            f"/api/v1/brokers/{bid}/contacts",
            json={"name": f"Contact {suf}", "email": f"c{suf}@example.com"},
            headers=AUTH_HEADERS,
        )
        assert ct.status_code == 201
        contact_id = ct.json()["id"]

        ks = await client.post(
            f"/api/v1/brokers/{bid}/known-senders",
            json={"email": f"sender-{suf}@example.com"},
            headers=AUTH_HEADERS,
        )
        assert ks.status_code == 201
        ks_id = ks.json()["id"]

        arc = await client.post(f"/api/v1/brokers/{bid}/archive", headers=AUTH_HEADERS)
        assert arc.status_code == 200
        assert arc.json()["is_active"] is False

        d_list = await client.get(
            f"/api/v1/brokers/{bid}/domains",
            headers=AUTH_HEADERS,
            params={"include_archived": "true"},
        )
        assert d_list.status_code == 200
        rows = {r["id"]: r for r in d_list.json()["items"]}
        assert rows[domain_id]["is_active"] is False

        a_list = await client.get(
            f"/api/v1/brokers/{bid}/aliases",
            headers=AUTH_HEADERS,
            params={"include_archived": "true"},
        )
        assert a_list.status_code == 200
        arows = {r["id"]: r for r in a_list.json()["items"]}
        assert arows[alias_id]["is_active"] is False

        c_list = await client.get(
            f"/api/v1/brokers/{bid}/contacts",
            headers=AUTH_HEADERS,
            params={"include_archived": "true"},
        )
        assert c_list.status_code == 200
        crows = {r["id"]: r for r in c_list.json()["items"]}
        assert crows[contact_id]["is_active"] is True

        ks_list = await client.get(
            f"/api/v1/brokers/{bid}/known-senders",
            headers=AUTH_HEADERS,
            params={"include_archived": "true"},
        )
        assert ks_list.status_code == 200
        ksrows = {r["id"]: r for r in ks_list.json()["items"]}
        assert ksrows[ks_id]["is_active"] is False


@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
class TestBrokerDeleteGuard:
    async def test_delete_referenced_broker_409(self, client, tenant_resolver) -> None:
        tenant_resolver["tenant_id"] = 1
        suf = uuid.uuid4().hex[:8]
        br = await client.post(
            "/api/v1/brokers",
            json={"name": f"Del Broker {suf}", "mc_number": None},
            headers=AUTH_HEADERS,
        )
        assert br.status_code == 201
        bid = br.json()["id"]

        load = await client.post(
            "/api/v1/loads",
            json={"broker_id": bid, "broker_name_snapshot": br.json()["name"]},
            headers=AUTH_HEADERS,
        )
        assert load.status_code == 201

        d = await client.delete(f"/api/v1/brokers/{bid}", headers=AUTH_HEADERS)
        assert d.status_code == 409
        body = d.json()
        assert body["detail"]["code"] == "BROKER_REFERENCED_BY_LOADS"


@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
class TestBrokerIdentityConflicts:
    async def test_domain_conflict_active(self, client, tenant_resolver) -> None:
        tenant_resolver["tenant_id"] = 1
        suf = uuid.uuid4().hex[:8]
        domain = f"shared-{suf}.example.com"

        b1 = await client.post(
            "/api/v1/brokers",
            json={"name": f"Dom A {suf}", "mc_number": None},
            headers=AUTH_HEADERS,
        )
        b2 = await client.post(
            "/api/v1/brokers",
            json={"name": f"Dom B {suf}", "mc_number": None},
            headers=AUTH_HEADERS,
        )
        assert b1.status_code == 201 and b2.status_code == 201

        d1 = await client.post(
            f"/api/v1/brokers/{b1.json()['id']}/domains",
            json={"domain": domain},
            headers=AUTH_HEADERS,
        )
        assert d1.status_code == 201

        d2 = await client.post(
            f"/api/v1/brokers/{b2.json()['id']}/domains",
            json={"domain": domain},
            headers=AUTH_HEADERS,
        )
        assert d2.status_code == 409
        assert d2.json()["detail"]["code"] == "DOMAIN_CONFLICT"

    async def test_alias_conflict_active(self, client, tenant_resolver) -> None:
        tenant_resolver["tenant_id"] = 1
        suf = uuid.uuid4().hex[:8]
        alias = f"shared alias {suf}"

        b1 = await client.post(
            "/api/v1/brokers",
            json={"name": f"Al A {suf}", "mc_number": None},
            headers=AUTH_HEADERS,
        )
        b2 = await client.post(
            "/api/v1/brokers",
            json={"name": f"Al B {suf}", "mc_number": None},
            headers=AUTH_HEADERS,
        )
        assert b1.status_code == 201 and b2.status_code == 201

        a1 = await client.post(
            f"/api/v1/brokers/{b1.json()['id']}/aliases",
            json={"alias": alias},
            headers=AUTH_HEADERS,
        )
        assert a1.status_code == 201

        a2 = await client.post(
            f"/api/v1/brokers/{b2.json()['id']}/aliases",
            json={"alias": alias},
            headers=AUTH_HEADERS,
        )
        assert a2.status_code == 409
        assert a2.json()["detail"]["code"] == "ALIAS_CONFLICT"


@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
class TestBrokerListSearch:
    async def test_search_by_contact_department_returns_one_row(self, client, tenant_resolver) -> None:
        tenant_resolver["tenant_id"] = 1
        suf = uuid.uuid4().hex[:8]
        token = f"cntdept{suf}"
        br = await client.post(
            "/api/v1/brokers",
            json={"name": f"ZZ Hidden Firm {suf}", "mc_number": None},
            headers=AUTH_HEADERS,
        )
        assert br.status_code == 201
        bid = br.json()["id"]
        c = await client.post(
            f"/api/v1/brokers/{bid}/contacts",
            json={"name": "Rep", "department": token},
            headers=AUTH_HEADERS,
        )
        assert c.status_code == 201

        lst = await client.get("/api/v1/brokers", params={"q": token, "size": 100}, headers=AUTH_HEADERS)
        assert lst.status_code == 200
        data = lst.json()
        ids = [x["id"] for x in data["items"]]
        assert bid in ids
        assert ids.count(bid) == 1


@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
class TestBrokerResolver:
    async def test_known_sender_precedence_over_domain(self, client, tenant_resolver, demo_tid) -> None:
        tenant_resolver["tenant_id"] = demo_tid
        tid = demo_tid
        suf = uuid.uuid4().hex[:8]
        dom = f"ks-{suf}.example.com"
        sender_email = f"known{suf}@{dom}"

        b_ks = await client.post(
            "/api/v1/brokers",
            json={"name": f"KnownSenderWinner {suf}", "mc_number": None},
            headers=AUTH_HEADERS,
        )
        b_dom = await client.post(
            "/api/v1/brokers",
            json={"name": f"DomainOnly {suf}", "mc_number": None},
            headers=AUTH_HEADERS,
        )
        assert b_ks.status_code == 201 and b_dom.status_code == 201
        ksid = b_ks.json()["id"]
        did = b_dom.json()["id"]

        await client.post(
            f"/api/v1/brokers/{ksid}/known-senders",
            json={"email": sender_email},
            headers=AUTH_HEADERS,
        )
        await client.post(
            f"/api/v1/brokers/{did}/domains",
            json={"domain": dom},
            headers=AUTH_HEADERS,
        )

        hdr = f"Human <{sender_email}>"
        async for db in open_tenant_session_by_id(tid):
            res = await resolve_broker_for_intake_from_header(db, tid, hdr)
            assert res.broker_id == ksid
            assert res.broker_label == f"KnownSenderWinner {suf}"
            break

    async def test_domain_precedence_over_alias(self, client, tenant_resolver, demo_tid) -> None:
        tenant_resolver["tenant_id"] = demo_tid
        tid = demo_tid
        suf = uuid.uuid4().hex[:8]
        win_domain = f"win-{suf}.example.com"

        b_dom = await client.post(
            "/api/v1/brokers",
            json={"name": f"DomainWinner {suf}", "mc_number": None},
            headers=AUTH_HEADERS,
        )
        b_alias = await client.post(
            "/api/v1/brokers",
            json={"name": f"AliasOnly {suf}", "mc_number": None},
            headers=AUTH_HEADERS,
        )
        assert b_dom.status_code == 201 and b_alias.status_code == 201
        wid = b_dom.json()["id"]
        aid = b_alias.json()["id"]

        await client.post(
            f"/api/v1/brokers/{wid}/domains",
            json={"domain": win_domain},
            headers=AUTH_HEADERS,
        )
        await client.post(
            f"/api/v1/brokers/{aid}/aliases",
            json={"alias": f"displaymatch{suf}"},
            headers=AUTH_HEADERS,
        )

        hdr = f"displaymatch{suf} <ops@{win_domain}>"
        async for db in open_tenant_session_by_id(tid):
            res = await resolve_broker_for_intake_from_header(db, tid, hdr)
            assert res.broker_id == wid
            assert res.broker_label == f"DomainWinner {suf}"
            break

    async def test_intake_blocked_excluded_from_resolution(self, client, tenant_resolver, demo_tid) -> None:
        from sqlalchemy import select

        from app.models.broker import Broker

        tenant_resolver["tenant_id"] = demo_tid
        tid = demo_tid
        suf = uuid.uuid4().hex[:8]
        dom = f"blk-{suf}.example.com"

        br = await client.post(
            "/api/v1/brokers",
            json={"name": f"Blocked Firm {suf}", "mc_number": None},
            headers=AUTH_HEADERS,
        )
        assert br.status_code == 201
        bid = br.json()["id"]
        await client.post(f"/api/v1/brokers/{bid}/domains", json={"domain": dom}, headers=AUTH_HEADERS)

        async for db in open_tenant_session_by_id(tid):
            row = await db.scalar(select(Broker).where(Broker.id == bid, Broker.tenant_id == tid))
            assert row is not None
            row.intake_blocked = True
            await db.commit()
            break

        hdr = f"X <u@{dom}>"
        async for db in open_tenant_session_by_id(tid):
            res = await resolve_broker_for_intake_from_header(db, tid, hdr)
            assert res.broker_id is None
            assert res.ambiguous is False
            assert res.blocked_match is True
            break


def test_broker_intake_resolve_rows_ambiguous_two_brokers() -> None:
    r = _result_from_match_rows([(101, "A", False), (102, "B", False)], "domain")
    assert r.broker_id is None
    assert r.ambiguous is True


def test_broker_intake_resolve_rows_single_match() -> None:
    r = _result_from_match_rows([(7, "Acme", False)], "alias")
    assert r.broker_id == 7
    assert r.broker_label == "Acme"
    assert r.match_method == "alias"
    assert r.ambiguous is False


def test_broker_intake_resolve_rows_same_id_duplicates_collapsed() -> None:
    r = _result_from_match_rows([(3, "X", False), (3, "X", False)], "exact_known_sender")
    assert r.broker_id == 3
    assert not r.ambiguous


def test_broker_intake_resolve_rows_empty() -> None:
    r = _result_from_match_rows([], "domain")
    assert r.broker_id is None
    assert not r.ambiguous


def test_broker_intake_resolve_rows_blocked_only() -> None:
    r = _result_from_match_rows([(9, "Blocked Co", True)], "domain")
    assert r.broker_id is None
    assert r.blocked_match is True


def test_broker_intake_resolve_rows_non_blocked_wins_over_blocked() -> None:
    r = _result_from_match_rows([(1, "Good", False), (2, "Bad", True)], "domain")
    assert r.broker_id == 1
    assert not r.blocked_match
