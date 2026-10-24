"""Task 14 checkpoint 1: paired ln01 revisions and tenant_load_number_periods DDL."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[1]

LN01_FMP = "ln01_load_number_periods_fmp"
LN01_X5 = "ln01_load_number_periods_x5"
FMP02 = "fmp02_fmp_tenant_scope"
POD_X5 = "i14_load_pod_evidence_x5"


@pytest.fixture(scope="module")
def script() -> ScriptDirectory:
    cfg = Config(str(ROOT / "alembic_tenant.ini"))
    return ScriptDirectory.from_config(cfg)


def test_ln01_heads_are_paired_siblings(script: ScriptDirectory) -> None:
    assert set(script.get_heads()) == {LN01_FMP, LN01_X5}


def test_ln01_down_revisions(script: ScriptDirectory) -> None:
    fmp = script.get_revision(LN01_FMP)
    x5 = script.get_revision(LN01_X5)
    assert fmp is not None and x5 is not None
    assert fmp.down_revision == FMP02
    assert x5.down_revision == POD_X5
