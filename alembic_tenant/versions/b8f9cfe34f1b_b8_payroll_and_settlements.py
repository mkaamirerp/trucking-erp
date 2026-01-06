"""B8 payroll + settlements schema

Revision ID: b8f9cfe34f1b
Revises: f2d5b4be0ac2
Create Date: 2026-01-15 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from datetime import datetime

# revision identifiers, used by Alembic.
revision: str = "b8f9cfe34f1b"
down_revision: Union[str, Sequence[str], None] = "f2d5b4be0ac2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_enums(bind) -> None:
    worker_type = postgresql.ENUM(
        "EMPLOYEE_DRIVER",
        "CONTRACTOR_COMPANY_DRIVER",
        "OWNER_OPERATOR_LEASED_ON",
        "THIRD_PARTY_CARRIER",
        name="worker_type",
    )
    payee_type = postgresql.ENUM("DRIVER", "CARRIER", name="payee_type")
    pay_document_type = postgresql.ENUM(
        "PAYSTUB",
        "SETTLEMENT_STATEMENT",
        "CONTRACTOR_PAY_STATEMENT",
        "CARRIER_PAYOUT_STATEMENT",
        name="pay_document_type",
    )
    pay_run_status = postgresql.ENUM("DRAFT", "GENERATED", "FINALIZED", "VOIDED", name="pay_run_status")
    payout_status = postgresql.ENUM("UNPAID", "PARTIAL", "PAID", name="payout_status")
    source_type = postgresql.ENUM("EARNING", "DEDUCTION", "FEE", "ESCROW", "ADJUSTMENT", "TAX", name="source_type")
    responsibility = postgresql.ENUM("COMPANY", "WORKER", name="responsibility")
    calc_method = postgresql.ENUM(
        "ACTUAL", "FLAT", "PERCENT_OF_GROSS", "PERCENT_OF_NET_AFTER_DISPATCH", name="calc_method"
    )
    frequency = postgresql.ENUM(
        "ONE_TIME", "WEEKLY", "BIWEEKLY", "MONTHLY", "QUARTERLY", "YEARLY", name="frequency"
    )
    gross_calc_type = postgresql.ENUM(
        "CPM", "PERCENT_REVENUE", "FLAT_PER_LOAD", "HOURLY", "SALARY", "HYBRID", name="gross_calc_type"
    )
    settlement_frequency = postgresql.ENUM("WEEKLY", "BIWEEKLY", "SEMI_MONTHLY", "MONTHLY", name="settlement_frequency")
    mile_source = postgresql.ENUM(
        "ADDRESS_TO_ADDRESS", "ZIP_TO_ZIP", "CITY_TO_CITY", "MANUAL", name="mile_source"
    )
    pay_mile_mode = postgresql.ENUM(
        "ALL_MILES", "LOADED_ONLY", "LOADED_AND_EMPTY_DIFFERENT_RATES", name="pay_mile_mode"
    )
    escrow_rule_type = postgresql.ENUM("HOLD_WEEKS", "HOLD_FIXED_PER_PERIOD", "HOLD_UNTIL_TARGET", name="escrow_rule_type")
    escrow_entry_type = postgresql.ENUM("HOLD", "RELEASE", "ADJUSTMENT", name="escrow_entry_type")
    override_type = postgresql.ENUM("CHANGE_AMOUNT", "ADD_ITEM", "REMOVE_ITEM", name="override_type")
    payout_payment_status = postgresql.ENUM("PENDING", "SENT", "CONFIRMED", "FAILED", "VOIDED", name="payout_payment_status")

    for enum_type in [
        worker_type,
        payee_type,
        pay_document_type,
        pay_run_status,
        payout_status,
        source_type,
        responsibility,
        calc_method,
        frequency,
        gross_calc_type,
        settlement_frequency,
        mile_source,
        pay_mile_mode,
        escrow_rule_type,
        escrow_entry_type,
        override_type,
        payout_payment_status,
    ]:
        enum_type.create(bind, checkfirst=True)


def _drop_enums(bind) -> None:
    for name in [
        "payout_payment_status",
        "override_type",
        "escrow_entry_type",
        "escrow_rule_type",
        "pay_mile_mode",
        "mile_source",
        "settlement_frequency",
        "gross_calc_type",
        "frequency",
        "calc_method",
        "responsibility",
        "source_type",
        "payout_status",
        "pay_run_status",
        "pay_document_type",
        "payee_type",
        "worker_type",
    ]:
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)


def upgrade() -> None:
    """Upgrade schema to B8 payroll + settlements."""
    bind = op.get_bind()
    _create_enums(bind)

    inspector = sa.inspect(bind)

    # Preserve legacy employees table if present to avoid data loss; rename it before creating the new schema table.
    if inspector.has_table("employees"):
        legacy_name = f"employees_legacy_{datetime.utcnow().strftime('%Y%m%d')}"
        op.rename_table("employees", legacy_name)

    worker_type_enum = postgresql.ENUM(
        "EMPLOYEE_DRIVER",
        "CONTRACTOR_COMPANY_DRIVER",
        "OWNER_OPERATOR_LEASED_ON",
        "THIRD_PARTY_CARRIER",
        name="worker_type",
        create_type=False,
    )
    payee_type_enum = postgresql.ENUM("DRIVER", "CARRIER", name="payee_type", create_type=False)
    pay_document_type_enum = postgresql.ENUM(
        "PAYSTUB",
        "SETTLEMENT_STATEMENT",
        "CONTRACTOR_PAY_STATEMENT",
        "CARRIER_PAYOUT_STATEMENT",
        name="pay_document_type",
        create_type=False,
    )
    pay_run_status_enum = postgresql.ENUM("DRAFT", "GENERATED", "FINALIZED", "VOIDED", name="pay_run_status", create_type=False)
    payout_status_enum = postgresql.ENUM("UNPAID", "PARTIAL", "PAID", name="payout_status", create_type=False)
    source_type_enum = postgresql.ENUM("EARNING", "DEDUCTION", "FEE", "ESCROW", "ADJUSTMENT", "TAX", name="source_type", create_type=False)
    responsibility_enum = postgresql.ENUM("COMPANY", "WORKER", name="responsibility", create_type=False)
    calc_method_enum = postgresql.ENUM(
        "ACTUAL", "FLAT", "PERCENT_OF_GROSS", "PERCENT_OF_NET_AFTER_DISPATCH", name="calc_method", create_type=False
    )
    frequency_enum = postgresql.ENUM(
        "ONE_TIME", "WEEKLY", "BIWEEKLY", "MONTHLY", "QUARTERLY", "YEARLY", name="frequency", create_type=False
    )
    gross_calc_type_enum = postgresql.ENUM(
        "CPM", "PERCENT_REVENUE", "FLAT_PER_LOAD", "HOURLY", "SALARY", "HYBRID", name="gross_calc_type", create_type=False
    )
    settlement_frequency_enum = postgresql.ENUM(
        "WEEKLY", "BIWEEKLY", "SEMI_MONTHLY", "MONTHLY", name="settlement_frequency", create_type=False
    )
    mile_source_enum = postgresql.ENUM(
        "ADDRESS_TO_ADDRESS", "ZIP_TO_ZIP", "CITY_TO_CITY", "MANUAL", name="mile_source", create_type=False
    )
    pay_mile_mode_enum = postgresql.ENUM(
        "ALL_MILES",
        "LOADED_ONLY",
        "LOADED_AND_EMPTY_DIFFERENT_RATES",
        name="pay_mile_mode",
        create_type=False,
    )
    escrow_rule_type_enum = postgresql.ENUM(
        "HOLD_WEEKS", "HOLD_FIXED_PER_PERIOD", "HOLD_UNTIL_TARGET", name="escrow_rule_type", create_type=False
    )
    escrow_entry_type_enum = postgresql.ENUM("HOLD", "RELEASE", "ADJUSTMENT", name="escrow_entry_type", create_type=False)
    override_type_enum = postgresql.ENUM("CHANGE_AMOUNT", "ADD_ITEM", "REMOVE_ITEM", name="override_type", create_type=False)
    payout_payment_status_enum = postgresql.ENUM(
        "PENDING", "SENT", "CONFIRMED", "FAILED", "VOIDED", name="payout_payment_status", create_type=False
    )

