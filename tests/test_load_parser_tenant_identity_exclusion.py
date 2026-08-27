"""Tests for Load parser tenant_identity_exclusion builder (no OpenAI, no broker logic)."""

from __future__ import annotations

import inspect

from app.services import load_parser_tenant_identity_exclusion as mod
from app.services.load_parser_tenant_identity_exclusion import (
    build_load_parser_tenant_identity_exclusion,
    is_public_email_domain,
    normalize_authority_id,
    normalize_email,
    normalize_phone_digits,
)


def test_two_tenants_produce_different_exclusion_objects() -> None:
    a = build_load_parser_tenant_identity_exclusion(
        tenant_name="Alpha Freight Co",
        legal_name="Alpha Freight Company Inc",
        mc_number="MC-1111111",
        usdot_number="2222222",
        company_phone="+1 (416) 555-0101",
        company_email="ops@alphafreight.example",
        address_street="100 Alpha Rd",
        address_city="Toronto",
        address_postal="M5V 2T6",
    )
    b = build_load_parser_tenant_identity_exclusion(
        tenant_name="Beta Haulers",
        legal_name="Beta Haulers LLC",
        mc_number="3333333",
        usdot_number="DOT 4444444",
        company_phone="647-555-0199",
        company_email="dispatch@betahaulers.example",
        address_street="200 Beta Ave",
        address_city="Mississauga",
        address_postal="L5B1M2",
    )
    assert a["names"] != b["names"]
    assert a["mc_numbers"] == ["1111111"]
    assert b["mc_numbers"] == ["3333333"]
    assert a["phones"] == ["4165550101"]
    assert b["phones"] == ["6475550199"]
    assert a["email_domains"] == ["alphafreight.example"]
    assert b["email_domains"] == ["betahaulers.example"]
    assert a["addresses"][0]["city"] == "Toronto"
    assert b["addresses"][0]["city"] == "Mississauga"
    assert "cvor_numbers" not in a
    assert "region" not in a["addresses"][0]
    assert "country" not in a["addresses"][0]


def test_missing_profile_fields_are_safe_empty_arrays() -> None:
    out = build_load_parser_tenant_identity_exclusion(
        tenant_name=None,
        legal_name=None,
        mc_number=None,
        usdot_number="",
        company_phone=None,
        company_email=None,
        address_street=None,
        address_city=None,
    )
    assert out == {
        "names": [],
        "mc_numbers": [],
        "usdot_numbers": [],
        "phones": [],
        "emails": [],
        "email_domains": [],
        "addresses": [],
    }
    assert "cvor_numbers" not in out
    assert "None" not in str(out)
    assert None not in out["names"]
    assert "" not in out["mc_numbers"]


def test_normalization_phone_authority_email_name_postal() -> None:
    assert normalize_phone_digits("+1 (647) 241-9696") == "6472419696"
    assert normalize_phone_digits("647-241-9696") == "6472419696"
    assert normalize_authority_id("MC: 001397898") == "1397898"
    assert normalize_authority_id("USDOT 3842541") == "3842541"
    assert normalize_email("  Info@Example.COM ") == "info@example.com"
    out = build_load_parser_tenant_identity_exclusion(
        tenant_name="  Acme   Transport  ",
        legal_name="acme transport",
        mc_number="MC 555609",
        company_phone="1-877-240-1181",
        company_email="Carriers@AcmeTransport.COM",
        address_postal="L6T 2T4",
        address_city="Brampton",
    )
    # Name dedupe by casefold; first display form kept.
    assert out["names"] == ["Acme Transport"]
    assert out["mc_numbers"] == ["555609"]
    assert out["phones"] == ["8772401181"]
    assert out["emails"] == ["carriers@acmetransport.com"]
    assert out["email_domains"] == ["acmetransport.com"]
    assert out["addresses"][0] == {"city": "Brampton", "postal": "L6T2T4"}


def test_public_email_domains_not_company_owned() -> None:
    assert is_public_email_domain("gmail.com")
    assert is_public_email_domain("hotmail.com")
    assert is_public_email_domain("outlook.com")
    assert is_public_email_domain("yahoo.com")
    assert not is_public_email_domain("armstrongtransport.com")

    out = build_load_parser_tenant_identity_exclusion(
        tenant_name="Demo Co",
        company_email="owner@gmail.com",
    )
    assert out["emails"] == ["owner@gmail.com"]
    assert out["email_domains"] == []

    out2 = build_load_parser_tenant_identity_exclusion(
        tenant_name="Demo Co",
        company_email="ops@Yahoo.COM",
    )
    assert out2["emails"] == ["ops@yahoo.com"]
    assert out2["email_domains"] == []


def test_module_has_no_hardcoded_tenant_or_broker_values() -> None:
    src = inspect.getsource(mod)
    forbidden = (
        "IK Logistics",
        "Armstrong",
        "J.B. Hunt",
        "JBHunt",
        "1397898",
        "555609",
        "Loflin",
        "RXO",
        "TQL",
        "11036696",
        "8785874",
    )
    for token in forbidden:
        assert token not in src, f"hardcoded token found: {token}"


def test_rate_con_address_is_street_city_postal_only() -> None:
    out = build_load_parser_tenant_identity_exclusion(
        address_street="10 Main St",
        address_city="Brampton",
        address_postal="L6T 2T4",
    )
    assert out["addresses"] == [
        {"street": "10 Main St", "city": "Brampton", "postal": "L6T2T4"}
    ]


def test_city_only_without_street_still_builds_address() -> None:
    out = build_load_parser_tenant_identity_exclusion(
        address_city="Kitchener",
        address_postal="N2G1A1",
    )
    assert out["addresses"] == [{"city": "Kitchener", "postal": "N2G1A1"}]


def test_postal_alone_is_not_an_address() -> None:
    out = build_load_parser_tenant_identity_exclusion(address_postal="L6T2T4")
    assert out["addresses"] == []


def test_excluded_profile_fields_cannot_enter_returned_exclusion() -> None:
    """Frozen allowlist: non-rate-con profile fields must not appear in any array/address."""
    from types import SimpleNamespace

    tenant = SimpleNamespace(name="Allowlisted Tenant")
    profile = SimpleNamespace(
        legal_name="Allowlisted Legal Inc",
        mc_number="MC-1002003",
        usdot_number="9008007",
        company_phone="416-555-0100",
        company_email="ops@allowlisted.example",
        address_street="1 Allowed St",
        address_city="Allowed City",
        address_postal="A1A 1A1",
        # Distinctive poison — must never leak into returned exclusion.
        cvor_number="POISON-CVOR-999888",
        address_region="POISON-REGION-ON",
        address_country="POISON-COUNTRY-CA",
        operator_license="POISON-OP-LIC",
        hst_number="POISON-HST-123",
        w9_storage_key="poison/w9.pdf",
        w9_original_filename="poison-w9.pdf",
    )
    out = build_load_parser_tenant_identity_exclusion(tenant=tenant, profile=profile)
    blob = str(out)
    for poison in (
        "POISON-CVOR-999888",
        "POISON-REGION-ON",
        "POISON-COUNTRY-CA",
        "POISON-OP-LIC",
        "POISON-HST-123",
        "poison/w9.pdf",
        "poison-w9.pdf",
        "cvor_numbers",
        "region",
        "country",
    ):
        assert poison not in blob, f"excluded value leaked: {poison}"
    assert out["names"] == ["Allowlisted Tenant", "Allowlisted Legal Inc"]
    assert out["mc_numbers"] == ["1002003"]
    assert out["usdot_numbers"] == ["9008007"]
    assert out["phones"] == ["4165550100"]
    assert out["emails"] == ["ops@allowlisted.example"]
    assert out["addresses"] == [
        {"street": "1 Allowed St", "city": "Allowed City", "postal": "A1A1A1"}
    ]
    assert set(out.keys()) == {
        "names",
        "mc_numbers",
        "usdot_numbers",
        "phones",
        "emails",
        "email_domains",
        "addresses",
    }
