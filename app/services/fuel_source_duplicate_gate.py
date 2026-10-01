"""Fuel source ingestion duplicate detection (tenant + provider scoped).

PDF: filename signal, provider document identity from parsed source, raw SHA-256.
CSV: same layers plus normalized transaction fingerprint (for regenerated exports).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Final, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fuel import FuelBvd, FuelNationwide
from app.services.fuel_bvd_extraction import BVD_PROVIDER_CODE, FuelBvdExtractedRow
from app.services.fuel_nationwide_extraction import FuelNationwideExtractedRow
from app.services.fuel_nationwide_import import NATIONWIDE_PROVIDER_CODE

FUEL_DUPLICATE_EXACT: Final[str] = "FUEL_DUPLICATE_EXACT"
FUEL_DUPLICATE_DOCUMENT: Final[str] = "FUEL_DUPLICATE_DOCUMENT"
FUEL_POSSIBLE_REVISION: Final[str] = "FUEL_POSSIBLE_REVISION"
FUEL_DUPLICATE_TRANSACTIONS: Final[str] = "FUEL_DUPLICATE_TRANSACTIONS"
FUEL_TRANSACTION_OVERLAP: Final[str] = "FUEL_TRANSACTION_OVERLAP"

_STATUS_RANK: dict[str | None, int] = {
    "SOURCE_REVIEWED": 0,
    "IN_REVIEW": 1,
    "PENDING": 2,
    None: 3,
}


@dataclass(frozen=True)
class BvdDocumentIdentity:
    provider: str
    invoice_number: str
    invoice_date: str
    start_date: str
    end_date: str

    def is_complete(self) -> bool:
        return all(
            [
                self.invoice_number,
                self.invoice_date,
                self.start_date,
                self.end_date,
            ]
        )

    def business_lock_key(self, tenant_id: int) -> int | None:
        """PostgreSQL advisory lock: tenant + provider + invoice_number (not SHA-256)."""
        if not _norm_text(self.invoice_number):
            return None
        raw = f"{tenant_id}:{self.provider}:{_norm_text(self.invoice_number)}"
        return int(hashlib.sha256(raw.encode()).hexdigest()[:15], 16) % (2**31 - 1)


@dataclass
class ExistingBvdImportMatch:
    import_id: uuid.UUID
    review_status: str | None
    uploaded_at: datetime | None
    source_file_sha256: str | None
    source_file_name: str | None
    invoice_number: str | None
    invoice_date: str | None
    start_date: str | None
    end_date: str | None


@dataclass
class FuelDuplicateIngestionConflict:
    code: str
    message: str
    http_status: int = 409
    provider: str = BVD_PROVIDER_CODE
    existing_import_id: str = ""
    existing_status: str = "PENDING"
    existing_uploaded_at: str | None = None
    invoice_number: str | None = None
    invoice_date: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    matched_on: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_detail(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "provider": self.provider,
            "existing_import_id": self.existing_import_id,
            "existing_status": self.existing_status,
            "existing_uploaded_at": self.existing_uploaded_at,
            "invoice_number": self.invoice_number,
            "invoice_date": self.invoice_date,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "matched_on": self.matched_on,
        }
        out.update(self.extra)
        return out


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _norm_text(value: str | None) -> str:
    if value is None:
        return ""
    return str(value).strip()


def document_identity_from_extracted_rows(rows: Iterable[FuelBvdExtractedRow]) -> BvdDocumentIdentity:
    header = next((r for r in rows if r.row_type == "HEADER"), None)
    fields = header.fields if header else {}
    return BvdDocumentIdentity(
        provider=BVD_PROVIDER_CODE,
        invoice_number=_norm_text(fields.get("invoice_number")),
        invoice_date=_norm_text(fields.get("invoice_date")),
        start_date=_norm_text(fields.get("start_date")),
        end_date=_norm_text(fields.get("end_date")),
    )


def _header_identity_matches(row: ExistingBvdImportMatch, identity: BvdDocumentIdentity) -> bool:
    return (
        _norm_text(row.invoice_number) == identity.invoice_number
        and _norm_text(row.invoice_date) == identity.invoice_date
        and _norm_text(row.start_date) == identity.start_date
        and _norm_text(row.end_date) == identity.end_date
    )


def pick_best_existing_import(matches: list[ExistingBvdImportMatch]) -> ExistingBvdImportMatch:
    def sort_key(m: ExistingBvdImportMatch) -> tuple[int, float]:
        rank = _STATUS_RANK.get(m.review_status, 99)
        ts = m.uploaded_at.timestamp() if m.uploaded_at else 0.0
        return (rank, -ts)

    return sorted(matches, key=sort_key)[0]


async def _load_bvd_header_matches(
    db: AsyncSession,
    *,
    tenant_id: int,
    invoice_number: str,
) -> list[ExistingBvdImportMatch]:
    if not invoice_number:
        return []
    result = await db.execute(
        select(FuelBvd).where(
            FuelBvd.tenant_id == tenant_id,
            FuelBvd.row_type == "HEADER",
            FuelBvd.invoice_number == invoice_number,
        )
    )
    out: list[ExistingBvdImportMatch] = []
    for row in result.scalars().all():
        out.append(
            ExistingBvdImportMatch(
                import_id=row.import_id,
                review_status=row.review_status,
                uploaded_at=row.uploaded_at,
                source_file_sha256=row.source_file_sha256,
                source_file_name=row.source_file_name,
                invoice_number=row.invoice_number,
                invoice_date=row.invoice_date,
                start_date=row.start_date,
                end_date=row.end_date,
            )
        )
    return out


async def _load_bvd_sha_matches(
    db: AsyncSession,
    *,
    tenant_id: int,
    file_sha256: str,
) -> list[ExistingBvdImportMatch]:
    result = await db.execute(
        select(FuelBvd).where(
            FuelBvd.tenant_id == tenant_id,
            FuelBvd.source_file_sha256 == file_sha256,
        )
    )
    by_import: dict[uuid.UUID, ExistingBvdImportMatch] = {}
    for row in result.scalars().all():
        if row.import_id not in by_import or row.row_type == "HEADER":
            by_import[row.import_id] = ExistingBvdImportMatch(
                import_id=row.import_id,
                review_status=row.review_status,
                uploaded_at=row.uploaded_at,
                source_file_sha256=row.source_file_sha256,
                source_file_name=row.source_file_name,
                invoice_number=row.invoice_number,
                invoice_date=row.invoice_date,
                start_date=row.start_date,
                end_date=row.end_date,
            )
    return list(by_import.values())


def evaluate_bvd_pdf_duplicate(
    *,
    file_sha256: str,
    filename: str,
    identity: BvdDocumentIdentity,
    sha_matches: list[ExistingBvdImportMatch],
    invoice_number_matches: list[ExistingBvdImportMatch],
) -> FuelDuplicateIngestionConflict | None:
    """Pure decision matrix for BVD PDF (tenant-scoped matches already loaded)."""
    matched_on: list[str] = []
    best: ExistingBvdImportMatch | None = None

    if sha_matches:
        matched_on.append("SHA256")
        best = pick_best_existing_import(sha_matches)
        if filename and any(_norm_text(m.source_file_name) == _norm_text(filename) for m in sha_matches):
            matched_on.append("FILE_NAME")
        if identity.is_complete() and any(_header_identity_matches(m, identity) for m in sha_matches):
            matched_on.append("DOCUMENT_IDENTITY")
        return _conflict_from_match(
            FUEL_DUPLICATE_EXACT,
            "This BVD invoice file has already been uploaded.",
            best,
            identity,
            matched_on,
        )

    identity_matches = [m for m in invoice_number_matches if _header_identity_matches(m, identity)]
    if identity.is_complete() and identity_matches:
        matched_on = ["DOCUMENT_IDENTITY"]
        if filename and any(_norm_text(m.source_file_name) == _norm_text(filename) for m in identity_matches):
            matched_on.append("FILE_NAME")
        best = pick_best_existing_import(identity_matches)
        return _conflict_from_match(
            FUEL_DUPLICATE_DOCUMENT,
            "This BVD invoice has already been uploaded.",
            best,
            identity,
            matched_on,
        )

    if identity.invoice_number and invoice_number_matches and identity.is_complete():
        if not identity_matches:
            matched_on = ["INVOICE_NUMBER"]
            best = pick_best_existing_import(invoice_number_matches)
            return _conflict_from_match(
                FUEL_POSSIBLE_REVISION,
                "A BVD invoice with this number already exists with a different date or charge period.",
                best,
                identity,
                matched_on,
                extra={"conflict_type": "POSSIBLE_REVISION"},
            )

    return None


def _conflict_from_match(
    code: str,
    message: str,
    match: ExistingBvdImportMatch,
    identity: BvdDocumentIdentity,
    matched_on: list[str],
    extra: dict[str, Any] | None = None,
) -> FuelDuplicateIngestionConflict:
    return FuelDuplicateIngestionConflict(
        code=code,
        message=message,
        provider=identity.provider,
        existing_import_id=str(match.import_id),
        existing_status=match.review_status or "PENDING",
        existing_uploaded_at=match.uploaded_at.isoformat() if match.uploaded_at else None,
        invoice_number=identity.invoice_number or match.invoice_number,
        invoice_date=identity.invoice_date or match.invoice_date,
        start_date=identity.start_date or match.start_date,
        end_date=identity.end_date or match.end_date,
        matched_on=matched_on,
        extra=extra or {},
    )


def business_document_advisory_lock_key(
    tenant_id: int,
    provider_code: str,
    invoice_number: str,
) -> int | None:
    """Canonical concurrency key for provider document ingestion (BVD PDF today)."""
    ident = BvdDocumentIdentity(
        provider=provider_code,
        invoice_number=_norm_text(invoice_number),
        invoice_date="",
        start_date="",
        end_date="",
    )
    return ident.business_lock_key(tenant_id)


async def acquire_bvd_import_advisory_lock(db: AsyncSession, *, tenant_id: int, identity: BvdDocumentIdentity) -> None:
    """Hold until transaction ends; serializes same tenant+provider+invoice_number imports."""
    key = identity.business_lock_key(tenant_id)
    if key is None:
        return
    from sqlalchemy import text

    await db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": key})


async def check_bvd_pdf_duplicate_before_import(
    db: AsyncSession,
    *,
    tenant_id: int,
    pdf_bytes: bytes,
    filename: str,
    extracted_rows: list[FuelBvdExtractedRow],
    permanent_only: bool = False,
    exclude_import_id: uuid.UUID | None = None,
) -> FuelDuplicateIngestionConflict | None:
    file_sha = sha256_hex(pdf_bytes)
    identity = document_identity_from_extracted_rows(extracted_rows)
    if permanent_only:
        sha_result = await db.execute(
            select(FuelBvd).where(
                FuelBvd.tenant_id == tenant_id,
                FuelBvd.source_file_sha256 == file_sha,
                FuelBvd.review_status == "SOURCE_REVIEWED",
            )
        )
        sha_matches: list[ExistingBvdImportMatch] = []
        by_import: dict[uuid.UUID, ExistingBvdImportMatch] = {}
        for row in sha_result.scalars().all():
            if row.import_id not in by_import or row.row_type == "HEADER":
                by_import[row.import_id] = ExistingBvdImportMatch(
                    import_id=row.import_id,
                    review_status=row.review_status,
                    uploaded_at=row.uploaded_at,
                    source_file_sha256=row.source_file_sha256,
                    source_file_name=row.source_file_name,
                    invoice_number=row.invoice_number,
                    invoice_date=row.invoice_date,
                    start_date=row.start_date,
                    end_date=row.end_date,
                )
        sha_matches = list(by_import.values())
        invoice_matches: list[ExistingBvdImportMatch] = []
        if identity.invoice_number:
            hdr_result = await db.execute(
                select(FuelBvd).where(
                    FuelBvd.tenant_id == tenant_id,
                    FuelBvd.row_type == "HEADER",
                    FuelBvd.invoice_number == identity.invoice_number,
                    FuelBvd.review_status == "SOURCE_REVIEWED",
                )
            )
            for row in hdr_result.scalars().all():
                invoice_matches.append(
                    ExistingBvdImportMatch(
                        import_id=row.import_id,
                        review_status=row.review_status,
                        uploaded_at=row.uploaded_at,
                        source_file_sha256=row.source_file_sha256,
                        source_file_name=row.source_file_name,
                        invoice_number=row.invoice_number,
                        invoice_date=row.invoice_date,
                        start_date=row.start_date,
                        end_date=row.end_date,
                    )
                )
    else:
        sha_matches = await _load_bvd_sha_matches(db, tenant_id=tenant_id, file_sha256=file_sha)
        invoice_matches = []
        if identity.invoice_number:
            invoice_matches = await _load_bvd_header_matches(
                db, tenant_id=tenant_id, invoice_number=identity.invoice_number
            )
    if exclude_import_id is not None:
        sha_matches = [m for m in sha_matches if m.import_id != exclude_import_id]
        invoice_matches = [m for m in invoice_matches if m.import_id != exclude_import_id]
    return evaluate_bvd_pdf_duplicate(
        file_sha256=file_sha,
        filename=filename,
        identity=identity,
        sha_matches=sha_matches,
        invoice_number_matches=invoice_matches,
    )


@dataclass(frozen=True)
class NationwideDocumentIdentity:
    provider: str
    invoice_number: str
    invoice_start_date: str
    invoice_end_date: str

    def is_complete(self) -> bool:
        return all([self.invoice_number, self.invoice_start_date, self.invoice_end_date])

    def business_lock_key(self, tenant_id: int) -> int | None:
        if not _norm_text(self.invoice_number):
            return None
        raw = f"{tenant_id}:{self.provider}:{_norm_text(self.invoice_number)}"
        return int(hashlib.sha256(raw.encode()).hexdigest()[:15], 16) % (2**31 - 1)


def document_identity_from_nationwide_rows(rows: Iterable[FuelNationwideExtractedRow]) -> NationwideDocumentIdentity:
    header = next((r for r in rows if r.row_type == "HEADER"), None)
    fields = header.fields if header else {}
    return NationwideDocumentIdentity(
        provider=NATIONWIDE_PROVIDER_CODE,
        invoice_number=_norm_text(fields.get("invoice_number")),
        invoice_start_date=_norm_text(fields.get("invoice_start_date")),
        invoice_end_date=_norm_text(fields.get("invoice_end_date")),
    )


def _nationwide_header_identity_matches(row: ExistingBvdImportMatch, identity: NationwideDocumentIdentity) -> bool:
    return (
        _norm_text(row.invoice_number) == identity.invoice_number
        and _norm_text(row.start_date) == identity.invoice_start_date
        and _norm_text(row.end_date) == identity.invoice_end_date
    )


def evaluate_nationwide_pdf_duplicate(
    *,
    file_sha256: str,
    filename: str,
    identity: NationwideDocumentIdentity,
    sha_matches: list[ExistingBvdImportMatch],
    invoice_number_matches: list[ExistingBvdImportMatch],
) -> FuelDuplicateIngestionConflict | None:
    matched_on: list[str] = []
    best: ExistingBvdImportMatch | None = None
    if sha_matches:
        matched_on.append("SHA256")
        best = pick_best_existing_import(sha_matches)
        if filename and any(_norm_text(m.source_file_name) == _norm_text(filename) for m in sha_matches):
            matched_on.append("FILE_NAME")
        if identity.is_complete() and any(_nationwide_header_identity_matches(m, identity) for m in sha_matches):
            matched_on.append("DOCUMENT_IDENTITY")
        return FuelDuplicateIngestionConflict(
            code=FUEL_DUPLICATE_EXACT,
            message="This Nationwide invoice file has already been uploaded.",
            provider=identity.provider,
            existing_import_id=str(best.import_id) if best else "",
            existing_status=best.review_status or "PENDING" if best else "PENDING",
            matched_on=matched_on,
        )
    identity_matches = [m for m in invoice_number_matches if _nationwide_header_identity_matches(m, identity)]
    if identity.is_complete() and identity_matches:
        best = pick_best_existing_import(identity_matches)
        return FuelDuplicateIngestionConflict(
            code=FUEL_DUPLICATE_DOCUMENT,
            message="This Nationwide invoice has already been uploaded.",
            provider=identity.provider,
            existing_import_id=str(best.import_id),
            existing_status=best.review_status or "PENDING",
            matched_on=["DOCUMENT_IDENTITY"],
        )
    return None


async def acquire_nationwide_import_advisory_lock(
    db: AsyncSession, *, tenant_id: int, identity: NationwideDocumentIdentity
) -> None:
    key = identity.business_lock_key(tenant_id)
    if key is None:
        return
    from sqlalchemy import text

    await db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": key})


async def check_nationwide_pdf_duplicate_before_import(
    db: AsyncSession,
    *,
    tenant_id: int,
    pdf_bytes: bytes,
    filename: str,
    extracted_rows: list[FuelNationwideExtractedRow],
    permanent_only: bool = False,
    exclude_import_id: uuid.UUID | None = None,
) -> FuelDuplicateIngestionConflict | None:
    file_sha = sha256_hex(pdf_bytes)
    identity = document_identity_from_nationwide_rows(extracted_rows)
    sha_matches: list[ExistingBvdImportMatch] = []
    invoice_matches: list[ExistingBvdImportMatch] = []
    sha_result = await db.execute(
        select(FuelNationwide).where(
            FuelNationwide.tenant_id == tenant_id,
            FuelNationwide.source_file_sha256 == file_sha,
            FuelNationwide.review_status == "SOURCE_REVIEWED",
        )
    )
    by_import: dict[uuid.UUID, ExistingBvdImportMatch] = {}
    for row in sha_result.scalars().all():
        if row.import_id not in by_import or row.row_type == "HEADER":
            by_import[row.import_id] = ExistingBvdImportMatch(
                import_id=row.import_id,
                review_status=row.review_status,
                uploaded_at=row.uploaded_at,
                source_file_sha256=row.source_file_sha256,
                source_file_name=row.source_file_name,
                invoice_number=row.invoice_number,
                invoice_date=row.invoice_start_date,
                start_date=row.invoice_start_date,
                end_date=row.invoice_end_date,
            )
    sha_matches = list(by_import.values())
    if identity.invoice_number:
        hdr_result = await db.execute(
            select(FuelNationwide).where(
                FuelNationwide.tenant_id == tenant_id,
                FuelNationwide.row_type == "HEADER",
                FuelNationwide.invoice_number == identity.invoice_number,
                FuelNationwide.review_status == "SOURCE_REVIEWED",
            )
        )
        for row in hdr_result.scalars().all():
            invoice_matches.append(
                ExistingBvdImportMatch(
                    import_id=row.import_id,
                    review_status=row.review_status,
                    uploaded_at=row.uploaded_at,
                    source_file_sha256=row.source_file_sha256,
                    source_file_name=row.source_file_name,
                    invoice_number=row.invoice_number,
                    invoice_date=row.invoice_start_date,
                    start_date=row.invoice_start_date,
                    end_date=row.invoice_end_date,
                )
            )
    if exclude_import_id is not None:
        sha_matches = [m for m in sha_matches if m.import_id != exclude_import_id]
        invoice_matches = [m for m in invoice_matches if m.import_id != exclude_import_id]
    return evaluate_nationwide_pdf_duplicate(
        file_sha256=file_sha,
        filename=filename,
        identity=identity,
        sha_matches=sha_matches,
        invoice_number_matches=invoice_matches,
    )


# --- CSV normalized transaction fingerprint (provider-agnostic hook) ---


def _decimal_norm(value: str | None) -> str:
    if value is None or str(value).strip() == "":
        return ""
    raw = str(value).strip().replace(",", "")
    try:
        d = Decimal(raw)
    except InvalidOperation:
        return _norm_text(value)
    return format(d.normalize(), "f")


def _txn_fingerprint_row(row: dict[str, Any]) -> dict[str, str]:
    return {
        "transaction_date": _norm_text(row.get("transaction_date")),
        "card_number": _norm_text(row.get("card_number") or row.get("card_id") or row.get("account_id")),
        "auth_code": _norm_text(row.get("auth_code") or row.get("provider_transaction_id") or row.get("reference_id")),
        "unit_number": _norm_text(row.get("unit_number")),
        "prod": _norm_text(row.get("prod") or row.get("product")),
        "qty": _decimal_norm(row.get("qty")),
        "final_amt": _decimal_norm(row.get("final_amt") or row.get("final_amount") or row.get("total")),
        "cur": _norm_text(row.get("cur") or row.get("currency")),
    }


def fuel_csv_transaction_fingerprint(transactions: list[dict[str, Any]]) -> str:
    """Deterministic SHA-256 over normalized provider transaction identity (order-independent)."""
    normalized = [_txn_fingerprint_row(t) for t in transactions]
    normalized.sort(key=lambda r: json.dumps(r, sort_keys=True, separators=(",", ":")))
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return sha256_hex(payload.encode("utf-8"))


def evaluate_csv_duplicate_layers(
    *,
    raw_sha256: str,
    existing_raw_sha: set[str],
    document_identity_key: str | None,
    existing_document_keys: set[str],
    transaction_fingerprint: str,
    existing_fingerprints: set[str],
    overlapping_auth_codes: set[str],
) -> FuelDuplicateIngestionConflict | None:
    """CSV decision matrix hook (no storage side effects)."""
    if raw_sha256 in existing_raw_sha:
        return FuelDuplicateIngestionConflict(
            code=FUEL_DUPLICATE_EXACT,
            message="This CSV file has already been uploaded.",
            matched_on=["SHA256"],
        )
    if document_identity_key and document_identity_key in existing_document_keys:
        return FuelDuplicateIngestionConflict(
            code=FUEL_DUPLICATE_DOCUMENT,
            message="This provider document has already been uploaded.",
            matched_on=["DOCUMENT_IDENTITY"],
        )
    if transaction_fingerprint in existing_fingerprints:
        return FuelDuplicateIngestionConflict(
            code=FUEL_DUPLICATE_TRANSACTIONS,
            message="These provider transactions have already been uploaded.",
            matched_on=["TRANSACTION_FINGERPRINT"],
        )
    if overlapping_auth_codes:
        return FuelDuplicateIngestionConflict(
            code=FUEL_TRANSACTION_OVERLAP,
            message="This CSV overlaps existing provider transaction IDs.",
            matched_on=["TRANSACTION_ID_OVERLAP"],
            extra={"overlap_count": len(overlapping_auth_codes), "sample_ids": sorted(overlapping_auth_codes)[:5]},
        )
    return None
