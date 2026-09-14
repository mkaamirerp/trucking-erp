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


def test_replace_processed_meta_keeps_original_upload_key() -> None:
    intake = {
        "files": {
            "CDL_BACK": {
                "storage_key": "original.jpg",
                "enh_file_id": "processed.jpg",
                "dl_preprocess_status": "PROCESSED",
            },
            "CDL_BACK_PROCESSED": {"storage_key": "processed.jpg", "file_id": "processed.jpg"},
        }
    }
    next_intake = ro._replace_processed_file_meta(
        intake,
        "CDL_BACK",
        storage_key="rotated.jpg",
        original_filename="rotated.jpg",
        rotate_cw_deg=180,
    )
    assert next_intake["files"]["CDL_BACK"]["storage_key"] == "original.jpg"
    assert next_intake["files"]["CDL_BACK"]["enh_file_id"] == "rotated.jpg"
    assert next_intake["files"]["CDL_BACK"]["dl_manual_rotate_cw_deg"] == 180
    assert next_intake["files"]["CDL_BACK_PROCESSED"]["storage_key"] == "rotated.jpg"
    assert intake["files"]["CDL_BACK"]["enh_file_id"] == "processed.jpg"


def test_parse_manual_rotate_rejects_non_quarter_turns() -> None:
    assert ro._parse_manual_rotate_cw(0) == 0
    assert ro._parse_manual_rotate_cw(90) == 90
    assert ro._parse_manual_rotate_cw(180) == 180
    assert ro._parse_manual_rotate_cw(270) == 270
    with pytest.raises(ro.HTTPException) as exc:
        ro._parse_manual_rotate_cw(45)
    assert exc.value.status_code == 400


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


def test_processed_storage_key_is_enh_file_not_original() -> None:
    intake = {
        "files": {
            "CDL_BACK": {
                "storage_key": "original.jpg",
                "enh_file_id": "processed.jpg",
                "dl_preprocess_status": "PROCESSED",
            },
            "CDL_BACK_PROCESSED": {"storage_key": "processed.jpg"},
        }
    }
    assert ro._dl_processed_storage_key(intake, "CDL_BACK") == "processed.jpg"


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


@pytest.mark.asyncio
async def test_bake_manual_rotate_rewrites_processed_without_opencv(monkeypatch) -> None:
    import numpy as np
    import cv2
    from app.services.applicant_dl_opencv import encode_processed_jpeg

    src = np.zeros((40, 80, 3), dtype=np.uint8)
    src[0:10] = 255
    jpeg = encode_processed_jpeg(src)

    class Store:
        def read_bytes(self, key, module, slug):
            assert key == "processed.jpg"
            return jpeg

    saved: dict[str, object] = {}

    async def fake_save(_slug, _app_id, body, *, original_storage_key):
        saved["body"] = body
        saved["original_storage_key"] = original_storage_key
        return SimpleNamespace(storage_key="rotated.jpg", original_filename="rotated.jpg")

    monkeypatch.setattr("app.core.storage.get_storage", lambda: Store())
    monkeypatch.setattr("app.core.storage.save_applicant_dl_processed_bytes", fake_save)
    monkeypatch.setattr(
        "app.services.applicant_dl_preprocess.run_applicant_dl_opencv",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("OpenCV must not run on manual rotate")),
    )

    intake = {
        "files": {
            "CDL_BACK": {
                "storage_key": "original.jpg",
                "enh_file_id": "processed.jpg",
                "dl_preprocess_status": "PROCESSED",
            },
            "CDL_BACK_PROCESSED": {"storage_key": "processed.jpg"},
        }
    }
    out = await ro._bake_manual_rotate_into_processed(
        intake,
        tenant_slug="demo",
        application_id=1,
        doc_type="CDL_BACK",
        rotate_cw_deg=180,
    )
    assert saved["original_storage_key"] == "processed.jpg"
    assert out["files"]["CDL_BACK"]["storage_key"] == "original.jpg"
    assert ro._dl_processed_storage_key(out, "CDL_BACK") == "rotated.jpg"
    arr = cv2.imdecode(np.frombuffer(saved["body"], dtype=np.uint8), cv2.IMREAD_COLOR)
    assert arr is not None
    assert float(arr[-10:].mean()) > float(arr[:10].mean())
