"""Document-safe company contact accessor.

Business documents (invoices, pay stubs, PDFs) must use ONLY canonical
platform_company_profiles data. Owner/user contact from platform_users must
never be used as the source for document-facing company identity.

This module is the required source for all document generation paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import selectinload

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform import PlatformCompanyProfile, PlatformTenant


# Document-readiness: a company is document-ready only when canonical profile has:
# - legal_name
# - full business address (street, city, region, postal, country)
# - company_phone
# - company_email
_REQUIRED_FOR_DOCUMENTS = (
    "legal_name",
    "address_street", "address_city", "address_region", "address_postal", "address_country",
    "company_phone", "company_email",
)


@dataclass
class CanonicalCompanyContact:
    """Canonical company contact for business documents. No fallbacks."""

    tenant_id: int
    legal_name: str
    address_street: str
    address_city: str
    address_region: str
    address_postal: str
    address_country: str
    company_phone: str
    company_email: str

    def as_dict(self) -> dict[str, str]:
        return {
            "legal_name": self.legal_name,
            "address_street": self.address_street,
            "address_city": self.address_city,
            "address_region": self.address_region,
            "address_postal": self.address_postal,
            "address_country": self.address_country,
            "company_phone": self.company_phone,
            "company_email": self.company_email,
        }


@dataclass
class DocumentContactResult:
    """Result of document-safe company contact lookup."""

    is_document_ready: bool
    contact: CanonicalCompanyContact | None
    missing_fields: list[str]


def _is_nonempty(value: str | None) -> bool:
    return bool(value and str(value).strip())


async def get_canonical_company_contact_for_documents(
    tenant_id: int, db: AsyncSession
) -> DocumentContactResult:
    """
    Fetch document-safe company contact from platform_company_profiles ONLY.

    Does NOT fall back to platform_users (owner) or onboarding payload.
    Returns complete data only when all required fields are present in the profile.

    Use this for: invoices, pay stubs, business PDFs, outgoing business templates.
    """
    tenant = await db.scalar(
        select(PlatformTenant)
        .options(selectinload(PlatformTenant.company_profile))
        .where(PlatformTenant.id == tenant_id)
    )
    if not tenant or not tenant.company_profile:
        return DocumentContactResult(
            is_document_ready=False,
            contact=None,
            missing_fields=list(_REQUIRED_FOR_DOCUMENTS),
        )

    profile: PlatformCompanyProfile = tenant.company_profile
    missing: list[str] = []

    legal_name = (profile.legal_name or "").strip()
    if not legal_name:
        missing.append("legal_name")

    addr_street = (profile.address_street or "").strip()
    addr_city = (profile.address_city or "").strip()
    addr_region = (profile.address_region or "").strip()
    addr_postal = (profile.address_postal or "").strip()
    addr_country = (profile.address_country or "").strip()
    if not addr_street:
        missing.append("address_street")
    if not addr_city:
        missing.append("address_city")
    if not addr_region:
        missing.append("address_region")
    if not addr_postal:
        missing.append("address_postal")
    if not addr_country:
        missing.append("address_country")

    company_phone = (profile.company_phone or "").strip()
    company_email = (profile.company_email or "").strip().lower()
    if not company_phone:
        missing.append("company_phone")
    if not company_email:
        missing.append("company_email")

    if missing:
        return DocumentContactResult(
            is_document_ready=False,
            contact=None,
            missing_fields=missing,
        )

    return DocumentContactResult(
        is_document_ready=True,
        contact=CanonicalCompanyContact(
            tenant_id=tenant_id,
            legal_name=legal_name,
            address_street=addr_street,
            address_city=addr_city,
            address_region=addr_region,
            address_postal=addr_postal,
            address_country=addr_country,
            company_phone=company_phone,
            company_email=company_email,
        ),
        missing_fields=[],
    )
