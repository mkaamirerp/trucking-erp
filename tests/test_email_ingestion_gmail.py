"""Gmail delta ingestion (History API): tenant-scoped, idempotent upsert."""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import delete, select

from app.deps.tenant_db import open_tenant_session_by_id
from app.models.email_attachment import EmailMessageAttachment
from app.models.email_ingestion import EmailMessage, EmailThread
from app.models.tenant_email_account import TenantEmailAccount
from app.services import email_ingestion_gmail as ingest
from app.utils.encryption import encrypt_secret

REQUIRES_DB = not os.environ.get("DATABASE_URL")


@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
@pytest.mark.asyncio
async def test_gmail_delta_sync_upsert_is_idempotent(monkeypatch):
    suffix = uuid.uuid4().hex[:8]
    thread_ext = f"th-{suffix}"
    msg1 = f"m1-{suffix}"
    msg2 = f"m2-{suffix}"

    hist_calls = [0]

    async def fake_refresh_access_token(refresh_token: str) -> dict:
        return {"access_token": "fake-access"}

    async def fake_http_get(access_token: str, path: str, params=None):
        if path != "/history":
            raise AssertionError(f"unexpected http path {path}")
        hist_calls[0] += 1

        class Resp:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                if hist_calls[0] == 1:
                    return {
                        "history": [
                            {
                                "id": "h1",
                                "messagesAdded": [{"message": {"id": msg1, "threadId": thread_ext}}],
                            }
                        ],
                        "historyId": "200",
                    }
                return {"history": [], "historyId": "200"}

        return Resp()

    async def fake_gmail_get_json(access_token: str, path: str, params=None):
        if path == "/profile":
            return {"emailAddress": "ops@example.com", "historyId": "200"}
        if path == f"/threads/{thread_ext}":
            return {
                "id": thread_ext,
                "snippet": "thread snippet",
                "messages": [
                    {
                        "id": msg1,
                        "threadId": thread_ext,
                        "internalDate": "1711300000000",
                        "labelIds": ["INBOX", "UNREAD"],
                        "snippet": "first",
                        "payload": {
                            "headers": [
                                {"name": "From", "value": "broker@example.com"},
                                {"name": "To", "value": "ops@example.com"},
                                {"name": "Subject", "value": "Rate confirmation"},
                                {"name": "Date", "value": "Mon, 24 Mar 2026 10:00:00 +0000"},
                            ],
                            "mimeType": "multipart/mixed",
                            "body": {},
                            "parts": [
                                {
                                    "mimeType": "text/plain",
                                    "filename": "",
                                    "body": {"data": "SGVsbG8="},
                                },
                                {
                                    "mimeType": "application/pdf",
                                    "filename": "rate-confirmation.pdf",
                                    "body": {"attachmentId": f"att-{suffix}", "size": 12345},
                                    "headers": [{"name": "Content-Disposition", "value": "attachment"}],
                                },
                            ],
                        },
                    },
                    {
                        "id": msg2,
                        "threadId": thread_ext,
                        "internalDate": "1711303600000",
                        "labelIds": ["INBOX"],
                        "snippet": "second",
                        "payload": {
                            "headers": [
                                {"name": "From", "value": "broker@example.com"},
                                {"name": "To", "value": "ops@example.com"},
                                {"name": "Subject", "value": "Rate confirmation"},
                                {"name": "Date", "value": "Mon, 24 Mar 2026 11:00:00 +0000"},
                            ],
                            "mimeType": "text/plain",
                            "body": {"data": "V29ybGQ="},
                        },
                    },
                ],
            }
        raise AssertionError(f"unexpected path {path} params={params}")

    async def noop_routing(*_a, **_k):
        return None

    monkeypatch.setattr(ingest, "refresh_access_token", fake_refresh_access_token)
    monkeypatch.setattr(ingest, "_gmail_http_get", fake_http_get)
    monkeypatch.setattr(ingest, "_gmail_get_json", fake_gmail_get_json)
    monkeypatch.setattr(ingest, "apply_intake_routing_for_gmail_thread", noop_routing)

    async for tenant_db in open_tenant_session_by_id(53):
        await tenant_db.execute(
            delete(EmailMessageAttachment).where(
                EmailMessageAttachment.tenant_id == 53,
                EmailMessageAttachment.external_attachment_id == f"att-{suffix}",
            )
        )
        await tenant_db.execute(
            delete(EmailMessage).where(
                EmailMessage.tenant_id == 53,
                EmailMessage.external_thread_id == thread_ext,
            )
        )
        await tenant_db.execute(
            delete(EmailThread).where(
                EmailThread.tenant_id == 53,
                EmailThread.external_thread_id == thread_ext,
            )
        )
        acc = await tenant_db.scalar(
            select(TenantEmailAccount).where(
                TenantEmailAccount.tenant_id == 53,
                TenantEmailAccount.provider == "gmail",
            )
        )
        if not acc:
            acc = TenantEmailAccount(
                tenant_id=53,
                provider="gmail",
                email_address="ops@example.com",
                status="CONNECTED",
                access_token_encrypted=encrypt_secret("a"),
                refresh_token_encrypted=encrypt_secret("r"),
                is_primary=True,
                gmail_history_id="99",
            )
            tenant_db.add(acc)
        else:
            acc.refresh_token_encrypted = encrypt_secret("r")
            acc.gmail_history_id = "99"
        await tenant_db.commit()

        first = await ingest.sync_gmail_inbox_for_tenant(tenant_db, tenant_id=53, max_threads=10)
        second = await ingest.sync_gmail_inbox_for_tenant(tenant_db, tenant_id=53, max_threads=10)
        assert first.threads_scanned == 1
        assert first.history_pages >= 1
        assert first.attachments_upserted >= 1
        assert second.threads_scanned == 0
        assert second.attachments_upserted == 0

        thread_count = await tenant_db.scalar(
            select(EmailThread).where(
                EmailThread.tenant_id == 53,
                EmailThread.provider == "gmail",
                EmailThread.external_thread_id == thread_ext,
            )
        )
        assert thread_count is not None

        msg_rows = (
            (
                await tenant_db.execute(
                    select(EmailMessage).where(
                        EmailMessage.tenant_id == 53,
                        EmailMessage.provider == "gmail",
                        EmailMessage.external_thread_id == thread_ext,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(msg_rows) == 2
        att_rows = (
            (
                await tenant_db.execute(
                    select(EmailMessageAttachment).where(
                        EmailMessageAttachment.tenant_id == 53,
                        EmailMessageAttachment.provider == "gmail",
                        EmailMessageAttachment.external_attachment_id == f"att-{suffix}",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(att_rows) == 1
        assert att_rows[0].filename == "rate-confirmation.pdf"
        assert att_rows[0].mime_type == "application/pdf"
        assert att_rows[0].download_status == "metadata_only"
        break


@pytest.mark.asyncio
async def test_decode_pubsub_gmail_notification():
    import base64
    import json

    inner = {"emailAddress": "user@gmail.com", "historyId": 123456}
    raw = base64.urlsafe_b64encode(json.dumps(inner).encode()).decode().rstrip("=")
    body = {"message": {"data": raw}}
    email, hid = ingest.decode_pubsub_gmail_notification(body)
    assert email == "user@gmail.com"
    assert hid == "123456"
