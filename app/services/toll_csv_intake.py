"""Toll Segment 2: generic FILE/CSV intake.

Flow:
  receive CSV bytes
        ↓
  validate
        ↓
  SHA-256
        ↓
  tenant-scoped duplicate lookup (report, do not reject)
        ↓
  store original bytes (existing storage abstraction)
        ↓
  persist TollSourceBatch + TollFileSourceRow[] in one transaction
        ↓
  STOP — no provider map, no TollTransaction
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Final, Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import StoredFile, delete_toll_csv_file, save_toll_csv_file_bytes
from app.models.toll import (
    BATCH_STATUS_PARSED,
    FILE_FORMAT_CSV,
    SOURCE_TYPE_FILE,
    TollFileSourceRow,
    TollSourceBatch,
    TollTransaction,
)

logger = logging.getLogger(__name__)

MAX_TOLL_CSV_BYTES: Final[int] = 20 * 1024 * 1024
TOLL_CSV_PARSER_NAME: Final[str] = "generic_csv"
TOLL_CSV_PARSER_VERSION: Final[str] = "1"
TOLL_CSV_STORAGE_MODULE: Final[str] = "toll"
TOLL_CSV_PREVIEW_LIMIT: Final[int] = 5

_PDF_MAGIC: Final[bytes] = b"%PDF"
_ZIP_MAGIC: Final[bytes] = b"PK\x03\x04"
_UTF16_LE: Final[bytes] = b"\xff\xfe"
_UTF16_BE: Final[bytes] = b"\xfe\xff"

_REJECT_EXTENSIONS: Final[frozenset[str]] = frozenset(
    {".pdf", ".xlsx", ".xls", ".zip", ".png", ".jpg", ".jpeg", ".gif"}
)
_REJECT_CONTENT_TYPES: Final[frozenset[str]] = frozenset(
    {
        "application/pdf",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/zip",
        "image/png",
        "image/jpeg",
        "application/json",
    }
)
_ALLOWED_EXCEL_CSV_CONTENT_TYPE: Final[str] = "application/vnd.ms-excel"

TollCsvStoreBytes = Callable[..., Awaitable[StoredFile]]
TollCsvDeleteStored = Callable[..., None]


class TollCsvIntakeError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


@dataclass(frozen=True)
class TollCsvParsedRow:
    source_row_order: int
    cells: dict[str, str]
    values: tuple[str, ...]


@dataclass(frozen=True)
class TollCsvParseResult:
    encoding: str
    delimiter: str
    header_names: tuple[str, ...]
    cell_keys: tuple[str, ...]
    rows: tuple[TollCsvParsedRow, ...]
    skipped_blank_row_count: int
    byte_size: int
    source_hash: str
    parser_name: str = TOLL_CSV_PARSER_NAME
    parser_version: str = TOLL_CSV_PARSER_VERSION


@dataclass(frozen=True)
class TollCsvPersistResult:
    batch_id: int
    source_type: str
    file_format: str
    filename: str
    source_hash: str
    source_storage_ref: str
    row_count: int
    headers: tuple[str, ...]
    duplicate_match_count: int
    duplicate_batch_ids: tuple[int, ...]
    status: str
    preview_rows: tuple[dict[str, str], ...] = field(default_factory=tuple)
    provider_code: str | None = None

    def as_api_dict(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "source_type": self.source_type,
            "file_format": self.file_format,
            "filename": self.filename,
            "source_hash": self.source_hash,
            "source_storage_ref": self.source_storage_ref,
            "row_count": self.row_count,
            "headers": list(self.headers),
            "duplicate_match_count": self.duplicate_match_count,
            "duplicate_batch_ids": list(self.duplicate_batch_ids),
            "status": self.status,
            "preview_rows": list(self.preview_rows),
        }


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _filename_extension(filename: str) -> str:
    name = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if "." not in name:
        return ""
    return "." + name.rsplit(".", 1)[-1].strip().lower()


def _normalize_content_type(content_type: str | None) -> str | None:
    if content_type is None:
        return None
    return content_type.split(";", 1)[0].strip().lower() or None


def validate_toll_csv_file(
    *,
    filename: str,
    body: bytes,
    content_type: str | None = None,
) -> None:
    """Reject non-CSV FILE payloads. PDF remains FILE, but is not this parser."""
    if not body:
        raise TollCsvIntakeError("TOLL_CSV_EMPTY", "CSV file is empty")
    if len(body) > MAX_TOLL_CSV_BYTES:
        raise TollCsvIntakeError(
            "TOLL_CSV_TOO_LARGE",
            f"CSV file exceeds {MAX_TOLL_CSV_BYTES} bytes",
        )
    ext = _filename_extension(filename)
    if ext in _REJECT_EXTENSIONS:
        raise TollCsvIntakeError(
            "TOLL_CSV_NOT_CSV",
            "Toll CSV intake accepts CSV FILE sources only; PDF/binary formats are not parsed here",
        )
    normalized_type = _normalize_content_type(content_type)
    if normalized_type == _ALLOWED_EXCEL_CSV_CONTENT_TYPE and body[:4] != _ZIP_MAGIC:
        normalized_type = "text/csv"
    if normalized_type in _REJECT_CONTENT_TYPES:
        raise TollCsvIntakeError(
            "TOLL_CSV_NOT_CSV",
            "Declared content type is not a CSV FILE",
        )
    sample = body[:8]
    if sample.startswith(_PDF_MAGIC) or sample.startswith(_ZIP_MAGIC):
        raise TollCsvIntakeError(
            "TOLL_CSV_NOT_CSV",
            "File bytes are not CSV text",
        )
    if sample.startswith(_UTF16_LE) or sample.startswith(_UTF16_BE):
        raise TollCsvIntakeError(
            "TOLL_CSV_ENCODING",
            "UTF-16 CSV is not accepted; encode as UTF-8",
        )
    if b"\x00" in body[:8192]:
        raise TollCsvIntakeError("TOLL_CSV_BINARY", "CSV file contains binary NUL bytes")


def _decode_csv_text(body: bytes) -> tuple[str, str]:
    if body.startswith(b"\xef\xbb\xbf"):
        return body.decode("utf-8-sig"), "utf-8-sig"
    for encoding in ("utf-8", "cp1252"):
        try:
            return body.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise TollCsvIntakeError(
        "TOLL_CSV_ENCODING",
        "CSV file is not valid UTF-8 or Windows-1252 text",
    )


def _detect_delimiter(text: str) -> str:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","
    if delimiter not in {",", "\t", ";", "|"}:
        delimiter = ","
    return delimiter


def _uniquify_headers(headers: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    keys: list[str] = []
    for index, raw in enumerate(headers, start=1):
        base = raw.strip() if raw.strip() else f"column_{index}"
        count = seen.get(base, 0) + 1
        seen[base] = count
        keys.append(base if count == 1 else f"{base}__{count}")
    return keys


def parse_toll_csv_bytes(body: bytes) -> TollCsvParseResult:
    text, encoding = _decode_csv_text(body)
    if not text.strip():
        raise TollCsvIntakeError("TOLL_CSV_EMPTY", "CSV file has no text content")
    delimiter = _detect_delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    try:
        raw_headers = next(reader)
    except StopIteration as exc:
        raise TollCsvIntakeError("TOLL_CSV_NO_HEADER", "CSV file has no header row") from exc
    header_names = tuple(str(h) for h in raw_headers)
    if not any(name.strip() for name in header_names):
        raise TollCsvIntakeError("TOLL_CSV_NO_HEADER", "CSV file has no header row")
    cell_keys = tuple(_uniquify_headers(list(header_names)))

    rows: list[TollCsvParsedRow] = []
    skipped = 0
    for raw in reader:
        if not any(str(cell).strip() for cell in raw):
            skipped += 1
            continue
        values = tuple(str(cell) for cell in raw)
        cells: dict[str, str] = {}
        for index, key in enumerate(cell_keys):
            cells[key] = values[index] if index < len(values) else ""
        if len(values) > len(cell_keys):
            for extra_index in range(len(cell_keys), len(values)):
                cells[f"column_{extra_index + 1}"] = values[extra_index]
        rows.append(
            TollCsvParsedRow(
                source_row_order=len(rows) + 1,
                cells=cells,
                values=values,
            )
        )
    return TollCsvParseResult(
        encoding=encoding,
        delimiter=delimiter,
        header_names=header_names,
        cell_keys=cell_keys,
        rows=tuple(rows),
        skipped_blank_row_count=skipped,
        byte_size=len(body),
        source_hash=sha256_hex(body),
    )


def mapped_canonical_fields(row: Mapping[str, str]) -> dict[str, Any]:
    """No provider profile in Segment 2 — intermediate cells stay unmapped."""
    del row
    return {}


async def list_duplicate_batch_ids(
    db: AsyncSession,
    *,
    tenant_id: int,
    source_hash: str,
) -> list[int]:
    """Tenant-scoped SHA-256 lookup. Never unique-rejects. Never crosses tenants."""
    result = await db.execute(
        select(TollSourceBatch.id)
        .where(
            TollSourceBatch.tenant_id == tenant_id,
            TollSourceBatch.source_hash == source_hash,
        )
        .order_by(TollSourceBatch.id)
    )
    return [int(batch_id) for batch_id in result.scalars().all()]


async def persist_toll_csv_file(
    db: AsyncSession,
    *,
    tenant_id: int,
    tenant_slug: str,
    filename: str,
    body: bytes,
    content_type: str | None = None,
    created_by: str | None = None,
    provider_code: str | None = None,
    store_bytes: TollCsvStoreBytes | None = None,
    delete_stored: TollCsvDeleteStored | None = None,
) -> TollCsvPersistResult:
    """Validate, store original bytes, persist FILE batch + unmapped rows. No TollTransaction."""
    validate_toll_csv_file(filename=filename, body=body, content_type=content_type)
    parsed = parse_toll_csv_bytes(body)
    duplicate_batch_ids = tuple(
        await list_duplicate_batch_ids(
            db, tenant_id=tenant_id, source_hash=parsed.source_hash
        )
    )
    intake_token = uuid.uuid4().hex
    save_original = store_bytes or save_toll_csv_file_bytes
    remove_original = delete_stored or delete_toll_csv_file
    stored: StoredFile | None = None
    try:
        stored = await save_original(
            tenant_slug,
            intake_token,
            body,
            filename_hint=filename,
        )
        batch = TollSourceBatch(
            tenant_id=tenant_id,
            source_type=SOURCE_TYPE_FILE,
            file_format=FILE_FORMAT_CSV,
            provider_code=provider_code,
            source_storage_ref=stored.storage_key,
            source_hash=parsed.source_hash,
            source_filename=filename,
            status=BATCH_STATUS_PARSED,
            created_by=created_by,
            updated_by=created_by,
        )
        db.add(batch)
        await db.flush()
        if batch.id is None:
            raise TollCsvIntakeError(
                "TOLL_CSV_PERSIST",
                "FILE batch was not assigned an id",
                http_status=500,
            )
        for row in parsed.rows:
            db.add(
                TollFileSourceRow(
                    tenant_id=tenant_id,
                    batch_id=batch.id,
                    source_row_order=row.source_row_order,
                    source_row_id=None,
                    cells=dict(row.cells),
                    values=list(row.values),
                )
            )
        await db.flush()
        await db.commit()
    except Exception:
        await db.rollback()
        if stored is not None:
            try:
                remove_original(stored.storage_key, tenant_slug=tenant_slug)
            except Exception:
                logger.exception(
                    "Toll CSV intake storage cleanup failed after DB rollback tenant_slug=%s",
                    tenant_slug,
                )
        raise
    preview = tuple(dict(row.cells) for row in parsed.rows[:TOLL_CSV_PREVIEW_LIMIT])
    return TollCsvPersistResult(
        batch_id=int(batch.id),
        source_type=SOURCE_TYPE_FILE,
        file_format=FILE_FORMAT_CSV,
        filename=filename,
        source_hash=parsed.source_hash,
        source_storage_ref=stored.storage_key,
        row_count=len(parsed.rows),
        headers=parsed.header_names,
        duplicate_match_count=len(duplicate_batch_ids),
        duplicate_batch_ids=duplicate_batch_ids,
        status=BATCH_STATUS_PARSED,
        preview_rows=preview,
        provider_code=provider_code,
    )


def persist_created_canonical_transactions(
    db: AsyncSession, *, tenant_id: int, batch_id: int
) -> bool:
    """Segment 2 lock helper for tests: intake never hydrates toll_transactions."""
    _ = db, tenant_id, batch_id, TollTransaction
    return False
