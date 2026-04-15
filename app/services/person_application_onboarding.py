"""Person application onboarding lifecycle helpers (approve vs onboard; setup_status).

HR/payroll modules are out of scope here — only state transitions and tenant UI mode reads.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.person_application_workflow import (
    WORKFLOW_LANE_COMPLETE,
    WORKFLOW_LANE_HR_PAYROLL,
    WORKFLOW_LANE_PROCESSING,
    WORKFLOW_LANE_REJECTED,
    WORKFLOW_LANE_SUBMITTED,
    normalize_workflow_lane,
)
from app.constants.person_onboarding import (
    PERSON_SETUP_UI_COMBINED,
    PERSON_SETUP_UI_MODES,
    PERSON_SETUP_UI_SEGMENTED,
    SETUP_STATUS_COMPLETE,
    SETUP_STATUS_PENDING,
    SETUP_STATUS_PENDING_DOWNSTREAM,
    normalize_person_setup_ui_mode,
    validate_person_setup_ui_mode_for_write,
)
from app.services.driver_compensation_setup import assert_combined_driver_onboarding_ready
from app.models.person_application import PersonApplication
from app.models.platform import PlatformTenant
from app.schemas.driver_onboarding import DriverOnboardingStatus


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def set_submitted_lane_on_applicant_submit(app: PersonApplication) -> None:
    """Applicant submitted (first time from DRAFT): queue ownership returns to admin inbox as submitted."""
    app.current_workflow_lane = WORKFLOW_LANE_SUBMITTED


def ensure_processing_lane_if_submitted_admin_engaged(app: PersonApplication) -> None:
    """Meaningful admin work on a SUBMITTED row moves routing off the submitted bucket."""
    if app.status != DriverOnboardingStatus.SUBMITTED.value:
        return
    if normalize_workflow_lane(getattr(app, "current_workflow_lane", None)) == WORKFLOW_LANE_SUBMITTED:
        app.current_workflow_lane = WORKFLOW_LANE_PROCESSING


def set_lane_after_manager_approve(app: PersonApplication, *, person_setup_ui_mode: str) -> None:
    """After first approval from SUBMITTED: combined → manager still owns until complete-onboarding; segmented → HR/payroll."""
    mode = normalize_person_setup_ui_mode(person_setup_ui_mode)
    if mode == PERSON_SETUP_UI_SEGMENTED:
        app.current_workflow_lane = WORKFLOW_LANE_HR_PAYROLL
    else:
        app.current_workflow_lane = WORKFLOW_LANE_PROCESSING


def set_rejected_lane(app: PersonApplication) -> None:
    app.current_workflow_lane = WORKFLOW_LANE_REJECTED


def is_driver_driver_person_application(app: PersonApplication) -> bool:
    """DRIVER workflow and DRIVER role — combined-mode driver blocks apply here only."""
    wf = (app.application_type or "DRIVER").strip().upper()
    rc = (app.requested_role_code or "DRIVER").strip().upper()
    return wf == "DRIVER" and rc == "DRIVER"


async def get_person_setup_ui_mode(platform_db: AsyncSession, tenant_id: int) -> str:
    """Tenant-level combined/segmented mode from platform_tenants."""
    tenant = await platform_db.get(PlatformTenant, int(tenant_id))
    if not tenant:
        return PERSON_SETUP_UI_COMBINED
    raw = getattr(tenant, "person_setup_ui_mode", None) or PERSON_SETUP_UI_COMBINED
    s = (raw if isinstance(raw, str) else str(raw)).strip().lower()
    return s if s in PERSON_SETUP_UI_MODES else PERSON_SETUP_UI_COMBINED


def setup_status_after_approval(person_setup_ui_mode: str) -> str:
    """
    Derive setup_status immediately after manager **approval** (accepted / promoted).

    Approval is intentionally **not** the same as full **onboarding completion**:
    both tenant UI modes land here in ``pending_downstream`` until an explicit
    ``complete-onboarding`` action sets ``complete`` (and ``onboarded_*``).

    - **segmented**: HR/payroll-owned setup remains outstanding → clearly downstream-pending.
    - **combined**: in-flow setup may be finished before approve, but lifecycle truth still
      advances via ``complete-onboarding`` so **approve** vs **onboard** stay separable.
    """
    _ = normalize_person_setup_ui_mode(person_setup_ui_mode)
    return SETUP_STATUS_PENDING_DOWNSTREAM


async def reconcile_person_application_lanes_for_tenant_ui_mode(
    tenant_db: AsyncSession,
    platform_db: AsyncSession,
    tenant_id: int,
) -> None:
    """Adjust APPROVED-incomplete routing lanes when tenant combined/segmented mode changes (or to fix drift).

    Does not touch complete or rejected rows. Does not modify status/setup_status timestamps.
    """
    mode = normalize_person_setup_ui_mode(await get_person_setup_ui_mode(platform_db, tenant_id))
    if mode == PERSON_SETUP_UI_SEGMENTED:
        await tenant_db.execute(
            update(PersonApplication)
            .where(
                PersonApplication.tenant_id == tenant_id,
                PersonApplication.status == DriverOnboardingStatus.APPROVED.value,
                PersonApplication.setup_status != SETUP_STATUS_COMPLETE,
                PersonApplication.current_workflow_lane == WORKFLOW_LANE_PROCESSING,
            )
            .values(current_workflow_lane=WORKFLOW_LANE_HR_PAYROLL)
        )
    else:
        await tenant_db.execute(
            update(PersonApplication)
            .where(
                PersonApplication.tenant_id == tenant_id,
                PersonApplication.status == DriverOnboardingStatus.APPROVED.value,
                PersonApplication.setup_status != SETUP_STATUS_COMPLETE,
                PersonApplication.current_workflow_lane == WORKFLOW_LANE_HR_PAYROLL,
            )
            .values(current_workflow_lane=WORKFLOW_LANE_PROCESSING)
        )
    await tenant_db.flush()


async def set_tenant_person_setup_ui_mode(
    platform_db: AsyncSession,
    tenant_id: int,
    mode: str,
) -> str:
    """Persist tenant person_setup_ui_mode. Raises ValueError if mode is invalid."""
    validated = validate_person_setup_ui_mode_for_write(mode)
    tenant = await platform_db.get(PlatformTenant, int(tenant_id))
    if not tenant:
        raise ValueError("tenant_not_found")
    tenant.person_setup_ui_mode = validated
    await platform_db.flush()
    return validated


async def finalize_person_application_onboarding(
    tenant_db: AsyncSession,
    *,
    tenant_id: int,
    application_id: int,
    actor_member_id: int | None,
    person_setup_ui_mode: str | None = None,
) -> PersonApplication:
    """
    Mark onboarding fully complete (onboarded_* + setup_status=complete).

    Idempotent: if already complete, returns the row unchanged.
    """
    res = await tenant_db.execute(
        select(PersonApplication)
        .where(
            PersonApplication.id == application_id,
            PersonApplication.tenant_id == tenant_id,
        )
        .with_for_update()
    )
    app = res.scalar_one_or_none()
    if not app:
        raise ValueError("application_not_found")
    if app.status != DriverOnboardingStatus.APPROVED.value:
        raise ValueError("application_not_approved")
    if getattr(app, "setup_status", None) == SETUP_STATUS_COMPLETE:
        return app

    if person_setup_ui_mode is not None:
        mode = normalize_person_setup_ui_mode(person_setup_ui_mode)
        if mode == PERSON_SETUP_UI_COMBINED and is_driver_driver_person_application(app):
            await assert_combined_driver_onboarding_ready(tenant_db, tenant_id=tenant_id, app=app)

    now = _utcnow()
    app.onboarded_at = now
    app.onboarded_by_user_id = actor_member_id
    app.setup_status = SETUP_STATUS_COMPLETE
    app.current_workflow_lane = WORKFLOW_LANE_COMPLETE
    await tenant_db.flush()
    return app


def apply_rejection_setup_state(app: PersonApplication) -> None:
    """Clear approval/onboarding completion when rejecting from SUBMITTED."""
    app.setup_status = SETUP_STATUS_PENDING
    app.onboarded_at = None
    app.onboarded_by_user_id = None
