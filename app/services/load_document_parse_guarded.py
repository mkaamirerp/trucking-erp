"""Legacy guarded parser module — production entrypoint is Rate Confirmation v2.

``parse_pdf_bytes_to_load_document_response`` re-exports the clean production path
(``load_document_parse_rate_con``). Old PRODUCT_PARSE_DIAGNOSTICS prompt builders and
``apply_guarded_load_document_repairs`` wiring were removed from this runtime entrypoint.

Historical diagnostics / guardrail modules may still exist on disk for Load Lab /
migration inventory; they are not called by the New Load parse-document path.
"""

from __future__ import annotations

from app.services.load_document_parse_rate_con import parse_pdf_bytes_to_load_document_response

__all__ = ["parse_pdf_bytes_to_load_document_response"]
