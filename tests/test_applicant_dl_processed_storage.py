from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.storage import LocalStorageBackend, save_applicant_dl_processed_bytes


@pytest.mark.asyncio
async def test_local_save_bytes_round_trip(tmp_path: Path) -> None:
    with patch("app.core.storage.settings") as settings:
        settings.local_storage_dir = str(tmp_path)
        settings.company_docs_dir = None
        backend = LocalStorageBackend()
        stored = await backend.save_bytes(
            "demo",
            "applicant_dl",
            "application",
            42,
            b"processed-jpeg-bytes",
            filename_hint="licence_processed.jpg",
            content_type="image/jpeg",
        )

        assert stored.storage_key.startswith("demo/applicant_dl/application/42/")
        assert stored.original_filename == "licence_processed.jpg"
        assert stored.content_type == "image/jpeg"
        assert backend.read_bytes(stored.storage_key) == b"processed-jpeg-bytes"


@pytest.mark.asyncio
async def test_processed_helper_writes_second_object_without_touching_original(tmp_path: Path) -> None:
    with patch("app.core.storage.settings") as settings:
        settings.storage_provider = "local"
        settings.local_storage_dir = str(tmp_path)
        settings.company_docs_dir = None

        import app.core.storage as storage_mod

        old_engine = storage_mod._engine
        storage_mod._engine = None
        try:
            original_key = "demo/applicant_dl/application/77/raw-original.jpg"
            original_path = tmp_path / original_key
            original_path.parent.mkdir(parents=True, exist_ok=True)
            original_path.write_bytes(b"RAW-UNCHANGED")

            processed = await save_applicant_dl_processed_bytes(
                "demo",
                77,
                b"DERIVED-PROCESSED",
                original_storage_key=original_key,
            )

            assert processed.storage_key != original_key
            assert (tmp_path / processed.storage_key).read_bytes() == b"DERIVED-PROCESSED"
            assert original_path.read_bytes() == b"RAW-UNCHANGED"
        finally:
            storage_mod._engine = old_engine
