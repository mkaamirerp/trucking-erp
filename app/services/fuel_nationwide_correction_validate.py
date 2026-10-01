"""Nationwide staging field correction validation."""

from __future__ import annotations

from app.services.fuel_nationwide_import import NATIONWIDE_SOURCE_FIELD_NAMES, ROW_TRANSACTION


class NationwideCorrectionValidationError(Exception):
    def __init__(self, field_name: str, message: str) -> None:
        super().__init__(message)
        self.field_name = field_name


EDITABLE_NATIONWIDE_FIELDS: frozenset[str] = frozenset(NATIONWIDE_SOURCE_FIELD_NAMES)


def validate_reviewed_nationwide_field(field_name: str, reviewed_value: str, *, row_type: str) -> None:
    if field_name not in EDITABLE_NATIONWIDE_FIELDS:
        raise NationwideCorrectionValidationError(field_name, f"field {field_name} is not editable")
    if row_type == ROW_TRANSACTION and field_name == "total" and not str(reviewed_value).strip():
        raise NationwideCorrectionValidationError(field_name, "total cannot be blank on transactions")
