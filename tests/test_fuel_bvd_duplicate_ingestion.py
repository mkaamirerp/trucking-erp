"""BVD PDF duplicate ingestion gate (money-safety)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services.fuel_bvd_extraction import ROW_HEADER, extract_bvd_rows_from_digital_pdf
from app.services.fuel_bvd_import import FuelBvdImportError, import_bvd_digital_pdf
from app.services.fuel_source_duplicate_gate import (
    BvdDocumentIdentity,
    ExistingBvdImportMatch,
    FUEL_DUPLICATE_DOCUMENT,
    FUEL_DUPLICATE_EXACT,
    FUEL_POSSIBLE_REVISION,
    business_document_advisory_lock_key,
    evaluate_bvd_pdf_duplicate,
    sha256_hex,
)

REPO = Path(__file__).resolve().parents[1]
BVD_PDF = REPO / "docs" / "fixtures" / "fuel" / "BVD_invoice_972201.pdf"


def _identity_from_pdf() -> BvdDocumentIdentity:
    rows, _, _ = extract_bvd_rows_from_digital_pdf(BVD_PDF.read_bytes())
    header = next(r for r in rows if r.row_type == ROW_HEADER)
    return BvdDocumentIdentity(
        provider="BVD",
        invoice_number=header.fields["invoice_number"] or "",
        invoice_date=header.fields["invoice_date"] or "",
        start_date=header.fields["start_date"] or "",
        end_date=header.fields["end_date"] or "",
    )


def _match(import_id: str, status: str = "PENDING", sha: str | None = None, name: str | None = None) -> ExistingBvdImportMatch:
    ident = _identity_from_pdf()
    return ExistingBvdImportMatch(
        import_id=uuid.UUID(import_id),
        review_status=status,
        uploaded_at=datetime.now(timezone.utc),
        source_file_sha256=sha,
        source_file_name=name,
        invoice_number=ident.invoice_number,
        invoice_date=ident.invoice_date,
        start_date=ident.start_date,
        end_date=ident.end_date,
    )


def test_pdf_exact_duplicate_by_sha() -> None:
    sha = sha256_hex(BVD_PDF.read_bytes())
    ident = _identity_from_pdf()
    conflict = evaluate_bvd_pdf_duplicate(
        file_sha256=sha,
        filename="renamed-july-fuel.pdf",
        identity=ident,
        sha_matches=[_match("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", sha=sha, name="other.pdf")],
        invoice_number_matches=[],
    )
    assert conflict is not None
    assert conflict.code == FUEL_DUPLICATE_EXACT
    assert "SHA256" in conflict.matched_on


def test_pdf_document_identity_duplicate_different_hash() -> None:
    ident = _identity_from_pdf()
    existing = _match("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", sha="differenthash", name="BVD_invoice_972201.pdf")
    conflict = evaluate_bvd_pdf_duplicate(
        file_sha256="newhashvalue",
        filename="july-fuel.pdf",
        identity=ident,
        sha_matches=[],
        invoice_number_matches=[existing],
    )
    assert conflict is not None
    assert conflict.code == FUEL_DUPLICATE_DOCUMENT
    assert "DOCUMENT_IDENTITY" in conflict.matched_on


def test_pdf_possible_revision_same_invoice_different_period() -> None:
    ident = _identity_from_pdf()
    other = ExistingBvdImportMatch(
        import_id=uuid.uuid4(),
        review_status="SOURCE_REVIEWED",
        uploaded_at=datetime.now(timezone.utc),
        source_file_sha256="other",
        source_file_name="BVD_invoice_972201.pdf",
        invoice_number=ident.invoice_number,
        invoice_date="2026-08-01 00:00:00",
        start_date="2026-08-01 00:00:00",
        end_date="2026-08-07 23:59:59",
    )
    conflict = evaluate_bvd_pdf_duplicate(
        file_sha256="brandnewhash",
        filename="BVD_invoice_972201.pdf",
        identity=ident,
        sha_matches=[],
        invoice_number_matches=[other],
    )
    assert conflict is not None
    assert conflict.code == FUEL_POSSIBLE_REVISION


def test_pdf_same_filename_different_identity_allowed() -> None:
    """Filename-only collision: lookup is by invoice_number, so no identity match → allow."""
    ident = BvdDocumentIdentity(
        provider="BVD",
        invoice_number="888888",
        invoice_date="2026-01-01 00:00:00",
        start_date="2026-01-01 00:00:00",
        end_date="2026-01-07 23:59:59",
    )
    assert (
        evaluate_bvd_pdf_duplicate(
            file_sha256="y",
            filename="statement.pdf",
            identity=ident,
            sha_matches=[],
            invoice_number_matches=[],
        )
        is None
    )


def test_advisory_lock_key_is_tenant_provider_invoice_only() -> None:
    ident = _identity_from_pdf()
    key_a = business_document_advisory_lock_key(53, "BVD", ident.invoice_number)
    key_b = business_document_advisory_lock_key(53, "BVD", ident.invoice_number)
    key_other_tenant = business_document_advisory_lock_key(99, "BVD", ident.invoice_number)
    assert key_a is not None
    assert key_a == key_b
    assert key_a != key_other_tenant
    ident_alt_dates = BvdDocumentIdentity(
        provider="BVD",
        invoice_number=ident.invoice_number,
        invoice_date="2099-01-01 00:00:00",
        start_date="2099-01-01 00:00:00",
        end_date="2099-01-07 23:59:59",
    )
    assert ident_alt_dates.business_lock_key(53) == key_a


def test_pick_best_existing_prefers_source_reviewed() -> None:
    from app.services.fuel_source_duplicate_gate import pick_best_existing_import

    a = _match("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", status="PENDING")
    b = _match("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", status="SOURCE_REVIEWED")
    best = pick_best_existing_import([a, b])
    assert str(best.import_id) == "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


class _FakeResult:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _GateSession:
    def __init__(self, headers: list, sha_rows: list) -> None:
        self.headers = headers
        self.sha_rows = sha_rows
        self.added: list = []

    async def execute(self, stmt):
        sql = str(stmt)
        if "source_file_sha256" in sql:
            return _FakeResult(self.sha_rows)
        return _FakeResult(self.headers)

    def add(self, obj) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass


@pytest.mark.asyncio
async def test_import_blocks_second_identical_upload(monkeypatch: pytest.MonkeyPatch) -> None:
    pdf = BVD_PDF.read_bytes()
    sha = sha256_hex(pdf)
    ident = _identity_from_pdf()
    header_row = type(
        "Row",
        (),
        {
            "import_id": uuid.uuid4(),
            "row_type": "HEADER",
            "review_status": "SOURCE_REVIEWED",
            "uploaded_at": datetime.now(timezone.utc),
            "source_file_sha256": sha,
            "source_file_name": "BVD_invoice_972201.pdf",
            "invoice_number": ident.invoice_number,
            "invoice_date": ident.invoice_date,
            "start_date": ident.start_date,
            "end_date": ident.end_date,
        },
    )()

    session = _GateSession(headers=[header_row], sha_rows=[header_row])

    async def _noop_lock(*_a, **_k):
        return None

    async def _fake_save(**_kwargs):
        return "storage/key.pdf", sha

    monkeypatch.setattr("app.services.fuel_bvd_import.acquire_bvd_import_advisory_lock", _noop_lock)
    monkeypatch.setattr("app.services.fuel_bvd_import.save_bvd_pdf_to_storage", _fake_save)

    with pytest.raises(FuelBvdImportError) as exc:
        await import_bvd_digital_pdf(
            session,
            tenant_id=53,
            tenant_slug="demo",
            pdf_bytes=pdf,
            filename="BVD_invoice_972201.pdf",
            uploaded_by="tester",
        )
    assert exc.value.http_status == 409
    assert exc.value.code == FUEL_DUPLICATE_EXACT
    assert exc.value.detail.get("existing_import_id")
    assert len(session.added) == 0


@pytest.mark.asyncio
async def test_import_first_upload_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    pdf = BVD_PDF.read_bytes()
    sha = sha256_hex(pdf)
    session = _GateSession(headers=[], sha_rows=[])

    async def _noop_lock(*_a, **_k):
        return None

    async def _fake_save(**_kwargs):
        return "storage/key.pdf", sha

    monkeypatch.setattr("app.services.fuel_bvd_import.acquire_bvd_import_advisory_lock", _noop_lock)
    monkeypatch.setattr("app.services.fuel_bvd_import.save_bvd_pdf_to_storage", _fake_save)

    import_id, count, status = await import_bvd_digital_pdf(
        session,
        tenant_id=99,
        tenant_slug="demo",
        pdf_bytes=pdf,
        filename="BVD_invoice_972201.pdf",
        uploaded_by="tester",
    )
    assert status == "SUCCESS"
    assert count == 24
    assert len(session.added) == 24
    assert session.added[0].tenant_id == 99


@pytest.mark.asyncio
async def test_process_bvd_import_review_is_idempotent() -> None:
    from unittest.mock import AsyncMock, MagicMock

    from app.services.fuel_bvd_review import BVD_REVIEW_SOURCE_COMPLETE, process_bvd_import_review

    db = AsyncMock()
    import_id = uuid.uuid4()
    summary = {
        "import_id": str(import_id),
        "invoice_number": "972201",
        "row_count": 24,
        "transaction_count": 2,
        "correction_count": 0,
        "review_status": BVD_REVIEW_SOURCE_COMPLETE,
    }
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.services.fuel_bvd_review.get_bvd_import_review_summary",
            AsyncMock(return_value=summary),
        )
        out = await process_bvd_import_review(
            db, tenant_id=53, import_id=import_id, reviewed_by="tester"
        )
    assert out["review_status"] == BVD_REVIEW_SOURCE_COMPLETE
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_concurrent_different_hash_same_invoice_serializes_to_one_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulate two uploads (hash AAA vs BBB) for the same BVD invoice; only one may commit."""
    pdf_a = BVD_PDF.read_bytes()
    pdf_b = pdf_a + b"%"
    sha_a = sha256_hex(pdf_a)
    sha_b = sha256_hex(pdf_b)
    assert sha_a != sha_b
    ident = _identity_from_pdf()

    business_key = business_document_advisory_lock_key(77, "BVD", ident.invoice_number)
    assert business_key is not None
    gate = asyncio.Lock()
    shared_headers: list = []

    class _ConcurrentSession:
        def __init__(self, label: str) -> None:
            self.label = label
            self.added: list = []
            self._holding = False

        async def execute(self, stmt, *args, **kwargs):
            sql = str(stmt)
            if "pg_advisory_xact_lock" in sql:
                await gate.acquire()
                self._holding = True
                return _FakeResult([])
            if "source_file_sha256" in sql:
                rows = []
                for h in shared_headers:
                    if h.source_file_sha256 == sha_a or h.source_file_sha256 == sha_b:
                        rows.append(h)
                return _FakeResult(rows)
            if "invoice_number" in sql and "HEADER" in sql:
                return _FakeResult(list(shared_headers))
            return _FakeResult([])

        def add(self, obj) -> None:
            self.added.append(obj)

        async def commit(self) -> None:
            if self.added:
                header = next((r for r in self.added if r.row_type == "HEADER"), self.added[0])
                shared_headers.append(header)
            if self._holding:
                gate.release()
                self._holding = False

    async def _fake_save(**kwargs):
        pdf_bytes = kwargs["pdf_bytes"]
        return "storage/key.pdf", sha256_hex(pdf_bytes)

    async def _real_lock(db, *, tenant_id, identity):
        from sqlalchemy import text

        key = identity.business_lock_key(tenant_id)
        await db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": key})

    monkeypatch.setattr("app.services.fuel_bvd_import.acquire_bvd_import_advisory_lock", _real_lock)
    monkeypatch.setattr(
        "app.services.fuel_bvd_import.save_bvd_pdf_to_storage",
        lambda **kw: _fake_save(pdf_bytes=kw.get("pdf_bytes")),
    )

    results: list = []

    async def run_upload(pdf: bytes, label: str) -> None:
        session = _ConcurrentSession(label)
        try:
            out = await import_bvd_digital_pdf(
                session,
                tenant_id=77,
                tenant_slug="demo",
                pdf_bytes=pdf,
                filename=f"{label}.pdf",
                uploaded_by=label,
            )
            results.append(("ok", out))
        except FuelBvdImportError as exc:
            results.append(("dup", exc))

    await asyncio.gather(run_upload(pdf_a, "A"), run_upload(pdf_b, "B"))

    ok_count = sum(1 for r in results if r[0] == "ok")
    dup_count = sum(1 for r in results if r[0] == "dup")
    assert ok_count == 1
    assert dup_count == 1
    dup_exc = next(r[1] for r in results if r[0] == "dup")
    assert dup_exc.code in (FUEL_DUPLICATE_DOCUMENT, FUEL_POSSIBLE_REVISION, FUEL_DUPLICATE_EXACT)
    assert len(shared_headers) == 1
