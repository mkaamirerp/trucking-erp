"""Load Lab — broker contact email provenance (parse_diagnostics only).

Explains where broker_contact_email_snapshot came from: PDF text, optional email thread
surfaces on normalized_package, tenant BrokerContact / known-sender tables, global
reference, AI output, and whether post-AI guardrails changed the field.

Does not alter extracted fields or workspace hydration.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.broker import BrokerContact, BrokerKnownSender
from app.models.global_booking_broker import GlobalBookingBrokerKnownSender
from app.utils.broker_identity import normalize_domain, normalize_known_sender_email


def _empty_diagnostics() -> dict[str, Any]:
    return {
        "broker_contact_email_value": None,
        "broker_contact_email_source": "none",
        "broker_contact_email_source_detail": "no broker_contact_email_snapshot",
        "broker_contact_email_found_in_pdf_text": False,
        "broker_contact_email_found_in_email_header": False,
        "broker_contact_email_found_in_email_body": False,
        "broker_contact_email_from_tenant_contact_id": None,
        "broker_contact_email_from_global_reference": False,
        "broker_contact_email_from_ai_output": False,
        "broker_contact_email_changed_by_post_ai_repair": False,
        "broker_contact_email_possible_external_sources": _historical_source_channels(),
    }


def _historical_source_channels() -> list[str]:
    """Explains prior incidents (e.g. carrier@jbhunt.com not on PDF) — diagnostic only."""
    return [
        "1_prior_parse_response_or_stale_run_row_reuse_same_file_hash",
        "2_tenant_broker_contacts_email_column_match_without_pdf_literal",
        "3_tenant_broker_known_senders_or_domain_directory_signals",
        "4_global_booking_broker_known_sender_or_reference_tables",
        "5_openai_model_output_in_semantic_extract_json",
        "6_email_thread_headers_or_body_when_present_on_normalized_package",
    ]


def _norm_email_key(raw: str | None) -> str | None:
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s:
        return None
    try:
        return normalize_known_sender_email(s)
    except Exception:
        return s.casefold()


def _email_in_blob(email_key: str | None, blob: str | None) -> bool:
    if not email_key or not blob:
        return False
    b = blob.casefold()
    if email_key in b:
        return True
    # Loose: local@domain with different spacing
    if email_key.replace(" ", "") in b.replace(" ", ""):
        return True
    return False


def _extract_email_thread_surfaces(pkg: dict[str, Any] | None) -> tuple[str, str]:
    """
    Optional surfaces for future Gmail / email-ingestion packages.
    Returns (header_concat, body_concat) for substring checks.
    """
    if not isinstance(pkg, dict):
        return "", ""

    def _walk(o: Any, depth: int = 0) -> tuple[list[str], list[str]]:
        if depth > 8:
            return [], []
        headers: list[str] = []
        bodies: list[str] = []
        if isinstance(o, dict):
            for k, v in o.items():
                lk = str(k).casefold()
                if lk in ("headers", "raw_headers", "email_headers", "message_headers", "smtp_headers"):
                    if isinstance(v, str) and v.strip():
                        headers.append(v)
                    elif isinstance(v, list):
                        headers.extend(str(x) for x in v if isinstance(x, str) and x.strip())
                    elif isinstance(v, dict):
                        h2, b2 = _walk(v, depth + 1)
                        headers.extend(h2)
                        bodies.extend(b2)
                elif lk in ("body", "email_body", "text_body", "snippet", "plain_text", "html_body"):
                    if isinstance(v, str) and v.strip():
                        bodies.append(v)
                    elif isinstance(v, dict):
                        h2, b2 = _walk(v, depth + 1)
                        headers.extend(h2)
                        bodies.extend(b2)
                elif lk in ("thread", "source_email", "ingestion", "email", "envelope"):
                    h2, b2 = _walk(v, depth + 1)
                    headers.extend(h2)
                    bodies.extend(b2)
                else:
                    h2, b2 = _walk(v, depth + 1)
                    headers.extend(h2)
                    bodies.extend(b2)
        elif isinstance(o, list):
            for it in o:
                h2, b2 = _walk(it, depth + 1)
                headers.extend(h2)
                bodies.extend(b2)
        return headers, bodies

    hdr_parts, body_parts = _walk(pkg)
    return "\n".join(hdr_parts)[:50_000], "\n".join(body_parts)[:50_000]


def _domain_in_directory(email_key: str | None, broker_domains: list[str] | None) -> bool:
    if not email_key or "@" not in email_key:
        return False
    dom = email_key.split("@", 1)[-1].strip()
    if not dom:
        return False
    try:
        dcf = normalize_domain(dom).casefold()
    except Exception:
        dcf = dom.casefold()
    dirs = {str(x).strip().casefold() for x in (broker_domains or []) if isinstance(x, str) and x.strip()}
    return dcf in dirs


async def build_broker_contact_email_parse_diagnostics(
    db: AsyncSession,
    *,
    tenant_id: int,
    final_extracted: dict[str, Any] | None,
    ai_extracted: dict[str, Any] | None,
    email_before_post_ai_guardrails: str | None,
    raw_pdf_text: str | None,
    normalized_package: dict[str, Any] | None,
    broker_match_domains: list[str] | None,
) -> dict[str, Any]:
    out = _empty_diagnostics()
    ex = final_extracted if isinstance(final_extracted, dict) else {}
    raw_val = ex.get("broker_contact_email_snapshot")
    value = raw_val.strip() if isinstance(raw_val, str) and raw_val.strip() else None
    if not value:
        return out

    email_key = _norm_email_key(value)
    out["broker_contact_email_value"] = value

    pdf = raw_pdf_text or ""
    hdr, body = _extract_email_thread_surfaces(normalized_package if isinstance(normalized_package, dict) else None)
    in_pdf = _email_in_blob(email_key, pdf) or (value.strip().casefold() in pdf.casefold())
    in_hdr = _email_in_blob(email_key, hdr)
    in_body = _email_in_blob(email_key, body)
    out["broker_contact_email_found_in_pdf_text"] = bool(in_pdf)
    out["broker_contact_email_found_in_email_header"] = bool(in_hdr)
    out["broker_contact_email_found_in_email_body"] = bool(in_body)

    ai_ex = ai_extracted if isinstance(ai_extracted, dict) else {}
    ai_raw = ai_ex.get("broker_contact_email_snapshot")
    ai_val = ai_raw.strip() if isinstance(ai_raw, str) and ai_raw.strip() else None
    ai_key = _norm_email_key(ai_val) if ai_val else None
    out["broker_contact_email_from_ai_output"] = bool(email_key and ai_key and email_key == ai_key and bool(ai_val))

    pre = email_before_post_ai_guardrails.strip() if isinstance(email_before_post_ai_guardrails, str) else ""
    pre_key = _norm_email_key(pre) if pre else None
    out["broker_contact_email_changed_by_post_ai_repair"] = (pre_key or None) != (email_key or None)

    tenant_contact_id: int | None = None
    try:
        rows = (
            (
                await db.execute(
                    select(BrokerContact.id, BrokerContact.email).where(
                        BrokerContact.tenant_id == tenant_id,
                        BrokerContact.is_active.is_(True),
                        BrokerContact.email.isnot(None),
                    ).limit(800)
                )
            )
            .all()
        )
        for cid, em in rows:
            if not isinstance(em, str) or not em.strip():
                continue
            ek = _norm_email_key(em.strip())
            if ek and email_key and ek == email_key:
                tenant_contact_id = int(cid)
                break
    except Exception:
        tenant_contact_id = None
    out["broker_contact_email_from_tenant_contact_id"] = tenant_contact_id

    global_ref = False
    if email_key:
        try:
            async with AsyncSessionLocal() as pdb:
                gid = (
                    await pdb.execute(
                        select(GlobalBookingBrokerKnownSender.id).where(
                            GlobalBookingBrokerKnownSender.email_normalized == email_key
                        ).limit(1)
                    )
                ).scalar_one_or_none()
                global_ref = gid is not None
        except Exception:
            global_ref = False
    out["broker_contact_email_from_global_reference"] = global_ref

    tenant_known_sender = False
    if email_key:
        try:
            cnt = (
                await db.execute(
                    select(BrokerKnownSender.id).where(
                        BrokerKnownSender.tenant_id == tenant_id,
                        BrokerKnownSender.is_active.is_(True),
                        BrokerKnownSender.email_normalized == email_key,
                    ).limit(1)
                )
            ).scalar_one_or_none()
            tenant_known_sender = cnt is not None
        except Exception:
            tenant_known_sender = False

    domain_dir = _domain_in_directory(email_key, broker_match_domains)

    in_document_surface = bool(in_pdf or in_hdr or in_body)

    if in_document_surface:
        out["broker_contact_email_source"] = "document_extracted"
        parts = []
        if in_pdf:
            parts.append("literal_or_normalized_match_in_pdf_raw_text")
        if in_hdr:
            parts.append("match_in_normalized_package_email_header_surface")
        if in_body:
            parts.append("match_in_normalized_package_email_body_surface")
        out["broker_contact_email_source_detail"] = "; ".join(parts)
    elif tenant_contact_id is not None and not in_document_surface:
        out["broker_contact_email_source"] = "suggested_contact_directory"
        out["broker_contact_email_source_detail"] = (
            f"matches_tenant_broker_contacts.id={tenant_contact_id} but not_found_in_pdf_or_email_thread_surfaces"
        )
    elif tenant_known_sender and not in_document_surface:
        out["broker_contact_email_source"] = "suggested_contact_directory"
        out["broker_contact_email_source_detail"] = (
            "matches_tenant_broker_known_senders_not_found_in_pdf_or_email_thread_surfaces"
        )
    elif global_ref and not in_document_surface:
        out["broker_contact_email_source"] = "suggested_global_reference"
        out["broker_contact_email_source_detail"] = (
            "matches_global_booking_broker_known_sender_not_found_in_pdf_or_email_thread_surfaces"
        )
    elif domain_dir and not in_document_surface:
        out["broker_contact_email_source"] = "suggested_contact_directory"
        out["broker_contact_email_source_detail"] = (
            "email_domain_matches_broker_match_domains_without_literal_address_in_pdf_or_thread_surfaces"
        )
    elif out["broker_contact_email_from_ai_output"] and not in_document_surface:
        out["broker_contact_email_source"] = "ai_output"
        out["broker_contact_email_source_detail"] = (
            "model_emitted_this_address_no_literal_match_in_pdf_or_package_email_surfaces_and_no_directory_row_match"
        )
    else:
        out["broker_contact_email_source"] = "unknown"
        out["broker_contact_email_source_detail"] = (
            "non_empty_snapshot_without_clear_pdf_thread_directory_or_ai_alignment_classification"
        )

    return out
