"""I5 — append-only notes on cancelled loads (policy contract, no HTTP)."""

from __future__ import annotations

import inspect

from app.services import loads as loads_service


def test_add_load_note_does_not_call_cancelled_commercial_guard() -> None:
    src = inspect.getsource(loads_service.add_load_note)
    assert "_reject_commercial_mutation_if_cancelled" not in src
