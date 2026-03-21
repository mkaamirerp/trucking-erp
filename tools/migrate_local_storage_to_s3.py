#!/usr/bin/env python3
"""
One-time migration: backfill locally stored tenant files into S3.

Reads file references from the DB (source of truth), resolves local paths
from existing conventions, uploads to configured S3 bucket using the same
storage_key. Idempotent: skips if already present in S3; does not delete local files.

Run from repo root with app env loaded (e.g. .env or /run/secrets/truckerp.env):

  python tools/migrate_local_storage_to_s3.py inventory   # List all DB-tracked files
  python tools/migrate_local_storage_to_s3.py migrate     # Upload local → S3 (skip if exists)
  python tools/migrate_local_storage_to_s3.py verify      # Check S3 has all expected objects

Requires:
  - DATABASE_URL (platform DB)
  - POSTGRES_ADMIN_URL or DATABASE_URL (for tenant DBs)
  - LOCAL_STORAGE_DIR or default repo storage/
  - S3_BUCKET, AWS_REGION (S3 target)
"""
from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Run from repo root so app is importable
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@dataclass
class FileRecord:
    storage_key: str
    module: str
    tenant_slug: str | None
    source: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class MigrationResult:
    total: int = 0
    skipped_exists: int = 0
    uploaded: int = 0
    missing_local: int = 0
    failed: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)


def _full_s3_key(storage_key: str, module: str, tenant_slug: str | None, prefix: str) -> str:
    """Replicate S3StorageBackend._full_key logic for script use."""
    from app.core.storage import _resolve_legacy_key
    if "/" in storage_key:
        k = storage_key
    else:
        k = _resolve_legacy_key(storage_key, module or "driver_docs", tenant_slug)
    if prefix:
        return f"{prefix.rstrip('/')}/{k}".lstrip("/")
    return k


def _tenant_slug_from_storage_key(storage_key: str) -> str | None:
    """Extract tenant slug from storage_key if it has path segments (e.g. demo/company_docs/...)."""
    if "/" in storage_key:
        return storage_key.split("/")[0]
    return None


async def _collect_platform_records(session: Any) -> list[FileRecord]:
    """Collect storage_key records from platform DB."""
    from sqlalchemy import select
    from app.models.platform import PlatformTenant, PlatformCompanyProfile, PlatformOnboardingPayload

    records: list[FileRecord] = []

    # platform_company_profiles.w9_storage_key
    result = await session.execute(
        select(PlatformCompanyProfile, PlatformTenant.slug).join(
            PlatformTenant, PlatformCompanyProfile.tenant_id == PlatformTenant.id
        ).where(PlatformCompanyProfile.w9_storage_key.isnot(None))
    )
    for row in result:
        profile, slug = row[0], row[1]
        key = profile.w9_storage_key.strip()
        if key:
            records.append(FileRecord(
                storage_key=key,
                module="company_docs",
                tenant_slug=slug,
                source="platform_company_profiles.w9_storage_key",
                extra={"profile_id": profile.id},
            ))

    # platform_onboarding_payloads.payload_json.w9_storage_key (only where tenant_id set)
    result = await session.execute(
        select(PlatformOnboardingPayload, PlatformTenant.slug).outerjoin(
            PlatformTenant, PlatformOnboardingPayload.tenant_id == PlatformTenant.id
        ).where(
            PlatformOnboardingPayload.tenant_id.isnot(None),
            PlatformOnboardingPayload.payload_json.isnot(None),
        )
    )
    for row in result:
        payload, slug = row[0], row[1]
        pj = payload.payload_json or {}
        key = (pj.get("w9_storage_key") or "").strip()
        if key and slug:
            records.append(FileRecord(
                storage_key=key,
                module="company_docs",
                tenant_slug=slug,
                source="platform_onboarding_payloads.payload_json.w9_storage_key",
                extra={"payload_id": payload.id},
            ))

    return records


async def _collect_tenant_records(
    session: Any,
    tenant_slug: str,
) -> list[FileRecord]:
    """Collect storage_key records from a tenant DB."""
    from sqlalchemy import select, text
    from app.models.driver_document_file import DriverDocumentFile
    from app.models.payee import PayDocument
    from app.models.person_application import PersonApplication

    records: list[FileRecord] = []

    # driver_document_files.storage_key
    result = await session.execute(
        select(DriverDocumentFile.storage_key).where(DriverDocumentFile.is_active)
    )
    for (key,) in result:
        if key and key.strip():
            records.append(FileRecord(
                storage_key=key.strip(),
                module="driver_docs",
                tenant_slug=tenant_slug,
                source="driver_document_files.storage_key",
            ))

    # pay_documents.file_storage_key
    result = await session.execute(select(PayDocument.file_storage_key))
    for (key,) in result:
        if key and key.strip():
            records.append(FileRecord(
                storage_key=key.strip(),
                module="pay_documents",
                tenant_slug=tenant_slug,
                source="pay_documents.file_storage_key",
            ))

    # person_applications.intake_payload: files (CDL) and documents
    result = await session.execute(
        select(PersonApplication.id, PersonApplication.intake_payload).where(
            PersonApplication.intake_payload.isnot(None)
        )
    )
    for app_id, payload in result:
        if not isinstance(payload, dict):
            continue
        files = payload.get("files") or {}
        for doc_type, meta in files.items():
            if not isinstance(meta, dict):
                continue
            for k in ("storage_key", "file_id", "enh_file_id"):
                val = meta.get(k)
                if val and isinstance(val, str) and val.strip():
                    sk = val.strip()
                    records.append(FileRecord(
                        storage_key=sk,
                        module="applicant_dl",
                        tenant_slug=tenant_slug,
                        source=f"person_applications.intake_payload.files.{doc_type}",
                        extra={"application_id": app_id},
                    ))
                    break  # one file per doc_type
        documents = payload.get("documents") or {}
        for doc_type, meta in documents.items():
            if not isinstance(meta, dict):
                continue
            for k in ("storage_key", "file_id"):
                val = meta.get(k)
                if val and isinstance(val, str) and val.strip():
                    sk = val.strip()
                    records.append(FileRecord(
                        storage_key=sk,
                        module="applicant_docs",
                        tenant_slug=tenant_slug,
                        source=f"person_applications.intake_payload.documents.{doc_type}",
                        extra={"application_id": app_id},
                    ))
                    break

    return records


async def collect_all_records(platform_session: Any, get_tenant_session: Any) -> list[FileRecord]:
    """Collect all file records from platform + all tenant DBs."""
    from sqlalchemy import select
    from app.models.platform import PlatformTenant

    all_records: list[FileRecord] = []

    # Platform records
    platform_records = await _collect_platform_records(platform_session)
    all_records.extend(platform_records)

    # Tenant records: list active tenants with db_name
    result = await platform_session.execute(
        select(PlatformTenant).where(
            PlatformTenant.db_name.isnot(None),
            PlatformTenant.db_name != "",
        )
    )
    tenants = list(result.scalars().all())

    for tenant in tenants:
        if not tenant.db_name or not tenant.slug:
            continue
        async with get_tenant_session(tenant) as tenant_session:
            tenant_records = await _collect_tenant_records(tenant_session, tenant.slug)
            all_records.extend(tenant_records)

    # Deduplicate by (storage_key, module) - same file can appear in multiple sources
    seen: set[tuple[str, str]] = set()
    unique: list[FileRecord] = []
    for r in all_records:
        key = (r.storage_key, r.module)
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)

    return unique


def resolve_local_path(storage_key: str, module: str, tenant_slug: str | None) -> Path:
    """Resolve storage_key to local filesystem path using LocalStorageBackend conventions."""
    from app.core.storage import LocalStorageBackend
    from app.core.config import settings

    backend = LocalStorageBackend()
    return backend._key_to_path(storage_key, module, tenant_slug)


def s3_exists(bucket: str, key: str, region: str) -> bool:
    """Check if object exists in S3."""
    import boto3
    client = boto3.client("s3", region_name=region)
    try:
        client.head_object(Bucket=bucket, Key=key)
        return True
    except Exception:
        return False


def s3_upload(bucket: str, key: str, body: bytes, region: str, content_type: str | None = None) -> None:
    """Upload bytes to S3."""
    import boto3
    client = boto3.client("s3", region_name=region)
    extra = {}
    if content_type:
        extra["ContentType"] = content_type
    client.put_object(Bucket=bucket, Key=key, Body=body, **extra)


def _content_type_from_suffix(storage_key: str) -> str:
    suf = Path(storage_key).suffix.lower()
    if suf in (".jpg", ".jpeg"):
        return "image/jpeg"
    if suf == ".png":
        return "image/png"
    if suf == ".pdf":
        return "application/pdf"
    return "application/octet-stream"


async def run_inventory(records: list[FileRecord]) -> None:
    """Print inventory of all DB-tracked files."""
    print("=" * 70)
    print("STORAGE MIGRATION INVENTORY")
    print("=" * 70)
    print(f"{'storage_key':<55} {'module':<18} {'source'}")
    print("-" * 70)
    for r in records:
        src_short = (r.source[:40] + "…") if len(r.source) > 40 else r.source
        print(f"{r.storage_key[:54]:<55} {r.module:<18} {src_short}")
    print("-" * 70)
    print(f"Total unique files: {len(records)}")


async def run_migrate(
    records: list[FileRecord],
    bucket: str,
    region: str,
    prefix: str,
) -> MigrationResult:
    """Upload local files to S3. Skip if exists; do not delete local."""
    result = MigrationResult()
    result.total = len(records)

    for r in records:
        tenant_slug = r.tenant_slug or _tenant_slug_from_storage_key(r.storage_key)
        full_key = _full_s3_key(r.storage_key, r.module, tenant_slug, prefix)

        if s3_exists(bucket, full_key, region):
            result.skipped_exists += 1
            continue

        local_path = resolve_local_path(r.storage_key, r.module, tenant_slug)
        if not local_path.is_file():
            result.missing_local += 1
            result.errors.append((r.storage_key, "Local file not found"))
            continue

        try:
            body = local_path.read_bytes()
            content_type = _content_type_from_suffix(r.storage_key)
            s3_upload(bucket, full_key, body, region, content_type)
            result.uploaded += 1
        except Exception as e:
            result.failed += 1
            result.errors.append((r.storage_key, str(e)))

    return result


async def run_verify(
    records: list[FileRecord],
    bucket: str,
    region: str,
    prefix: str,
) -> MigrationResult:
    """Verify all records exist in S3."""
    result = MigrationResult()
    result.total = len(records)

    for r in records:
        tenant_slug = r.tenant_slug or _tenant_slug_from_storage_key(r.storage_key)
        full_key = _full_s3_key(r.storage_key, r.module, tenant_slug, prefix)

        if s3_exists(bucket, full_key, region):
            result.uploaded += 1  # reuse as "verified"
        else:
            result.failed += 1
            result.errors.append((r.storage_key, "Not found in S3"))

    return result


def print_report(mode: str, result: MigrationResult) -> None:
    """Print migration summary report."""
    print("\n" + "=" * 70)
    print(f"STORAGE MIGRATION {mode.upper()} REPORT")
    print("=" * 70)
    print(f"  Total records:     {result.total}")
    if mode == "migrate":
        print(f"  Skipped (exists):   {result.skipped_exists}")
        print(f"  Uploaded:          {result.uploaded}")
        print(f"  Missing local:     {result.missing_local}")
    elif mode == "verify":
        print(f"  In S3 (ok):        {result.uploaded}")
    print(f"  Failed:            {result.failed}")
    if result.errors:
        print("\n  Errors:")
        for sk, err in result.errors[:20]:
            print(f"    - {sk[:50]}... : {err[:60]}")
        if len(result.errors) > 20:
            print(f"    ... and {len(result.errors) - 20} more")
    print("=" * 70)


async def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in ("inventory", "migrate", "verify"):
        print(
            "Usage: python tools/migrate_local_storage_to_s3.py inventory|migrate|verify",
            file=sys.stderr,
        )
        sys.exit(2)

    mode = sys.argv[1].lower()

    from app.core.config import settings
    from app.core.database import AsyncSessionLocal
    from app.core.db_url import to_async_pg_url
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from app.models.platform import PlatformTenant
    from sqlalchemy import select

    template = getattr(settings, "postgres_admin_url", None) or settings.database_url
    if not template:
        print("Error: DATABASE_URL or POSTGRES_ADMIN_URL required", file=sys.stderr)
        sys.exit(1)

    def _swap_db(url: str, db_name: str) -> str:
        base, _sep, _ = url.rpartition("/")
        return f"{base}/{db_name}" if base else url

    @asynccontextmanager
    async def get_tenant_session(tenant: PlatformTenant):
        tenant_url = _swap_db(to_async_pg_url(template), tenant.db_name)
        engine = create_async_engine(tenant_url, pool_pre_ping=True)
        try:
            maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
            async with maker() as session:
                yield session
        finally:
            await engine.dispose()

    async with AsyncSessionLocal() as platform_session:
        records = await collect_all_records(platform_session, get_tenant_session)

    if mode == "inventory":
        await run_inventory(records)
        return

    bucket = settings.s3_bucket
    region = settings.aws_region
    prefix = (settings.s3_prefix or "").rstrip("/")

    if mode == "migrate":
        result = await run_migrate(records, bucket, region, prefix)
    else:
        result = await run_verify(records, bucket, region, prefix)

    print_report(mode, result)
    if result.failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
