"""POD revision graph: x5 and DW-1 histories must not both create the table."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from scripts.tenant_revision_plan import (
    DW1C,
    POD_DW1,
    POD_X5,
    X5,
    RevisionPlanError,
    assert_target_matches_history,
    fuel_test_migrate_target,
    migration_target_for_request,
    upgrade_plan,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def script() -> ScriptDirectory:
    cfg = Config(str(ROOT / "alembic_tenant.ini"))
    return ScriptDirectory.from_config(cfg)


def _heads(script: ScriptDirectory) -> set[str]:
    return set(script.get_heads())


def test_approved_heads_are_exactly_the_pod_pair(script: ScriptDirectory) -> None:
    assert _heads(script) == {POD_DW1, POD_X5}


def test_x5_plan_creates_pod_once_without_dw1(script: ScriptDirectory) -> None:
    plan = assert_target_matches_history(script, X5, POD_X5)
    assert plan == [POD_X5]
    assert POD_DW1 not in plan
    assert DW1C not in plan


def test_empty_database_x5_target_does_not_include_dw1_pod(script: ScriptDirectory) -> None:
    plan = upgrade_plan(script, None, POD_X5)
    assert POD_X5 in plan
    assert POD_DW1 not in plan
    assert DW1C not in plan
    assert plan.count(POD_X5) == 1


def test_dw1c_plan_creates_pod_once_without_x5_revision(script: ScriptDirectory) -> None:
    plan = assert_target_matches_history(script, DW1C, POD_DW1)
    assert plan == [POD_DW1]
    assert POD_X5 not in plan


def test_existing_i14_refuses_second_pod_revision(script: ScriptDirectory) -> None:
    with pytest.raises(RevisionPlanError, match="already at"):
        assert_target_matches_history(script, POD_DW1, POD_X5)
    with pytest.raises(RevisionPlanError, match="already at"):
        assert_target_matches_history(script, POD_X5, POD_DW1)


def test_upgrade_heads_from_x5_would_run_both_pod_revisions(script: ScriptDirectory) -> None:
    """`upgrade heads` from x5 reaches both branches. That plan is forbidden."""
    pending: set[str] = set()
    for head in script.get_heads():
        pending.update(upgrade_plan(script, X5, head))
    assert POD_X5 in pending
    assert POD_DW1 in pending
    with pytest.raises(Exception, match="multiple heads"):
        script.get_current_head()


def test_explicit_tenant_targets_stay_usable_and_head_fails_closed(script: ScriptDirectory) -> None:
    assert migration_target_for_request(script, X5, POD_X5) == POD_X5
    assert migration_target_for_request(script, DW1C, POD_DW1) == POD_DW1
    assert migration_target_for_request(script, POD_DW1, POD_DW1) == POD_DW1
    assert migration_target_for_request(script, POD_X5, POD_X5) == POD_X5
    with pytest.raises(RevisionPlanError, match="refusing upgrade head"):
        migration_target_for_request(script, X5, "head")
    with pytest.raises(RevisionPlanError, match="refusing upgrade head"):
        migration_target_for_request(script, None, None)
    with pytest.raises(RevisionPlanError, match="already at"):
        migration_target_for_request(script, POD_DW1, POD_X5)
    with pytest.raises(RevisionPlanError, match="allowlist|must be one of"):
        migration_target_for_request(script, X5, "dw1c_composite_fk_set_null_optional_columns")


def test_fuel_migrate_picks_one_branch_and_rejects_the_other(script: ScriptDirectory) -> None:
    assert fuel_test_migrate_target(script, X5) == POD_X5
    assert fuel_test_migrate_target(script, None) == POD_X5
    assert fuel_test_migrate_target(script, DW1C) == POD_DW1
    assert fuel_test_migrate_target(script, POD_DW1) == POD_DW1
    assert fuel_test_migrate_target(script, POD_X5) == POD_X5
    x5_plan = upgrade_plan(script, X5, fuel_test_migrate_target(script, X5))
    dw1_plan = upgrade_plan(script, DW1C, fuel_test_migrate_target(script, DW1C))
    assert x5_plan == [POD_X5]
    assert dw1_plan == [POD_DW1]
    assert POD_DW1 not in x5_plan
    assert POD_X5 not in dw1_plan
    with pytest.raises(RevisionPlanError):
        fuel_test_migrate_target(script, "not-a-real-revision")
