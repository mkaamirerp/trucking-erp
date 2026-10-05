"""Toll tenant models.

Segment 1: source batches + canonical transactions (schema foundation only).

Locked boundary: ingest/normalize/attach to a TruckERP vehicle/unit, then STOP.
Do not store owner-operator, driver, payroll, settlement, or financial-responsibility
fields on these tables. Downstream modules pull by tenant + unit + datetime range.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Final

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

SOURCE_TYPE_API: Final[str] = "API"
SOURCE_TYPE_FILE: Final[str] = "FILE"
SOURCE_TYPE_MANUAL: Final[str] = "MANUAL"
SOURCE_TYPES: Final[frozenset[str]] = frozenset(
    {SOURCE_TYPE_API, SOURCE_TYPE_FILE, SOURCE_TYPE_MANUAL}
)

FILE_FORMAT_PDF: Final[str] = "PDF"
FILE_FORMAT_CSV: Final[str] = "CSV"
FILE_FORMATS: Final[frozenset[str]] = frozenset({FILE_FORMAT_PDF, FILE_FORMAT_CSV})

TRANSACTION_TYPE_NORMAL: Final[str] = "NORMAL"
TRANSACTION_TYPE_VIOLATION: Final[str] = "VIOLATION"
TRANSACTION_TYPES: Final[frozenset[str]] = frozenset(
    {TRANSACTION_TYPE_NORMAL, TRANSACTION_TYPE_VIOLATION}
)

READ_TYPE_DEVICE: Final[str] = "DEVICE"
READ_TYPE_PLATE: Final[str] = "PLATE"
READ_TYPES: Final[frozenset[str]] = frozenset({READ_TYPE_DEVICE, READ_TYPE_PLATE})

BATCH_STATUS_RECEIVED: Final[str] = "RECEIVED"
BATCH_STATUS_PARSED: Final[str] = "PARSED"

# Canonical amount: NUMERIC(14, 4). Never IEEE float.
TOLL_AMOUNT_PRECISION: Final[tuple[int, int]] = (14, 4)

# Display "identifier" is derived later from read_type + device/plate. Not stored.


class TollSourceBatch(Base):
    """One Toll intake batch (API pull, FILE upload, or MANUAL group).

    PDF and CSV are file formats of FILE, not separate business source types.
    Provider connection/account are optional: FILE can exist with no account
    and no transponder.
    """

    __tablename__ = "toll_source_batches"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_toll_source_batches_tenant_id_id"),
        CheckConstraint(
            "source_type IN ('API', 'FILE', 'MANUAL')",
            name="ck_toll_source_batches_source_type",
        ),
        CheckConstraint(
            "file_format IS NULL OR file_format IN ('PDF', 'CSV')",
            name="ck_toll_source_batches_file_format",
        ),
        CheckConstraint(
            "source_type = 'FILE' OR file_format IS NULL",
            name="ck_toll_source_batches_file_format_file_only",
        ),
        CheckConstraint(
            "source_type <> 'FILE' OR file_format IS NOT NULL",
            name="ck_toll_source_batches_file_requires_format",
        ),
        CheckConstraint(
            "csv_raw_header_names IS NULL OR jsonb_typeof(csv_raw_header_names) = 'array'",
            name="ck_toll_source_batches_csv_raw_header_names_array",
        ),
        CheckConstraint(
            "csv_column_keys IS NULL OR jsonb_typeof(csv_column_keys) = 'array'",
            name="ck_toll_source_batches_csv_column_keys_array",
        ),
        Index("ix_toll_source_batches_tenant_id", "tenant_id"),
        Index("ix_toll_source_batches_tenant_provider", "tenant_id", "provider_code"),
        Index("ix_toll_source_batches_tenant_status", "tenant_id", "status"),
        Index("ix_toll_source_batches_tenant_source_hash", "tenant_id", "source_hash"),
        Index(
            "ix_toll_source_batches_tenant_source_import_ref",
            "tenant_id",
            "source_import_ref",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)

    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    file_format: Mapped[str | None] = mapped_column(String(16), nullable=True)

    provider_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    #: Future-safe placeholder. No Toll provider-connection table in Segment 1, so no FK.
    provider_connection_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    account_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)

    source_storage_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_import_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)

    statement_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    statement_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    invoice_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    invoice_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    #: Ordered original CSV header labels. JSON array; not JSONB object keys.
    csv_raw_header_names: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    #: Ordered normalized unique keys used in TollFileSourceRow.cells.
    csv_column_keys: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    csv_parsed_row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    csv_skipped_blank_row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    csv_parser_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    csv_parser_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    csv_encoding: Mapped[str | None] = mapped_column(String(32), nullable=True)
    csv_delimiter: Mapped[str | None] = mapped_column(String(8), nullable=True)

    status: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default=BATCH_STATUS_RECEIVED
    )

    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(36), nullable=True)


class TollFileSourceRow(Base):
    """One generic CSV source row awaiting provider/profile normalization.

    Cells keep original header keys and original text. No amount/date/unit mapping.
    """

    __tablename__ = "toll_file_source_rows"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_toll_file_source_rows_tenant_id_id"),
        UniqueConstraint(
            "tenant_id",
            "batch_id",
            "source_row_order",
            name="uq_toll_file_source_rows_tenant_batch_source_row_order",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["toll_source_batches.tenant_id", "toll_source_batches.id"],
            name="fk_toll_file_source_rows_batch_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "jsonb_typeof(cells) = 'object'",
            name="ck_toll_file_source_rows_cells_object",
        ),
        CheckConstraint(
            "jsonb_typeof(values) = 'array'",
            name="ck_toll_file_source_rows_values_array",
        ),
        Index("ix_toll_file_source_rows_tenant_id", "tenant_id"),
        Index("ix_toll_file_source_rows_tenant_batch", "tenant_id", "batch_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    batch_id: Mapped[int] = mapped_column(Integer, nullable=False)

    source_row_order: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Original CSV physical/source line. Independent of dense source_row_order.
    source_line_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_row_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    cells: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    values: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class TollTransaction(Base):
    """Canonical Toll transaction. Provider facts stay in provider_raw.

    Three identities:
    - id (+ tenant_id): TruckERP canonical transaction identity
    - provider_transaction_id: provider identity (e.g. PrePass tollId); not PK
    - (batch_id, source_row_order) / source_row_id: source document/file row identity

    Date + unit / datetime + unit / date + device are NOT unique.
    Multiple valid tolls may exist for one unit within minutes.
    """

    __tablename__ = "toll_transactions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_toll_transactions_tenant_id_id"),
        UniqueConstraint(
            "tenant_id",
            "batch_id",
            "source_row_order",
            name="uq_toll_transactions_tenant_batch_source_row_order",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            ["toll_source_batches.tenant_id", "toll_source_batches.id"],
            name="fk_toll_transactions_batch_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "truck_id"],
            ["trucks.tenant_id", "trucks.id"],
            name="fk_toll_transactions_truck_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "jsonb_typeof(provider_raw) = 'object'",
            name="ck_toll_transactions_provider_raw_object",
        ),
        CheckConstraint(
            "transaction_type IN ('NORMAL', 'VIOLATION')",
            name="ck_toll_transactions_transaction_type",
        ),
        CheckConstraint(
            "read_type IS NULL OR read_type IN ('DEVICE', 'PLATE')",
            name="ck_toll_transactions_read_type",
        ),
        Index("ix_toll_transactions_tenant_id", "tenant_id"),
        Index("ix_toll_transactions_tenant_batch", "tenant_id", "batch_id"),
        Index("ix_toll_transactions_tenant_date", "tenant_id", "transaction_date"),
        Index(
            "ix_toll_transactions_tenant_truck_datetime",
            "tenant_id",
            "truck_id",
            "transaction_datetime",
        ),
        Index(
            "ix_toll_transactions_tenant_unit_datetime",
            "tenant_id",
            "unit_number_snapshot",
            "transaction_datetime",
        ),
        Index(
            "ix_toll_transactions_tenant_provider_txn",
            "tenant_id",
            "provider_transaction_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    batch_id: Mapped[int] = mapped_column(Integer, nullable=False)

    provider_transaction_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_row_order: Mapped[int] = mapped_column(Integer, nullable=False)
    source_row_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    transaction_datetime_source: Mapped[str] = mapped_column(Text, nullable=False)
    transaction_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    transaction_datetime: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    truck_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unit_number_snapshot: Mapped[str | None] = mapped_column(String(64), nullable=True)

    toll_agency_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    toll_agency_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    amount: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)

    transaction_type: Mapped[str] = mapped_column(String(20), nullable=False)

    read_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    device_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    plate_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    plate_state: Mapped[str | None] = mapped_column(String(16), nullable=True)

    dispute_status: Mapped[str | None] = mapped_column(String(64), nullable=True)

    provider_raw: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
