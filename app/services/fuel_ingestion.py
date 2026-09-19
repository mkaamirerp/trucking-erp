"""Intended Fuel source-row ingestion boundary (Segment 2).

Parser/adapter/manual intake must hydrate rows through this API. A source row
identified by (tenant_id, batch_id, source_row_order) is either a
fuel_transaction or a fuel_source_control, never both.

This module does not run reconciliation.
"""

from __future__ import annotations

from typing import Any, Literal, Mapping, Protocol

from app.services.fuel_controls import (
    ROW_ROLE_CONTROL,
    ROW_ROLE_TRANSACTION,
    FuelControlRowError,
    assert_row_may_hydrate_as_transaction,
    classify_source_row_role,
    route_provider_source_rows,
)

IngestKind = Literal["transaction", "control"]


class FuelIngestionStore(Protocol):
    """Persistence view used by the ingestion API. SQLAlchemy can implement this later."""

    def transaction_source_row_exists(
        self, tenant_id: int, batch_id: int, source_row_order: int
    ) -> bool: ...

    def control_source_row_exists(
        self, tenant_id: int, batch_id: int, source_row_order: int
    ) -> bool: ...

    def add_transaction_source_row(
        self, tenant_id: int, batch_id: int, source_row_order: int
    ) -> None: ...

    def add_control_source_row(
        self, tenant_id: int, batch_id: int, source_row_order: int
    ) -> None: ...


class MemoryFuelIngestionStore:
    """In-memory occupancy for tests and pre-persist batch routing."""

    def __init__(self) -> None:
        self.transactions: set[tuple[int, int, int]] = set()
        self.controls: set[tuple[int, int, int]] = set()

    def transaction_source_row_exists(
        self, tenant_id: int, batch_id: int, source_row_order: int
    ) -> bool:
        return (tenant_id, batch_id, source_row_order) in self.transactions

    def control_source_row_exists(
        self, tenant_id: int, batch_id: int, source_row_order: int
    ) -> bool:
        return (tenant_id, batch_id, source_row_order) in self.controls

    def add_transaction_source_row(
        self, tenant_id: int, batch_id: int, source_row_order: int
    ) -> None:
        self.transactions.add((tenant_id, batch_id, source_row_order))

    def add_control_source_row(
        self, tenant_id: int, batch_id: int, source_row_order: int
    ) -> None:
        self.controls.add((tenant_id, batch_id, source_row_order))


def _row_type_and_label(row: Mapping[str, Any]) -> tuple[str | None, str | None]:
    raw_type = row.get("row_type") or row.get("row_type_raw")
    label = row.get("source_label") or row.get("control_label_raw")
    return (
        None if raw_type is None else str(raw_type),
        None if label is None else str(label),
    )


def _require_source_row_order(row: Mapping[str, Any]) -> int:
    order = row.get("source_row_order")
    if order is None:
        raise FuelControlRowError(
            "source_row_order is required to enforce transaction/control exclusivity"
        )
    return int(order)


def assert_source_row_exclusive(
    store: FuelIngestionStore,
    *,
    tenant_id: int,
    batch_id: int,
    source_row_order: int,
    target: IngestKind,
) -> None:
    """Reject the other occupancy for this source row. No cross-table DB UNIQUE required."""
    txn = store.transaction_source_row_exists(tenant_id, batch_id, source_row_order)
    ctl = store.control_source_row_exists(tenant_id, batch_id, source_row_order)
    if target == "transaction":
        if ctl:
            raise FuelControlRowError(
                "Source row already stored as a fuel_source_control; "
                "cannot hydrate the same (tenant_id, batch_id, source_row_order) "
                "as a fuel_transaction"
            )
        if txn:
            raise FuelControlRowError(
                "Source row already stored as a fuel_transaction"
            )
        return
    if txn:
        raise FuelControlRowError(
            "Source row already stored as a fuel_transaction; "
            "cannot hydrate the same (tenant_id, batch_id, source_row_order) "
            "as a fuel_source_control"
        )
    if ctl:
        raise FuelControlRowError(
            "Source row already stored as a fuel_source_control"
        )


def hydrate_as_transaction(
    *,
    tenant_id: int,
    batch_id: int,
    row: Mapping[str, Any],
    store: FuelIngestionStore,
) -> dict[str, Any]:
    """Force-transaction path still goes through exclusivity + role checks."""
    raw_type, label = _row_type_and_label(row)
    amount = row.get("total_amount", row.get("declared_amount", row.get("amount")))
    assert_row_may_hydrate_as_transaction(
        row_type_raw=raw_type, source_label=label, amount=amount
    )
    order = _require_source_row_order(row)
    assert_source_row_exclusive(
        store,
        tenant_id=tenant_id,
        batch_id=batch_id,
        source_row_order=order,
        target="transaction",
    )
    store.add_transaction_source_row(tenant_id, batch_id, order)
    return {"kind": "transaction", "tenant_id": tenant_id, "batch_id": batch_id, "row": dict(row)}


def hydrate_as_control(
    *,
    tenant_id: int,
    batch_id: int,
    row: Mapping[str, Any],
    store: FuelIngestionStore,
) -> dict[str, Any]:
    raw_type, label = _row_type_and_label(row)
    amount = row.get("declared_amount", row.get("total_amount", row.get("amount")))
    role = classify_source_row_role(
        row_type_raw=raw_type, source_label=label, amount=amount
    )
    if role == ROW_ROLE_TRANSACTION:
        raise FuelControlRowError(
            "TRANSACTION source rows must not hydrate fuel_source_controls"
        )
    order = _require_source_row_order(row)
    assert_source_row_exclusive(
        store,
        tenant_id=tenant_id,
        batch_id=batch_id,
        source_row_order=order,
        target="control",
    )
    store.add_control_source_row(tenant_id, batch_id, order)
    routed = route_provider_source_rows([row])["controls"][0]
    return {"kind": "control", "tenant_id": tenant_id, "batch_id": batch_id, "row": routed}


def ingest_source_row(
    *,
    tenant_id: int,
    batch_id: int,
    row: Mapping[str, Any],
    store: FuelIngestionStore,
) -> dict[str, Any]:
    """Canonical intake: classify, then hydrate exactly one of transaction or control."""
    raw_type, label = _row_type_and_label(row)
    amount = row.get("total_amount", row.get("declared_amount", row.get("amount")))
    role = classify_source_row_role(
        row_type_raw=raw_type, source_label=label, amount=amount
    )
    if role == ROW_ROLE_TRANSACTION:
        return hydrate_as_transaction(
            tenant_id=tenant_id, batch_id=batch_id, row=row, store=store
        )
    if role == ROW_ROLE_CONTROL:
        return hydrate_as_control(
            tenant_id=tenant_id, batch_id=batch_id, row=row, store=store
        )
    raise FuelControlRowError(f"Unrecognized source row role: {role}")
