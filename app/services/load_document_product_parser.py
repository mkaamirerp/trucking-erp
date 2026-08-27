"""Canonical **public** import target for product PDF → ``LoadDocumentParseResponse``.

CRITICAL (Cursor / maintainers):
- Feature code (email intake, workspace parse, jobs) MUST import
  ``parse_pdf_bytes_to_load_document_response`` from **this module** (or the orchestrator
  that forwards here).
- Do not add a parallel public parser entrypoint in `app/services/` without an explicit
  architecture decision and tests.
- Production Rate Confirmation path: ``load_document_parse_rate_con`` (acquisition + v2
  handoff + mechanical validation). Legacy diagnostics path is not used at runtime.
"""

from __future__ import annotations

from app.services.load_document_parse_rate_con import parse_pdf_bytes_to_load_document_response

__all__ = ["parse_pdf_bytes_to_load_document_response"]
