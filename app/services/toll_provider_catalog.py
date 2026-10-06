"""Toll provider and interoperability-network reference catalog.

Upload dropdown uses every catalog row with upload_choice=True.
That includes account providers and the listed home-agency networks.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Final, Literal

CATALOG_PROVIDER: Final[str] = "PROVIDER"
CATALOG_NETWORK: Final[str] = "NETWORK"
INTAKE_WIRED: Final[str] = "WIRED"
INTAKE_NOT_WIRED: Final[str] = "NOT_WIRED"


@dataclass(frozen=True)
class TollCatalogRecord:
    provider_code: str
    provider_name: str
    issuer_authority: str | None
    home_state: str | None
    statement_format: str | None
    supports_pdf: bool
    supports_csv: bool
    supports_api: bool
    accepted_networks: tuple[str, ...]
    transaction_state: str | None
    facility_authority: str | None
    catalog_kind: Literal["PROVIDER", "NETWORK"]
    intake_status: str
    upload_choice: bool

    def as_api_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["accepted_networks"] = list(self.accepted_networks)
        return payload


def _provider(
    *,
    provider_code: str,
    provider_name: str,
    issuer_authority: str | None,
    home_state: str | None,
    statement_format: str | None,
    supports_pdf: bool,
    supports_csv: bool,
    supports_api: bool,
    accepted_networks: tuple[str, ...],
    intake_status: str,
) -> TollCatalogRecord:
    return TollCatalogRecord(
        provider_code=provider_code,
        provider_name=provider_name,
        issuer_authority=issuer_authority,
        home_state=home_state,
        statement_format=statement_format,
        supports_pdf=supports_pdf,
        supports_csv=supports_csv,
        supports_api=supports_api,
        accepted_networks=accepted_networks,
        transaction_state=None,
        facility_authority=None,
        catalog_kind=CATALOG_PROVIDER,
        intake_status=intake_status,
        upload_choice=True,
    )


def _network(
    *,
    provider_code: str,
    provider_name: str,
    home_state: str | None,
    issuer_authority: str | None = None,
    facility_authority: str | None = None,
    accepted_by: tuple[str, ...] = (),
    upload_choice: bool = True,
) -> TollCatalogRecord:
    return TollCatalogRecord(
        provider_code=provider_code,
        provider_name=provider_name,
        issuer_authority=issuer_authority,
        home_state=home_state,
        statement_format=None,
        supports_pdf=False,
        supports_csv=False,
        supports_api=False,
        accepted_networks=(),
        transaction_state=home_state,
        facility_authority=facility_authority,
        catalog_kind=CATALOG_NETWORK,
        intake_status=INTAKE_NOT_WIRED,
        upload_choice=upload_choice,
    )


# Primary statement/account providers. These appear first in the upload dropdown.
_PROVIDERS: tuple[TollCatalogRecord, ...] = (
    _provider(
        provider_code="EZPASS",
        provider_name="E-ZPass",
        issuer_authority="E-ZPass Interagency Group",
        home_state=None,
        statement_format="PDF",
        supports_pdf=True,
        supports_csv=True,
        supports_api=False,
        accepted_networks=(
            "EZPASS_NY",
            "EZPASS_NJ",
            "EZPASS_PA",
            "IPASS",
            "WVPA",
        ),
        intake_status=INTAKE_WIRED,
    ),
    _provider(
        provider_code="PREPASS",
        provider_name="PrePass",
        issuer_authority="PrePass / PrePass Plus",
        home_state=None,
        statement_format="API",
        supports_pdf=False,
        supports_csv=False,
        supports_api=True,
        accepted_networks=(),
        intake_status=INTAKE_NOT_WIRED,
    ),
)

# Interoperability / home-agency networks. Listed in the upload dropdown unless upload_choice=False.
_NETWORKS: tuple[TollCatalogRecord, ...] = (
    _network(provider_code="TOLLTAG", provider_name="TollTag", home_state="TX", issuer_authority="NTTA"),
    _network(provider_code="EZ_TAG", provider_name="EZ TAG", home_state="TX", issuer_authority="HCTRA"),
    _network(provider_code="TXTAG", provider_name="TxTag", home_state="TX", issuer_authority="TxDOT"),
    _network(provider_code="PIKEPASS", provider_name="PIKEPASS", home_state="OK", issuer_authority="Oklahoma Turnpike Authority"),
    _network(provider_code="IPASS", provider_name="I-PASS", home_state="IL", issuer_authority="Illinois Tollway"),
    _network(provider_code="SUNPASS", provider_name="SunPass", home_state="FL", issuer_authority="Florida Turnpike Enterprise"),
    _network(provider_code="EPASS", provider_name="E-PASS", home_state="FL", issuer_authority="Central Florida Expressway Authority"),
    _network(provider_code="PEACH_PASS", provider_name="Peach Pass", home_state="GA", issuer_authority="SRTA"),
    _network(provider_code="NC_QUICK_PASS", provider_name="NC Quick Pass", home_state="NC", issuer_authority="NCTA"),
    _network(provider_code="KTAG", provider_name="K-TAG", home_state="KS", issuer_authority="Kansas Turnpike Authority"),
    _network(provider_code="FASTRAK", provider_name="FasTrak", home_state="CA"),
    _network(provider_code="GOOD_TO_GO", provider_name="Good To Go!", home_state="WA"),
    _network(provider_code="EZPASS_NY", provider_name="E-ZPass NY", home_state="NY"),
    _network(provider_code="EZPASS_NJ", provider_name="E-ZPass NJ", home_state="NJ"),
    _network(provider_code="EZPASS_PA", provider_name="E-ZPass PA", home_state="PA"),
    _network(
        provider_code="WVPA",
        provider_name="WVPA",
        home_state="WV",
        issuer_authority="West Virginia Parkways Authority",
        upload_choice=False,
    ),
)


def list_catalog() -> list[TollCatalogRecord]:
    return list(_PROVIDERS) + list(_NETWORKS)


def list_upload_providers() -> list[TollCatalogRecord]:
    return [row for row in list_catalog() if row.upload_choice]


def list_networks() -> list[TollCatalogRecord]:
    return [row for row in _NETWORKS if row.catalog_kind == CATALOG_NETWORK]


def get_upload_provider(provider_code: str | None) -> TollCatalogRecord | None:
    selected = (provider_code or "").strip().upper()
    if not selected:
        return None
    for row in list_upload_providers():
        if row.provider_code == selected:
            return row
    return None


def upload_provider_codes() -> frozenset[str]:
    return frozenset(row.provider_code for row in list_upload_providers())
