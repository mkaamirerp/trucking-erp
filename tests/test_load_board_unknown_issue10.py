"""Issue I10 — unknown legacy statuses must not bucket as ready."""

from __future__ import annotations

from app.constants.load_integrity import LOAD_BOARD_UNKNOWN_STATUS_BUCKET
from app.schemas.load import ALLOWED_STATUSES
from app.services.loads import _legacy_board_bucket_for_status


def test_unknown_status_goes_to_unknown_bucket_not_ready():
    board = {s for s in ALLOWED_STATUSES if s != "draft"}
    assert _legacy_board_bucket_for_status("not_a_real_status", board) == LOAD_BOARD_UNKNOWN_STATUS_BUCKET
    assert _legacy_board_bucket_for_status("", board) == LOAD_BOARD_UNKNOWN_STATUS_BUCKET
    assert _legacy_board_bucket_for_status("ready", board) == "ready"
