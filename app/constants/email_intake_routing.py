"""Stable machine-oriented ``EmailThread.routing_reason`` codes for broker/email intake.

Long-term: keep a **compact primary code** on the thread; move elaboration to structured columns / review history.
Pipe-separated tails here are a temporary bridge for UI, not a growing mini-schema.

Convention:
- Primary code is the first segment (before ``:`` or ``|``).
- Optional ``key=value`` pairs after ``|`` (repeatable).
"""

from __future__ import annotations

import re

# --- Primary codes (first segment) ---

MAILBOX_INTAKE_REVIEW_ONLY = "mailbox_intake_review_only"
EMAIL_INTAKE_TOUCHPOINTS_NO_PDF_ATTACHMENT = "email_touchpoints_no_pdf_attachment"
BROKER_RESOLVE_AMBIGUOUS = "broker_resolve_ambiguous"
GLOBAL_BROKER_RESOLVE_AMBIGUOUS = "global_broker_resolve_ambiguous"
GLOBAL_BROKER_MATCH_REQUIRES_WORKSPACE = "global_broker_match_requires_workspace"
GLOBAL_BROKER_TIER_D_REQUIRES_REVIEW = "global_broker_tier_d_requires_review"
GLOBAL_BROKER_HEADER_VS_MC_DOT_DISAGREEMENT = "global_broker_header_vs_mc_dot_disagreement"
INTAKE_BROKER_CONFLICTING_SIGNALS = "intake_broker_conflicting_signals"
INTAKE_BROKER_CONFLICTING_REVIEW_DETAIL_HEADER_VS_SUPP_GLOBAL = "header_broker_vs_supplemental_global"
BROKER_INTAKE_BLOCKED = "broker_intake_blocked"
DUPLICATE_PDF_SHA256 = "duplicate_pdf_sha256"
EMAIL_INTAKE_PDF_LOW_CONFIDENCE_PRIMARY = "email_pdf_not_high_confidence"
EMAIL_INTAKE_PDF_PARSE_REVIEW_PRIMARY = "email_intake_pdf_parse_review"

# primary_code values that use the duplicate / merge operator workflow
DUPLICATE_INTAKE_REVIEW_PRIMARIES = frozenset({DUPLICATE_PDF_SHA256})

INTAKE_REVIEW_SOURCE_WRITTEN_PRIMARIES = frozenset({
    DUPLICATE_PDF_SHA256,
    BROKER_RESOLVE_AMBIGUOUS,
    GLOBAL_BROKER_RESOLVE_AMBIGUOUS,
    BROKER_INTAKE_BLOCKED,
    EMAIL_INTAKE_PDF_LOW_CONFIDENCE_PRIMARY,
    EMAIL_INTAKE_PDF_PARSE_REVIEW_PRIMARY,
})
LEGACY_EMAIL_INTAKE_AUTO_DIGITAL_PDF_RATE_CONFIRMATION = "auto_tql_digital_pdf_rate_confirmation"
AUTO_NON_INTAKE_MAIL_BACKGROUND = "auto_non_intake_mail_background"
GMAIL_MISSING_TOKEN_FOR_INTAKE_GATE = "gmail_missing_token_for_intake_gate"
MANUAL_CREATE_DRAFT_FROM_REVIEW = "manual_create_draft_from_review"
MANUAL_LINK_EXISTING_LOAD = "manual_link_existing_load"

_QR_TAG_RE = re.compile(r"\|qr_extractions=\d+$")


def format_duplicate_pdf_sha256(
    *,
    prior_load_id: int,
    content_sha256: str | None = None,
    detection_source: str | None = None,
) -> str:
    base = f"{DUPLICATE_PDF_SHA256}|prior_load_id={prior_load_id}"
    if content_sha256:
        h = str(content_sha256).strip().lower()
        if h:
            base = f"{base}|content_sha256={h}"
    if detection_source:
        ds = str(detection_source).strip()
        if ds:
            base = f"{base}|detection_source={ds}"
    return base


def format_email_intake_pdf_low_confidence(gate_detail: str) -> str:
    """PDF present but guarded parse did not yield a storable snapshot (pipe tail)."""
    g = str(gate_detail).strip().replace("|", "_").replace("\n", " ")[:512]
    return f"{EMAIL_INTAKE_PDF_LOW_CONFIDENCE_PRIMARY}|gate_detail={g}"


def format_email_intake_pdf_parse_review(*, gate_detail: str) -> str:
    """Guarded parse succeeded; review detail may include ``guarded_parse`` snapshot (no auto-load)."""
    g = str(gate_detail).strip().replace("|", "_").replace("\n", " ")[:512]
    return f"{EMAIL_INTAKE_PDF_PARSE_REVIEW_PRIMARY}|gate_detail={g}"


def format_intake_broker_conflicting_signals_routing() -> str:
    """Header/workspace broker won, but supplemental MC/DOT maps to a different global id — review."""
    return f"{INTAKE_BROKER_CONFLICTING_SIGNALS}|review_detail={INTAKE_BROKER_CONFLICTING_REVIEW_DETAIL_HEADER_VS_SUPP_GLOBAL}"


def append_qr_extractions_tag(reason: str, qr_count: int) -> str:
    """Append ``|qr_extractions=N`` when N > 0 (supplemental QR rows persisted for this thread)."""
    if qr_count <= 0:
        return reason
    base = strip_qr_extractions_tag(reason)
    return f"{base}|qr_extractions={qr_count}"


def strip_qr_extractions_tag(reason: str) -> str:
    """Remove a trailing ``|qr_extractions=N`` if present (e.g. before re-appending)."""
    return _QR_TAG_RE.sub("", reason)
