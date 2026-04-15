"""Local storage: readable_path for applicant_dl keys (production local provider)."""

from __future__ import annotations

from pathlib import Path

import pytest

import app.core.config as app_config
import app.core.storage as storage_mod


@pytest.fixture(autouse=True)
def reset_storage_engine():
    yield
    storage_mod._engine = None


def test_readable_path_resolves_applicant_dl_under_configured_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    storage_mod._engine = None
    monkeypatch.setattr(app_config.settings, "storage_provider", "local", raising=False)
    monkeypatch.setattr(app_config.settings, "local_storage_dir", str(tmp_path), raising=False)

    key = "demo/applicant_dl/application/42/proof.jpg"
    dest = tmp_path / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"dl-bytes")

    with storage_mod.readable_path(key, "applicant_dl", "demo") as p:
        assert p.is_file()
        assert p.read_bytes() == b"dl-bytes"
