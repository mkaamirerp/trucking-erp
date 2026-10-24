"""Plan a tenant Alembic upgrade and reject unsafe multi-branch plans.

Used by scripts/tenant_upgrade_revision.sh. Does not connect to a database.
"""

from __future__ import annotations

from alembic.script import ScriptDirectory

LN01_FMP = "ln01_load_number_periods_fmp"
LN01_X5 = "ln01_load_number_periods_x5"
APPROVED_SPLIT_HEADS = frozenset({LN01_FMP, LN01_X5})

POD_X5 = "i14_load_pod_evidence_x5"
POD_DW1 = "i14_load_pod_evidence"
APPROVED_POD_TARGETS = frozenset({POD_X5, POD_DW1})

FMP02 = "fmp02_fmp_tenant_scope"
X5 = "x5y6z7a8b9c0"
DW1C = "dw1c_composite_fk_set_null_optional_columns"
DW1D = "dw1d_load_commercial_evidence_retention_varchar32"


class RevisionPlanError(Exception):
    pass


def upgrade_plan(script: ScriptDirectory, current: str | None, target: str) -> list[str]:
    """Revisions Alembic would run to move `current` to `target`, oldest first.

    `current` None means base (empty alembic_version).
    """
    if target in {"head", "heads"}:
        raise RevisionPlanError("refusing upgrade head while tenant branches are split")
    lower = current or "base"
    try:
        pending = list(script.iterate_revisions(target, lower))
    except Exception as exc:
        raise RevisionPlanError(f"cannot plan {lower} -> {target}: {exc}") from exc
    return [rev.revision for rev in reversed(pending)]


def assert_ln01_plan_safe(plan: list[str], *, current: str | None, target: str) -> None:
    """Reject any plan that runs both ln01 sibling revisions."""
    if target not in APPROVED_SPLIT_HEADS:
        return
    ln_steps = [rev for rev in plan if rev in APPROVED_SPLIT_HEADS]
    if len(ln_steps) > 1:
        raise RevisionPlanError(
            "plan runs both load-number period revisions "
            f"({', '.join(ln_steps)}); refusing duplicate CREATE TABLE"
        )
    if target == LN01_X5 and LN01_FMP in plan:
        raise RevisionPlanError("x5 ln01 target plan includes the FMP ln01 revision")
    if target == LN01_FMP and LN01_X5 in plan:
        raise RevisionPlanError("FMP ln01 target plan includes the x5 ln01 revision")
    if current in APPROVED_SPLIT_HEADS and plan:
        raise RevisionPlanError(
            f"database is already at {current}; refusing a second ln01 revision"
        )


def assert_pod_plan_safe(plan: list[str], *, current: str | None, target: str) -> None:
    """Reject any plan that runs both POD revisions or the wrong branch."""
    if target not in APPROVED_POD_TARGETS:
        return
    pod_steps = [rev for rev in plan if rev in APPROVED_POD_TARGETS]
    if len(pod_steps) > 1:
        raise RevisionPlanError(
            "plan runs both POD revisions "
            f"({', '.join(pod_steps)}); refusing duplicate CREATE TABLE"
        )
    if target == POD_X5 and POD_DW1 in plan:
        raise RevisionPlanError("x5 POD target plan includes the DW-1 POD revision")
    if target == POD_DW1 and POD_X5 in plan:
        raise RevisionPlanError("DW-1 POD target plan includes the x5 POD revision")
    if current in APPROVED_POD_TARGETS and plan:
        raise RevisionPlanError(
            f"database is already at {current}; refusing a second POD revision"
        )
    if target == POD_X5 and current not in {None, X5} and DW1C in _ancestor_ids(plan, current):
        raise RevisionPlanError("refusing x5 POD revision on a DW-1 lineage database")


def _ancestor_ids(plan: list[str], current: str | None) -> set[str]:
    ids = set(plan)
    if current:
        ids.add(current)
    return ids


def ancestor_revisions(script: ScriptDirectory, revision: str) -> set[str]:
    found: set[str] = set()
    pending = [revision]
    while pending:
        rev_id = pending.pop()
        if not rev_id or rev_id in found:
            continue
        found.add(rev_id)
        try:
            rev = script.get_revision(rev_id)
        except Exception as exc:
            raise RevisionPlanError(f"unknown revision {rev_id}") from exc
        if rev is None:
            raise RevisionPlanError(f"unknown revision {rev_id}")
        pending.extend(rev._normalized_down_revisions)
    return found


def on_dw1_line(script: ScriptDirectory, current: str) -> bool:
    return any(
        rev == DW1C or rev.startswith("dw0") or rev.startswith("dw1")
        for rev in ancestor_revisions(script, current)
    )


def on_fmp_line(script: ScriptDirectory, current: str) -> bool:
    return FMP02 in ancestor_revisions(script, current) or current == FMP02


def pod_dw1_direct_parent(script: ScriptDirectory) -> str:
    rev = script.get_revision(POD_DW1)
    if rev is None:
        raise RevisionPlanError(f"unknown revision {POD_DW1}")
    parent = rev.down_revision
    if isinstance(parent, (list, tuple)):
        if len(parent) != 1:
            raise RevisionPlanError("unexpected merge parent for DW-1 POD revision")
        parent = parent[0]
    if not parent:
        raise RevisionPlanError("DW-1 POD revision has no down_revision")
    return str(parent)


def approved_heads_are_split(script: ScriptDirectory) -> bool:
    return set(script.get_heads()) == set(APPROVED_SPLIT_HEADS)


def migration_target_for_request(
    script: ScriptDirectory,
    current: str | None,
    requested: str | None,
) -> str:
    """Resolve one upgrade target. `head` is refused while the ln01 heads are split."""
    if requested in {None, "", "head", "heads"}:
        if approved_heads_are_split(script):
            raise RevisionPlanError("refusing upgrade head while tenant branches are split")
        if len(script.get_heads()) != 1:
            raise RevisionPlanError(f"unexpected tenant heads: {sorted(script.get_heads())}")
        return "head"
    if approved_heads_are_split(script) and requested not in APPROVED_SPLIT_HEADS:
        raise RevisionPlanError(
            f"target must be one of {sorted(APPROVED_SPLIT_HEADS)} while ln01 heads are split; got {requested!r}"
        )
    if requested in APPROVED_SPLIT_HEADS:
        if current == requested:
            return requested
        assert_target_matches_history(script, current, requested)
        return requested
    plan = upgrade_plan(script, current, requested)
    if POD_X5 in plan and POD_DW1 in plan:
        raise RevisionPlanError("plan runs both POD revisions; refusing duplicate CREATE TABLE")
    if LN01_X5 in plan and LN01_FMP in plan:
        raise RevisionPlanError("plan runs both ln01 revisions; refusing duplicate CREATE TABLE")
    return requested


def fuel_test_migrate_target(script: ScriptDirectory, current: str | None) -> str:
    """Pinned revision for Fuel's optional integration migrate. Never `head`."""
    if not approved_heads_are_split(script):
        heads = list(script.get_heads())
        if len(heads) != 1:
            raise RevisionPlanError(f"unexpected tenant heads: {sorted(heads)}")
        return heads[0]
    if current in APPROVED_SPLIT_HEADS:
        return current
    if current == FMP02 or (current is not None and on_fmp_line(script, current)):
        target = LN01_FMP
    elif current == POD_DW1 or (current is not None and on_dw1_line(script, current)):
        target = POD_DW1
    else:
        target = LN01_X5
    if current == target:
        return target
    assert_target_matches_history(script, current, target)
    return target


def assert_target_matches_history(script: ScriptDirectory, current: str | None, target: str) -> list[str]:
    """Return the upgrade plan or raise RevisionPlanError."""
    if current in APPROVED_SPLIT_HEADS and target in APPROVED_SPLIT_HEADS:
        raise RevisionPlanError(
            f"database is already at {current}; refusing a second ln01 revision"
        )
    if current in APPROVED_POD_TARGETS and target in APPROVED_POD_TARGETS:
        raise RevisionPlanError(
            f"database is already at {current}; refusing a second POD revision"
        )

    if target == LN01_X5 and current not in {None, X5, POD_X5}:
        if not (current == POD_X5 or ancestor_revisions(script, current) >= {POD_X5}):
            raise RevisionPlanError(
                f"{LN01_X5} is only for x5/POD-x5 lineage; current is {current}"
            )
    if target == LN01_FMP and current not in {None, FMP02}:
        if current != FMP02 and not on_fmp_line(script, current):
            raise RevisionPlanError(
                f"{LN01_FMP} requires FMP lineage (via {FMP02}); current is {current}"
            )

    if target == POD_X5 and current not in {None, X5}:
        raise RevisionPlanError(
            f"i14_load_pod_evidence_x5 is only for base or {X5}; current is {current}"
        )

    plan = upgrade_plan(script, current, target)

    if target == LN01_X5 and any(
        rev.startswith("dw0") or rev.startswith("dw1") or rev == POD_DW1 or rev == LN01_FMP
        for rev in plan
    ):
        raise RevisionPlanError("x5 ln01 plan would apply FMP/DW-1 revisions")
    if target == LN01_FMP and any(
        rev.startswith("dw0")
        or rev.startswith("dw1")
        or rev in {POD_DW1, POD_X5, LN01_X5}
        for rev in plan
    ):
        raise RevisionPlanError("FMP ln01 plan includes the x5 or DW-1 branch")

    if target == POD_X5 and any(
        rev.startswith("dw0") or rev.startswith("dw1") or rev == POD_DW1 for rev in plan
    ):
        raise RevisionPlanError("x5 POD plan would apply DW-1 revisions")
    if target == POD_DW1:
        parent = pod_dw1_direct_parent(script)
        if POD_X5 in plan:
            raise RevisionPlanError("DW-1 POD plan includes the x5 POD revision")
        if plan.count(POD_DW1) != 1:
            raise RevisionPlanError(f"DW-1 POD plan must apply {POD_DW1} exactly once; got {plan}")
        if current == parent:
            if plan != [POD_DW1]:
                raise RevisionPlanError(
                    "DW-1 POD plan would re-apply DW-1 revisions from the direct parent"
                )
        elif current is None or not on_dw1_line(script, current):
            raise RevisionPlanError(
                f"i14_load_pod_evidence requires DW-1 lineage (parent {parent}); current is {current}"
            )
        if plan[-1] != POD_DW1:
            raise RevisionPlanError(f"DW-1 POD plan must end at {POD_DW1}; got {plan}")

    if target in APPROVED_POD_TARGETS:
        assert_pod_plan_safe(plan, current=current, target=target)
    if target in APPROVED_SPLIT_HEADS:
        assert_ln01_plan_safe(plan, current=current, target=target)

    if target not in plan and current != target:
        raise RevisionPlanError(f"target {target} is not pending from {current}")
    return plan
