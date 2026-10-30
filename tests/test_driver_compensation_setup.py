"""Driver compensation setup schema + onboarding minimum checks (no DB)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from types import SimpleNamespace

from app.models.enums import GrossCalcType, SettlementFrequency
from app.schemas.driver_compensation_setup import DriverCompensationSetupWrite
from app.services.driver_compensation_setup import compensation_profile_meets_onboarding_minimum


class TestDriverCompensationSetupWrite:
    def test_cpm_requires_loaded(self) -> None:
        with pytest.raises(ValidationError):
            DriverCompensationSetupWrite(
                gross_calc_type="CPM",
                cpm_loaded=None,
                settlement_frequency=SettlementFrequency.BIWEEKLY,
            )

    def test_cpm_ok(self) -> None:
        row = DriverCompensationSetupWrite(
            gross_calc_type="CPM",
            cpm_loaded=Decimal("0.62"),
            settlement_frequency=SettlementFrequency.WEEKLY,
            participates_in_fuel_discount_program=True,
        )
        assert row.gross_calc_type.value == "CPM"

    def test_percent_requires_rate(self) -> None:
        with pytest.raises(ValidationError):
            DriverCompensationSetupWrite(
                gross_calc_type="PERCENT_REVENUE",
                percent_rate=None,
                settlement_frequency=SettlementFrequency.BIWEEKLY,
            )


def _prof(**kwargs):
    base = {
        "gross_calc_type": GrossCalcType.CPM,
        "percent_rate": None,
        "cpm_loaded": Decimal("0.5"),
        "hourly_rate": None,
        "salary_amount": None,
        "flat_amount": None,
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_compensation_profile_meets_onboarding_minimum_cpm() -> None:
    assert compensation_profile_meets_onboarding_minimum(_prof(cpm_loaded=Decimal("0.01")))
    assert not compensation_profile_meets_onboarding_minimum(_prof(cpm_loaded=None))


def test_compensation_profile_meets_onboarding_minimum_percent() -> None:
    assert compensation_profile_meets_onboarding_minimum(
        _prof(
            gross_calc_type=GrossCalcType.PERCENT_REVENUE,
            percent_rate=Decimal("0.82"),
            cpm_loaded=None,
        )
    )
    assert not compensation_profile_meets_onboarding_minimum(
        _prof(
            gross_calc_type=GrossCalcType.PERCENT_REVENUE,
            percent_rate=None,
            cpm_loaded=None,
        )
    )


def _write(**kw):
    base = {"gross_calc_type": "PERCENT_REVENUE", "settlement_frequency": SettlementFrequency.BIWEEKLY}
    base.update(kw)
    return DriverCompensationSetupWrite(**base)


@pytest.mark.parametrize("value", ["0", "-0.1", "1.01", "75", "100", "0.12345", "abc", "NaN"])
def test_percent_rate_rejected_outside_fraction_or_precision(value: str) -> None:
    with pytest.raises(ValidationError):
        _write(percent_rate=value)


@pytest.mark.parametrize("value", ["0.0001", "0.75", "1", "1.0000"])
def test_percent_rate_accepted_as_fraction(value: str) -> None:
    assert _write(percent_rate=value).percent_rate == Decimal(value)


def test_percent_rate_never_divided() -> None:
    assert _write(percent_rate="0.75").percent_rate == Decimal("0.75")


def test_percent_rate_bounded_even_for_other_models() -> None:
    with pytest.raises(ValidationError):
        _write(gross_calc_type="CPM", cpm_loaded="0.5", percent_rate="75")


@pytest.mark.parametrize("loaded", ["0", "0.0000", "-0.1", "0.12345"])
def test_cpm_loaded_must_be_positive(loaded: str) -> None:
    with pytest.raises(ValidationError):
        _write(gross_calc_type="CPM", cpm_loaded=loaded)


def test_cpm_empty_may_be_zero() -> None:
    row = _write(gross_calc_type="CPM", cpm_loaded="0.55", cpm_empty="0")
    assert row.cpm_empty == Decimal("0")
    with pytest.raises(ValidationError):
        _write(gross_calc_type="CPM", cpm_loaded="0.55", cpm_empty="-0.01")


def test_readiness_rejects_zero_cpm_and_percent_over_one() -> None:
    assert not compensation_profile_meets_onboarding_minimum(_prof(cpm_loaded=Decimal("0")))
    assert not compensation_profile_meets_onboarding_minimum(
        _prof(gross_calc_type=GrossCalcType.PERCENT_REVENUE, percent_rate=Decimal("75"), cpm_loaded=None)
    )
    assert compensation_profile_meets_onboarding_minimum(
        _prof(gross_calc_type=GrossCalcType.PERCENT_REVENUE, percent_rate=Decimal("1"), cpm_loaded=None)
    )


def test_worker_type_mapping_requires_known_classification() -> None:
    from app.models.enums import WorkerType
    from app.services.driver_compensation_setup import worker_type_for_employment_relationship

    assert worker_type_for_employment_relationship("company_driver") == WorkerType.EMPLOYEE_DRIVER
    assert worker_type_for_employment_relationship("owner_operator") == WorkerType.OWNER_OPERATOR_LEASED_ON
    for unknown in (None, "", "contractor", "lease_purchase"):
        with pytest.raises(ValueError, match="driver_classification_unknown"):
            worker_type_for_employment_relationship(unknown)
