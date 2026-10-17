"""Plan a tenant Alembic upgrade and reject plans that would create POD twice.

Used by scripts/tenant_upgrade_revision.sh. Does not connect to a database.
"""

from __future__ import annotations

from alembic.script import ScriptDirectory

POD_X5 = "i14_load_pod_evidence_x5"
POD_DW1 = "i14_load_pod_evidence"
APPROVED_POD_TARGETS = frozenset({POD_X5, POD_DW1})
X5 = "x5y6z7a8b9c0"
DW1C = "dw1c_composite_fk_set_null_optional_columns"


class RevisionPlanError(Exception):
    pass


def upgrade_plan(script: ScriptDirectory, current: str | None, target: str) -> list[str]:
    """Revisions Alembic would run to move `current` to `target`, oldest first.

    `current` None means base (empty alembic_version).
    """
    if target in {"head", "heads"}:
        raise RevisionPlanError("refusing upgrade head while POD branches are split")
    lower = current or "base"
    try:
        pending = list(script.iterate_revisions(target, lower))
    except Exception as exc:
        raise RevisionPlanError(f"cannot plan {lower} -> {target}: {exc}") from exc
    return [rev.revision for rev in reversed(pending)]


def assert_pod_plan_safe(plan: list[str], *, current: str | None, target: str) -> None:
    """Reject any plan that runs both POD revisions or the wrong branch."""
    if target not in APPROVED_POD_TARGETS:
        raise RevisionPlanError(
            f"target must be one of {sorted(APPROVED_POD_TARGETS)}; got {target!r}"
        )
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
    if current in {POD_DW1, POD_X5} and plan:
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


def assert_target_matches_history(script: ScriptDirectory, current: str | None, target: str) -> list[str]:
    """Return the upgrade plan or raise RevisionPlanError.

    Approved histories:
    - empty or x5 -> i14_load_pod_evidence_x5 (no DW-1 POD revision)
    - dw1c -> i14_load_pod_evidence (no x5 POD revision)
    """
    if current in APPROVED_POD_TARGETS:
        raise RevisionPlanError(
            f"database is already at {current}; refusing a second POD revision"
        )
    if target == POD_X5 and current not in {None, X5}:
        raise RevisionPlanError(
            f"i14_load_pod_evidence_x5 is only for base or {X5}; current is {current}"
        )
    if target == POD_DW1 and current != DW1C:
        raise RevisionPlanError(
            f"i14_load_pod_evidence is only for {DW1C}; current is {current}"
        )
    plan = upgrade_plan(script, current, target)
    if target == POD_X5 and any(
        rev.startswith("dw0") or rev.startswith("dw1") or rev == POD_DW1 for rev in plan
    ):
        raise RevisionPlanError("x5 POD plan would apply DW-1 revisions")
    if target == POD_DW1 and (
        POD_X5 in plan or any(rev.startswith("dw0") or rev.startswith("dw1") for rev in plan)
    ):
        raise RevisionPlanError("DW-1 POD plan would re-apply DW-1 or the x5 POD revision")
    assert_pod_plan_safe(plan, current=current, target=target)
    if target not in plan:
        raise RevisionPlanError(f"target {target} is not pending from {current}")
    return plan
