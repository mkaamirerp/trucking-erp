"""Thin re-exports for email intake routing.

CRITICAL (Cursor / maintainers):
- Do not add business logic, DB calls, parsing, or policy here.
- All intake policy lives in ``app.services.email_engine.intake_service`` (and its helpers).
- This module exists only to preserve a stable import path for callers.
"""

from __future__ import annotations

from app.services.email_engine.intake_service import (
    apply_email_pdf_intake,
    apply_review_only_mailbox_intake as apply_intake_routing_for_review_only_thread,
)

apply_intake_routing_for_email_thread = apply_email_pdf_intake


async def apply_intake_routing_for_other_mailbox_thread(db, tenant_id: int, thread_id: int) -> None:
    await apply_intake_routing_for_review_only_thread(db, tenant_id, thread_id)
