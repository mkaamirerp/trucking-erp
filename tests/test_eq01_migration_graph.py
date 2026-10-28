"""EQ01 migration graph safety: read-only, never runs Alembic upgrade."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from scripts.tenant_revision_plan import (
    APPROVED_EQ01_HEADS,
    APPROVED_RC01_HEADS,
    APPROVED_S1_HEADS,
    RC01_FMP,
    RC01_X5,
    DW1D, EQ01_FMP, EQ01_X5, FMP02, LN01_FMP, LN01_X5,
    POD_DW1, POD_X5, RevisionPlanError, S1_FMP, S1_X5, X5,
    assert_target_matches_history,
    fuel_test_migrate_target,
    migration_target_for_request,
    upgrade_plan,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def script() -> ScriptDirectory:
    return ScriptDirectory.from_config(Config(str(ROOT / "alembic_tenant.ini")))


def test_eq01_revisions_are_exactly_the_latest_pair(script: ScriptDirectory) -> None:
    assert set(script.get_heads()) == APPROVED_RC01_HEADS
    assert script.get_revision(RC01_FMP).down_revision == S1_FMP
    assert script.get_revision(RC01_X5).down_revision == S1_X5
    assert script.get_revision(S1_FMP).down_revision == EQ01_FMP
    assert script.get_revision(S1_X5).down_revision == EQ01_X5
    assert script.get_revision(EQ01_FMP).down_revision == LN01_FMP
    assert script.get_revision(EQ01_X5).down_revision == LN01_X5


@pytest.mark.parametrize(
    "current,target,expected",
    [
        (LN01_FMP, EQ01_FMP, [EQ01_FMP]),
        (LN01_X5, EQ01_X5, [EQ01_X5]),
        (FMP02, EQ01_FMP, [LN01_FMP, EQ01_FMP]),
        (POD_X5, EQ01_X5, [LN01_X5, EQ01_X5]),
        (X5, EQ01_X5, [POD_X5, LN01_X5, EQ01_X5]),
    ],
)
def test_eq01_pinned_upgrade_plan_contains_one_correct_sibling(
    script: ScriptDirectory, current: str, target: str, expected: list[str],
) -> None:
    assert assert_target_matches_history(script, current, target) == expected
    assert EQ01_FMP not in expected if target == EQ01_X5 else EQ01_X5 not in expected


@pytest.mark.parametrize(
    "current,target",
    [
        (LN01_FMP, EQ01_X5),
        (LN01_X5, EQ01_FMP),
        (FMP02, EQ01_X5),
        (X5, EQ01_FMP),
        (POD_DW1, EQ01_FMP),
        (POD_DW1, EQ01_X5),
        (EQ01_FMP, EQ01_X5),
        (EQ01_X5, EQ01_FMP),
    ],
)
def test_eq01_cross_branch_or_unrelated_lineage_fails_closed(
    script: ScriptDirectory, current: str, target: str,
) -> None:
    with pytest.raises(RevisionPlanError):
        assert_target_matches_history(script, current, target)


@pytest.mark.parametrize("target", [EQ01_X5, EQ01_FMP])
def test_eq01_reapply_same_revision_is_noop(script: ScriptDirectory, target: str) -> None:
    assert assert_target_matches_history(script, target, target) == []
    assert migration_target_for_request(script, target, target) == target


def test_eq01_head_and_historical_mis_target_refused(
    script: ScriptDirectory,
) -> None:
    for requested in (None, "head", "heads", ""):
        with pytest.raises(RevisionPlanError, match="refusing upgrade head"):
            migration_target_for_request(script, LN01_FMP, requested)
    with pytest.raises(RevisionPlanError, match="must be one of"):
        migration_target_for_request(script, LN01_FMP, LN01_FMP)
    with pytest.raises(RevisionPlanError, match="must be one of"):
        migration_target_for_request(script, X5, POD_X5)


def test_upgrade_both_repo_heads_from_x5_would_duplicate_eq01_and_is_forbidden(
    script: ScriptDirectory,
) -> None:
    candidate = set()
    for head in script.get_heads():
        candidate.update(upgrade_plan(script, X5, head))
    assert APPROVED_EQ01_HEADS.issubset(candidate)
    with pytest.raises(Exception, match="multiple heads"):
        script.get_current_head()


def test_rc01_plan_installs_one_sibling_and_refuses_the_other(script: ScriptDirectory) -> None:
    assert assert_target_matches_history(script, S1_FMP, RC01_FMP) == [RC01_FMP]
    assert assert_target_matches_history(script, S1_X5, RC01_X5) == [RC01_X5]
    assert assert_target_matches_history(script, EQ01_FMP, RC01_FMP) == [S1_FMP, RC01_FMP]
    assert RC01_X5 not in assert_target_matches_history(script, EQ01_FMP, RC01_FMP)
    assert assert_target_matches_history(script, RC01_FMP, RC01_FMP) == []
    for current, target in (
        (S1_X5, RC01_FMP),
        (S1_FMP, RC01_X5),
        (RC01_FMP, RC01_X5),
        (RC01_X5, RC01_FMP),
    ):
        with pytest.raises(RevisionPlanError):
            assert_target_matches_history(script, current, target)
    assert fuel_test_migrate_target(script, RC01_FMP) == RC01_FMP
    assert fuel_test_migrate_target(script, S1_FMP) == S1_FMP
    assert fuel_test_migrate_target(script, LN01_FMP) == EQ01_FMP


def test_fuel_test_migration_keeps_dw1_on_pod_and_eq01_appropriate_line(
    script: ScriptDirectory,
) -> None:
    assert fuel_test_migrate_target(script, DW1D) == POD_DW1
    assert fuel_test_migrate_target(script, POD_DW1) == POD_DW1
    assert fuel_test_migrate_target(script, LN01_FMP) == EQ01_FMP
    assert fuel_test_migrate_target(script, LN01_X5) == EQ01_X5
    assert fuel_test_migrate_target(script, None) == EQ01_X5


def test_shell_preflight_names_both_and_only_eq01_revision_heads() -> None:
    script_text = (ROOT / "scripts" / "tenant_migrate_preflight.sh").read_text()
    assert "APPROVED_EQ01_HEADS=" in script_text
    assert "eq01_equipment_attachments_fmp eq01_equipment_attachments_x5" in script_text
    assert 'elif [ "$HEAD_IDS" = "$APPROVED_EQ01_HEADS" ]; then' in script_text
    assert "upgrade head is forbidden" in script_text
