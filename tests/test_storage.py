"""Tests for storage abstraction: key generation, local backend, factory selection."""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import UploadFile

from fastapi import HTTPException

from app.core.storage import (
    StorageKeyError,
    build_storage_key,
    get_storage,
    LocalStorageBackend,
    S3StorageBackend,
    StoredFile,
    purge_applicant_dl_application,
    purge_fuel_bvd_import_files,
    purge_fuel_bvd_stage_files,
    purge_fuel_nationwide_import_files,
    purge_fuel_nationwide_stage_files,
    serve_file,
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


def _local_backend(tmp_path: Path, *, company_docs_dir: str | None = None) -> LocalStorageBackend:
    patcher = patch("app.core.storage.settings")
    mock_settings = patcher.start()
    mock_settings.local_storage_dir = str(tmp_path / "storage")
    mock_settings.company_docs_dir = company_docs_dir
    mock_settings.storage_provider = "local"
    backend = LocalStorageBackend()
    backend._test_patcher = patcher  # type: ignore[attr-defined]
    return backend


def _stop_backend(backend: LocalStorageBackend) -> None:
    patcher = getattr(backend, "_test_patcher", None)
    if patcher is not None:
        patcher.stop()


class TestLocalPathTraversal:
    """Local reads stay inside the storage root or the external company-docs directory."""

    def test_traversal_and_absolute_paths_do_not_escape(self, tmp_path: Path) -> None:
        storage = tmp_path / "storage"
        storage.mkdir()
        secret = tmp_path / "secret.txt"
        secret.write_bytes(b"TOP-SECRET")
        owned = storage / "pytest" / "applicant_dl" / "application" / "7" / "ok.jpg"
        owned.parent.mkdir(parents=True)
        owned.write_bytes(b"owned-bytes")
        backend = _local_backend(tmp_path)
        try:
            assert backend.read_bytes(
                "pytest/applicant_dl/application/7/ok.jpg", "applicant_dl", "pytest"
            ) == b"owned-bytes"
            for bad in (
                "../secret.txt",
                "pytest/../../secret.txt",
                "pytest/applicant_dl/application/7/../../../../secret.txt",
                str(secret),
                "/etc/passwd",
                "..",
                "pytest/../secret.txt",
            ):
                with pytest.raises(StorageKeyError):
                    backend.read_bytes(bad, "applicant_dl", "pytest")
                assert backend.exists(bad, "applicant_dl", "pytest") is False
            assert secret.read_bytes() == b"TOP-SECRET"
        finally:
            _stop_backend(backend)

    def test_symlink_outside_root_is_refused(self, tmp_path: Path) -> None:
        storage = tmp_path / "storage"
        outside = tmp_path / "outside.txt"
        outside.write_bytes(b"LINKED-SECRET")
        link_dir = storage / "pytest" / "applicant_dl" / "application" / "7"
        link_dir.mkdir(parents=True)
        link = link_dir / "link.jpg"
        link.symlink_to(outside)
        backend = _local_backend(tmp_path)
        try:
            with pytest.raises(StorageKeyError):
                backend.read_bytes(
                    "pytest/applicant_dl/application/7/link.jpg", "applicant_dl", "pytest"
                )
            assert outside.read_bytes() == b"LINKED-SECRET"
        finally:
            _stop_backend(backend)

    def test_legacy_flat_filename_and_external_company_docs(self, tmp_path: Path) -> None:
        storage = tmp_path / "storage"
        external = tmp_path / "external_company_docs"
        external.mkdir()
        (external / "legacy-w9.pdf").write_bytes(b"w9-bytes")
        backend = _local_backend(tmp_path, company_docs_dir=str(external))
        try:
            assert backend.read_bytes("legacy-w9.pdf", module="company_docs", tenant_slug="pytest") == b"w9-bytes"
            legacy_dl = storage / "driver_docs" / "applicant_dl" / "old-license.jpg"
            legacy_dl.parent.mkdir(parents=True)
            legacy_dl.write_bytes(b"legacy-dl")
            assert backend.read_bytes("old-license.jpg", module="applicant_dl", tenant_slug="pytest") == b"legacy-dl"
            full = storage / "pytest" / "company_docs" / "company" / "3" / "uuid.pdf"
            full.parent.mkdir(parents=True)
            full.write_bytes(b"full-company")
            assert (
                backend.read_bytes(
                    "pytest/company_docs/company/3/uuid.pdf", module="company_docs", tenant_slug="pytest"
                )
                == b"full-company"
            )
            secret = tmp_path / "secret.txt"
            secret.write_bytes(b"NO")
            with pytest.raises(StorageKeyError):
                backend.read_bytes("../secret.txt", module="company_docs", tenant_slug="pytest")
            with pytest.raises(StorageKeyError):
                backend.read_bytes(str(secret), module="company_docs", tenant_slug="pytest")
        finally:
            _stop_backend(backend)

    def test_serve_file_traversal_is_404(self, tmp_path: Path) -> None:
        import app.core.storage as storage_mod

        secret = tmp_path / "secret.txt"
        secret.write_bytes(b"TOP-SECRET")
        backend = _local_backend(tmp_path)
        orig = storage_mod._engine
        storage_mod._engine = backend
        try:
            with pytest.raises(HTTPException) as exc:
                serve_file("../secret.txt", "applicant_dl", "pytest")
            assert exc.value.status_code == 404
            with pytest.raises(HTTPException) as exc_abs:
                serve_file(str(secret), "driver_docs", "pytest")
            assert exc_abs.value.status_code == 404
        finally:
            storage_mod._engine = orig
            _stop_backend(backend)


class TestS3KeyAuthorization:
    """S3 keeps tenant/UUID keys. Traversal never becomes a GetObject."""

    def _backend(self, prefix: str = "") -> S3StorageBackend:
        backend = S3StorageBackend.__new__(S3StorageBackend)
        backend._prefix = prefix
        backend._bucket = "test-bucket"
        backend._client = MagicMock()
        return backend

    def test_full_key_preserves_tenant_layout_and_legacy_prefix(self) -> None:
        backend = self._backend()
        owned = "pytest/applicant_dl/application/12/aabbccddeeff00112233445566778899.jpg"
        assert backend._full_key(owned, "applicant_dl", "pytest") == owned
        assert backend._full_key("old.pdf", "applicant_docs", "pytest") == "pytest/applicant_docs/legacy/0/old.pdf"
        prefixed = self._backend("root")
        assert prefixed._full_key(owned, "applicant_dl", "pytest") == f"root/{owned}"

    def test_traversal_does_not_call_s3(self) -> None:
        backend = self._backend()
        for bad in ("../secret.txt", "/etc/passwd", "pytest/../../other/secret.txt", ".."):
            with pytest.raises(StorageKeyError):
                backend.read_bytes(bad, "applicant_dl", "pytest")
            assert backend.exists(bad, "applicant_dl", "pytest") is False
        backend._client.get_object.assert_not_called()
        backend._client.head_object.assert_not_called()

    def test_serve_file_streams_safe_key_and_404s_traversal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.core.storage as storage_mod

        backend = MagicMock()
        backend.exists.return_value = True
        backend.stream_chunks.return_value = iter([b"owned-bytes"])
        monkeypatch.setattr(storage_mod, "get_storage", lambda: backend)
        response = serve_file(
            "pytest/applicant_docs/application/4/abc.pdf",
            "applicant_docs",
            "pytest",
        )
        assert response.status_code == 200
        backend.exists.assert_called_once()
        backend.stream_chunks.assert_called_once()
        backend.exists.reset_mock()
        backend.stream_chunks.reset_mock()
        with pytest.raises(HTTPException) as exc:
            serve_file("../../etc/passwd", "applicant_docs", "pytest")
        assert exc.value.status_code == 404
        backend.exists.assert_not_called()
        backend.stream_chunks.assert_not_called()

    def test_object_key_rejects_trailing_slash_and_purge_prefixes_keep_it(self) -> None:
        backend = self._backend("root")
        directory = "tenant-a/applicant_dl/application/12/"
        with pytest.raises(StorageKeyError):
            backend._full_key(directory, "applicant_dl", "tenant-a")
        assert (
            backend._full_key(f"{directory}__purge__", "applicant_dl", "tenant-a")
            == f"root/{directory}__purge__"
        )

        import app.core.storage as storage_mod

        listed = self._backend()
        listed._client.list_objects_v2.return_value = {"Contents": [], "IsTruncated": False}
        orig = storage_mod._engine
        storage_mod._engine = listed
        cases = (
            (purge_applicant_dl_application, ("tenant-a", 12), "tenant-a/applicant_dl/application/12/"),
            (
                purge_fuel_nationwide_stage_files,
                ("tenant-a", "stage-1"),
                "tenant-a/fuel_nationwide_stage/stage/stage-1/",
            ),
            (
                purge_fuel_nationwide_import_files,
                ("tenant-a", "import-1"),
                "tenant-a/fuel_nationwide/import/import-1/",
            ),
            (
                purge_fuel_bvd_stage_files,
                ("tenant-a", "stage-1"),
                "tenant-a/fuel_bvd_stage/stage/stage-1/",
            ),
            (
                purge_fuel_bvd_import_files,
                ("tenant-a", "import-1"),
                "tenant-a/fuel_bvd/import/import-1/",
            ),
        )
        try:
            for fn, args, prefix in cases:
                listed._client.list_objects_v2.reset_mock()
                with pytest.raises(StorageKeyError):
                    listed._full_key(prefix, "unused", "tenant-a")
                assert fn(*args) == 0
                assert listed._client.list_objects_v2.call_args.kwargs["Prefix"] == prefix
        finally:
            storage_mod._engine = orig
