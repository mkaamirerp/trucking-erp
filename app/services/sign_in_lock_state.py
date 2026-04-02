"""Sign-in lock snapshot (password streak + tenant+email rate buckets) for UI + admin unlock flows."""

from __future__ import annotations

from typing import Any

from app.core.database import AsyncSessionLocal
from app.services.login_password_abuse import get_login_password_fail_streak_snapshot
from app.services.login_unlock_step_up_pending import login_step_up_pending_after_unlock_exists
from app.utils.rate_limit import get_login_unlock_throttle_snapshot


async def build_sign_in_lock_state(tenant_id: int, email_norm: str) -> dict[str, Any]:
    """Structured lock state for one workspace + normalized email (not IP buckets)."""
    streak = await get_login_password_fail_streak_snapshot(tenant_id, email_norm)
    rates = get_login_unlock_throttle_snapshot(tenant_id, email_norm)
    async with AsyncSessionLocal() as pdb:
        post_unlock_step_up_pending = await login_step_up_pending_after_unlock_exists(pdb, tenant_id, email_norm)
    login_at = bool(rates.get("login_per_tenant_email", {}).get("at_limit"))
    step_issue_at = bool(rates.get("login_step_up_issue_per_tenant_email", {}).get("at_limit"))
    step_verify_at = bool(rates.get("login_step_up_verify_per_tenant_email", {}).get("at_limit"))
    step_at = step_issue_at or step_verify_at
    streak_hot = bool(streak.get("has_active_window")) and int(streak.get("streak_count") or 0) > 0
    friction = bool(streak.get("turnstile_armed")) or bool(streak.get("otp_step_up_armed"))
    return {
        "password_fail_streak": streak,
        "tenant_email_rate_limits": rates,
        "post_unlock_step_up_pending": post_unlock_step_up_pending,
        "overall": {
            "tenant_email_login_bucket_blocked": login_at,
            "tenant_email_step_up_bucket_blocked": step_at,
            "any_tenant_email_rate_bucket_blocked": login_at or step_at,
            "password_fail_streak_failures_in_window": int(streak.get("streak_count") or 0)
            if streak.get("has_active_window")
            else 0,
            "password_abuse_extra_friction_active": friction,
            "all_clear_for_tenant_email_unlock_tool": not streak_hot
            and not login_at
            and not step_at
            and not friction,
        },
    }


async def build_sign_in_security_panel(tenant_id: int, email_norm: str) -> dict[str, Any]:
    """
    Tenant-admin UI: human-readable sign-in protection breakdown (workspace+email + streak).
    Does not evaluate per-client IP buckets (not attributable to a single user row).
    """
    state = await build_sign_in_lock_state(tenant_id, email_norm)
    o = state["overall"]
    streak = state["password_fail_streak"]
    rates = state["tenant_email_rate_limits"]
    post_unlock_pending = bool(state.get("post_unlock_step_up_pending"))
    all_clear = bool(o["all_clear_for_tenant_email_unlock_tool"])

    reasons: list[str] = []
    triggers: list[str] = []

    nfail = int(o["password_fail_streak_failures_in_window"])
    pwd_friction = bool(streak.get("turnstile_armed")) or bool(streak.get("otp_step_up_armed"))

    issue_meta = rates.get("login_step_up_issue_per_tenant_email", {})
    verify_meta = rates.get("login_step_up_verify_per_tenant_email", {})

    if nfail > 0 or pwd_friction:
        reasons.append("Too many wrong password attempts")
        triggers.append("wrong_password_streak")
    if o["tenant_email_login_bucket_blocked"]:
        reasons.append("Too many sign-in attempts for this account in this workspace")
        triggers.append("tenant_email_login_rate")
    if bool(issue_meta.get("at_limit")):
        reasons.append("Too many code requests")
        triggers.append("tenant_email_step_up_issue")
    if bool(verify_meta.get("at_limit")):
        reasons.append("Too many code verification attempts")
        triggers.append("tenant_email_step_up_verify")
    if post_unlock_pending:
        reasons.append(
            "The sign-in block was cleared. For security, the next sign-in will ask for a verification code by email."
        )
        triggers.append("post_admin_unlock_step_up_once")

    deduped: list[str] = []
    seen: set[str] = set()
    for r in reasons:
        if r not in seen:
            seen.add(r)
            deduped.append(r)

    login_meta = rates.get("login_per_tenant_email", {})
    wrong_password_at_limit = bool(nfail > 0 or pwd_friction)

    if not all_clear:
        sign_in_status = "locked"
    elif post_unlock_pending:
        sign_in_status = "verification_on_next_sign_in"
    else:
        sign_in_status = "clear"

    return {
        "sign_in_status": sign_in_status,
        "all_clear": all_clear,
        "reasons": deduped,
        "trigger_sources": list(dict.fromkeys(triggers)),
        "timestamps": {
            "streak_window_started_at": streak.get("window_started_at"),
            "streak_window_expires_at": streak.get("window_expires_at"),
            "last_streak_activity_at": streak.get("streak_last_activity_at"),
        },
        "restriction_summary": {
            "workspace_email_login_at_limit": bool(o["tenant_email_login_bucket_blocked"]),
            "workspace_email_login_retry_after_seconds": int(login_meta.get("retry_after_seconds") or 0),
            "workspace_step_up_issue_at_limit": bool(issue_meta.get("at_limit")),
            "workspace_step_up_issue_retry_after_seconds": int(issue_meta.get("retry_after_seconds") or 0),
            "workspace_step_up_verify_at_limit": bool(verify_meta.get("at_limit")),
            "workspace_step_up_verify_retry_after_seconds": int(verify_meta.get("retry_after_seconds") or 0),
            "password_fail_streak_count": nfail,
            "wrong_password_attempts_at_limit": wrong_password_at_limit,
            "post_unlock_step_up_pending": post_unlock_pending,
        },
        "lock_scope": {
            "workspace_plus_email_unlock_supported": True,
            "ip_based_note": (
                "Some sign-in limits may be caused by the internet connection being used, not only by this user. "
                "Unlocking the user here clears the user-level lock only. If sign-in still does not work, "
                "wait a little and try again, or use a different internet connection."
            ),
        },
        "note": "",
    }
