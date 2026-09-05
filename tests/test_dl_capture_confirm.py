"""Phone DL capture: PROCESSED vs user-confirmed (Use This Photo)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.routers import driver_onboarding as ro


def test_phone_step_stays_front_until_user_confirms() -> None:
    intake = {"files": {"CDL_FRONT": {"dl_preprocess_status": "PROCESSED"}}}
    assert ro._dl_side_user_confirmed(intake, "CDL_FRONT") is False
    assert ro._dl_capture_phone_step(intake) == "FRONT"

    intake["files"]["CDL_FRONT"]["dl_user_confirmed"] = True
    assert ro._dl_capture_phone_step(intake) == "BACK"


def test_phone_step_allows_front_retake_after_processed() -> None:
    intake = {
        "files": {
            "CDL_FRONT": {"dl_preprocess_status": "PROCESSED"},
            "CDL_BACK": {"dl_preprocess_status": "MISSING"},
        }
    }
    assert ro._dl_capture_phone_step(intake) == "FRONT"
    expected = "CDL_FRONT" if ro._dl_capture_phone_step(intake) == "FRONT" else "CDL_BACK"
    assert expected == "CDL_FRONT"


def test_phone_step_stays_back_until_user_confirms() -> None:
    intake = {
        "files": {
            "CDL_FRONT": {"dl_preprocess_status": "PROCESSED", "dl_user_confirmed": True},
            "CDL_BACK": {"dl_preprocess_status": "PROCESSED"},
        }
    }
    assert ro._dl_capture_phone_step(intake) == "BACK"
    intake["files"]["CDL_BACK"]["dl_user_confirmed"] = True
    assert ro._dl_capture_phone_step(intake) == "COMPLETE"


def test_failed_side_is_not_confirmed() -> None:
    intake = {
        "files": {
            "CDL_FRONT": {"dl_preprocess_status": "FAILED", "dl_user_confirmed": True},
        }
    }
    assert ro._dl_side_user_confirmed(intake, "CDL_FRONT") is False
    assert ro._dl_capture_phone_step(intake) == "FRONT"


def test_mark_confirmed_does_not_change_preprocess_status() -> None:
    intake = {
        "files": {
            "CDL_FRONT": {"dl_preprocess_status": "PROCESSED", "enh_file_id": "front.jpg"},
        }
    }
    next_intake = ro._mark_dl_side_user_confirmed(intake, "CDL_FRONT")
    assert next_intake["files"]["CDL_FRONT"]["dl_preprocess_status"] == "PROCESSED"
    assert next_intake["files"]["CDL_FRONT"]["dl_user_confirmed"] is True
    assert next_intake["files"]["CDL_FRONT"]["enh_file_id"] == "front.jpg"
    assert intake["files"]["CDL_FRONT"].get("dl_user_confirmed") is not True


@pytest.mark.asyncio
async def test_maybe_complete_waits_for_user_confirm() -> None:
    access = SimpleNamespace(completed_at=None)
    intake = {
        "files": {
            "CDL_FRONT": {"dl_preprocess_status": "PROCESSED"},
            "CDL_BACK": {"dl_preprocess_status": "PROCESSED"},
        }
    }
    await ro._maybe_complete_dl_capture_token(None, access, intake)
    assert access.completed_at is None

    intake["files"]["CDL_FRONT"]["dl_user_confirmed"] = True
    await ro._maybe_complete_dl_capture_token(None, access, intake)
    assert access.completed_at is None

    intake["files"]["CDL_BACK"]["dl_user_confirmed"] = True
    await ro._maybe_complete_dl_capture_token(None, access, intake)
    assert access.completed_at is not None


def test_session_out_exposes_confirmed_flags() -> None:
    access = SimpleNamespace(completed_at=None)
    intake = {
        "files": {
            "CDL_FRONT": {
                "dl_preprocess_status": "PROCESSED",
                "enh_file_id": "front.jpg",
            }
        }
    }
    out = ro._dl_capture_session_out(access, intake)
    assert out.step == "FRONT"
    assert out.front_status == "PROCESSED"
    assert out.front_confirmed is False
    assert out.back_confirmed is False

    intake["files"]["CDL_FRONT"]["dl_user_confirmed"] = True
    out = ro._dl_capture_session_out(access, intake)
    assert out.step == "BACK"
    assert out.front_confirmed is True
