"""Compatibility re-exports for email intake. Logic lives in `email_engine.intake_service` + `message_classifier`."""

from __future__ import annotations

from app.services.email_engine.intake_service import (
    apply_gmail_tql_intake_gate as apply_intake_routing_for_gmail_thread,
    apply_review_only_mailbox_intake as apply_intake_routing_for_review_only_thread,
    resolve_tql_broker_for_intake as _resolve_tql_broker,
)
from app.services.email_engine.message_classifier import (
    participants_indicate_tql,
    subject_or_snippet_indicates_tql,
    thread_indicates_tql_affinity,
)


async def apply_intake_routing_for_other_mailbox_thread(db, tenant_id: int, thread_id: int) -> None:
    await apply_intake_routing_for_review_only_thread(db, tenant_id, thread_id)
