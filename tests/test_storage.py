"""Tests for storage abstraction: key generation, local backend, factory selection."""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import UploadFile

from app.core.storage import (
    build_storage_key,
    get_storage,
    LocalStorageBackend,
    S3StorageBackend,
    StoredFile,
)


class TestBuildStorageKey:
    def test_tenant_slug_first_segment(self) -> None:
        key = build_storage_key("demo", "onboarding", "application", 13, "license-front.jpg")
        assert key.startswith("demo/")
        assert "/onboarding/" in key
        assert "/application/" in key
        assert "/13/" in key
        assert key.endswith("license-front.jpg") or "license-front.jpg" in key

    def test_sanitizes_filename(self) -> None:
        key = build_storage_key("demo", "driver_docs", "document", 1, "../../evil.jpg")
        assert ".." not in key
        assert "evil" in key or "jpg" in key

    def test_stable_pattern(self) -> None:
        k1 = build_storage_key("acme", "company_docs", "company", 42, "w9.pdf")
        assert k1 == "acme/company_docs/company/42/w9.pdf"


class TestLegacyKeyCompatibility:
    """Legacy keys (no '/') and full keys (with '/') resolve correctly."""

    def test_legacy_key_under_module_dir(self, tmp_path: Path) -> None:
        """Legacy key 'old.pdf' resolves to <storage_root>/driver_docs/old.pdf (module dir + key)."""
        patcher = patch("app.core.storage.settings")
        mock_settings = patcher.start()
        mock_settings.local_storage_dir = str(tmp_path)
        mock_settings.company_docs_dir = None
        try:
            backend = LocalStorageBackend()
            path = tmp_path / "driver_docs" / "old.pdf"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"legacy content")
            data = backend.read_bytes("old.pdf", module="driver_docs", tenant_slug="demo")
            assert data == b"legacy content"
        finally:
            patcher.stop()

    def test_full_key_under_storage_root(self, tmp_path: Path) -> None:
        """Full key demo/driver_docs/document/1/file.pdf uses _storage_root() / key."""
        patcher = patch("app.core.storage.settings")
        mock_settings = patcher.start()
        mock_settings.local_storage_dir = str(tmp_path)
        mock_settings.company_docs_dir = None
        try:
            backend = LocalStorageBackend()
            path = tmp_path / "demo" / "driver_docs" / "document" / "1" / "file.pdf"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"full key content")
            data = backend.read_bytes("demo/driver_docs/document/1/file.pdf", None, None)
            assert data == b"full key content"
        finally:
            patcher.stop()


class TestLocalStorageBackend:
    @pytest.fixture
    def tmp_storage_dir(self, tmp_path: Path) -> Path:
        return tmp_path

    @pytest.fixture
    def local_backend(self, tmp_storage_dir: Path) -> LocalStorageBackend:
        patcher = patch("app.core.storage.settings")
        mock_settings = patcher.start()
        mock_settings.local_storage_dir = str(tmp_storage_dir)
        mock_settings.company_docs_dir = None
        try:
            backend = LocalStorageBackend()
            tmp_storage_dir.mkdir(parents=True, exist_ok=True)
            yield backend
        finally:
            patcher.stop()

    @pytest.mark.asyncio
    async def test_save_upload_creates_file(self, local_backend: LocalStorageBackend, tmp_storage_dir: Path) -> None:
        content = b"pdf content here"
        chunk_iter = iter([content])

        async def mock_read(sz: int) -> bytes:
            return next(chunk_iter, b"")

        file = MagicMock(spec=UploadFile)
        file.filename = "test.pdf"
        file.content_type = "application/pdf"
        file.read = mock_read

        result = await local_backend.save_upload("demo", "driver_docs", "document", 99, file)

        assert isinstance(result, StoredFile)
        assert result.storage_key.startswith("demo/")
        assert "driver_docs" in result.storage_key
        assert result.file_size_bytes == len(content)
        assert result.original_filename == "test.pdf"
        path = tmp_storage_dir / result.storage_key
        assert path.is_file()
        assert path.read_bytes() == content

    @pytest.mark.asyncio
    async def test_read_bytes_roundtrip(self, local_backend: LocalStorageBackend) -> None:
        content = b"hello world"
        first = [True]

        async def mock_read(sz: int) -> bytes:
            if first[0]:
                first[0] = False
                return content
            return b""

        file = MagicMock(spec=UploadFile)
        file.filename = "data.bin"
        file.content_type = None
        file.read = mock_read

        stored = await local_backend.save_upload("demo", "driver_docs", "document", 1, file)
        read_back = local_backend.read_bytes(stored.storage_key, None, None)
        assert read_back == content

    def test_exists_and_delete(self, local_backend: LocalStorageBackend, tmp_storage_dir: Path) -> None:
        key = "demo/driver_docs/document/1/test.txt"
        path = tmp_storage_dir / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("hi")

        assert local_backend.exists(key, None, None)
        local_backend.delete(key, None, None)
        assert not path.exists()

    def test_stream_chunks_avoids_full_read(self, local_backend: LocalStorageBackend, tmp_storage_dir: Path) -> None:
        """stream_chunks yields chunks without loading whole file into memory."""
        key = "demo/driver_docs/document/1/big.bin"
        path = tmp_storage_dir / key
        path.parent.mkdir(parents=True, exist_ok=True)
        content = b"x" * (1024 * 100)
        path.write_bytes(content)
        chunks = list(local_backend.stream_chunks(key, None, None, chunk_size=1024))
        assert b"".join(chunks) == content
        assert len(chunks) > 1


class TestGetStorage:
    def test_local_by_default(self) -> None:
        import app.core.storage as storage_mod
        orig_engine = storage_mod._engine
        try:
            storage_mod._engine = None
            with patch("app.core.storage.settings") as mock:
                mock.storage_provider = "local"
                mock.local_storage_dir = None
                mock.company_docs_dir = None
                backend = get_storage()
                assert isinstance(backend, LocalStorageBackend)
        finally:
            storage_mod._engine = orig_engine

    def test_s3_when_configured(self) -> None:
        try:
            import boto3  # noqa: F401
        except ImportError:
            pytest.skip("boto3 not installed")
        import app.core.storage as storage_mod
        orig_engine = storage_mod._engine
        try:
            storage_mod._engine = None
            with patch("app.core.storage.settings") as mock:
                mock.storage_provider = "s3"
                mock.aws_region = "us-east-1"
                mock.s3_bucket = "test-bucket"
                mock.s3_prefix = ""
                with patch("boto3.client") as mock_client:
                    mock_client.return_value = MagicMock()
                    backend = get_storage()
                    assert isinstance(backend, S3StorageBackend)
        finally:
            storage_mod._engine = orig_engine
