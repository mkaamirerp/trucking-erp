"""Safety tests for purge_applicant_dl_application (draft-reset file delete)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import app.core.config as app_config
import app.core.storage as storage_mod
from app.core.storage import S3StorageBackend, purge_applicant_dl_application


@pytest.fixture(autouse=True)
def reset_storage_engine():
    yield
    storage_mod._engine = None


def _write_rel(root: Path, rel: str, data: bytes = b"keep") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _configure_local(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    storage_mod._engine = None
    monkeypatch.setattr(app_config.settings, "storage_provider", "local", raising=False)
    monkeypatch.setattr(app_config.settings, "local_storage_dir", str(tmp_path), raising=False)


def test_purge_deletes_only_exact_application_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_local(monkeypatch, tmp_path)

    _write_rel(tmp_path, "tenant-a/applicant_dl/application/12/original.jpg", b"orig")
    _write_rel(tmp_path, "tenant-a/applicant_dl/application/12/processed.jpg", b"proc")
    keep_123 = _write_rel(tmp_path, "tenant-a/applicant_dl/application/123/keep.jpg")
    keep_13 = _write_rel(tmp_path, "tenant-a/applicant_dl/application/13/keep.jpg")
    keep_b12 = _write_rel(tmp_path, "tenant-b/applicant_dl/application/12/keep.jpg")

    deleted = purge_applicant_dl_application("tenant-a", 12)

    assert deleted == 2
    assert not (tmp_path / "tenant-a/applicant_dl/application/12").exists()
    assert keep_123.is_file()
    assert keep_123.read_bytes() == b"keep"
    assert keep_13.is_file()
    assert keep_b12.is_file()


def test_purge_missing_application_directory_is_idempotent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_local(monkeypatch, tmp_path)

    neighbor = _write_rel(tmp_path, "tenant-a/applicant_dl/application/13/keep.jpg")

    deleted = purge_applicant_dl_application("tenant-a", 12)

    assert deleted == 0
    assert neighbor.is_file()
    assert neighbor.read_bytes() == b"keep"


def test_s3_purge_uses_trailing_slash_prefix_and_deletes_only_listed_keys() -> None:
    try:
        import boto3  # noqa: F401
    except ImportError:
        pytest.skip("boto3 not installed")

    storage_mod._engine = None
    mock_client = MagicMock()
    listed = [
        {"Key": "tenant-a/applicant_dl/application/12/original.jpg"},
        {"Key": "tenant-a/applicant_dl/application/12/processed.jpg"},
    ]
    mock_client.list_objects_v2.return_value = {"Contents": listed, "IsTruncated": False}

    with patch("app.core.storage.settings") as mock_settings:
        mock_settings.storage_provider = "s3"
        mock_settings.aws_region = "us-east-1"
        mock_settings.s3_bucket = "test-bucket"
        mock_settings.s3_prefix = ""
        with patch("boto3.client", return_value=mock_client):
            backend = S3StorageBackend()
            storage_mod._engine = backend
            deleted = purge_applicant_dl_application("tenant-a", 12)

    assert deleted == 2
    mock_client.list_objects_v2.assert_called_once()
    list_kwargs = mock_client.list_objects_v2.call_args.kwargs
    assert list_kwargs["Bucket"] == "test-bucket"
    assert list_kwargs["Prefix"] == "tenant-a/applicant_dl/application/12/"
    assert list_kwargs["Prefix"].endswith("/")
    assert not list_kwargs["Prefix"].endswith("12")
    mock_client.delete_objects.assert_called_once_with(
        Bucket="test-bucket",
        Delete={"Objects": [{"Key": item["Key"]} for item in listed]},
    )
    deleted_keys = [o["Key"] for o in mock_client.delete_objects.call_args.kwargs["Delete"]["Objects"]]
    assert all(k.startswith("tenant-a/applicant_dl/application/12/") for k in deleted_keys)
    assert not any("application/123/" in k for k in deleted_keys)


def test_s3_purge_honors_configured_prefix_and_paginates_past_1000() -> None:
    try:
        import boto3  # noqa: F401
    except ImportError:
        pytest.skip("boto3 not installed")

    storage_mod._engine = None
    mock_client = MagicMock()
    page_prefix = "prod/tenant-a/applicant_dl/application/12/"
    page1_keys = [{"Key": f"{page_prefix}obj-{i:04d}.jpg"} for i in range(1000)]
    page2_keys = [{"Key": f"{page_prefix}obj-1000.jpg"}]

    def list_objects_v2(**kwargs):
        assert kwargs["Prefix"] == page_prefix
        token = kwargs.get("ContinuationToken")
        if token is None:
            return {
                "Contents": page1_keys,
                "IsTruncated": True,
                "NextContinuationToken": "page-2",
            }
        assert token == "page-2"
        return {"Contents": page2_keys, "IsTruncated": False}

    mock_client.list_objects_v2.side_effect = list_objects_v2

    with patch("app.core.storage.settings") as mock_settings:
        mock_settings.storage_provider = "s3"
        mock_settings.aws_region = "us-east-1"
        mock_settings.s3_bucket = "test-bucket"
        mock_settings.s3_prefix = "prod"
        with patch("boto3.client", return_value=mock_client):
            backend = S3StorageBackend()
            storage_mod._engine = backend
            deleted = purge_applicant_dl_application("tenant-a", 12)

    assert deleted == 1001
    assert mock_client.list_objects_v2.call_count == 2
    assert mock_client.delete_objects.call_count == 2
    first_delete = mock_client.delete_objects.call_args_list[0].kwargs["Delete"]["Objects"]
    second_delete = mock_client.delete_objects.call_args_list[1].kwargs["Delete"]["Objects"]
    assert len(first_delete) == 1000
    assert len(second_delete) == 1
    assert all(item["Key"].startswith(page_prefix) for item in first_delete + second_delete)
