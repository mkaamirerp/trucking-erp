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
