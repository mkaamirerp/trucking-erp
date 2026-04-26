"""Load Lab v2 — OpenAI semantic extraction on a persisted run (tenant DB only).

No operational load writes. Failures are recorded on the run row.
"""

from __future__ import annotations

import re
import json
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.load_lab import LoadLabExtractionRun
from app.schemas.critical_extraction_v11 import CriticalExtractionV11Root
from app.schemas.load_document_parse import (
    LoadDocumentParseResponse,
    LoadParseDocumentMeta,
)
from app.schemas.load_lab_semantic import LoadLabSemanticModelOutput, StrictExtracted
from app.schemas.load_document_parse import LoadParseExtractedFields, LoadParseReferenceItem, LoadParseStopItem
from app.services.critical_extraction_v11_guardrails import (
    apply_critical_extraction_v11_guardrails,
    coercive_prune_critical_payload,
)
from app.services.critical_extraction_v11_map import map_critical_v11_to_extracted_fields
from app.services.critical_extraction_v11_prompt import build_critical_v11_system_prompt
from app.services.extraction_field_learning import record_extraction_field_learning_load_lab_ai_snapshot
from app.services import load_lab as load_lab_v1
from app.services import load_lab_review as load_lab_review_v3
from app.services.load_lab_broker_contact_email_diagnostics import build_broker_contact_email_parse_diagnostics
from app.services.load_lab_broker_matrix import build_broker_confidence_matrix, load_broker_match_signals
from app.services.load_lab_diagnostics import build_parse_diagnostics
from app.services.load_lab_grounding import ground_party_mentions_to_brokers
from app.services.load_lab_reference_extract import (
    augment_diagnostic_reference_resolution,
    merge_structured_references_into_extracted_dict,
)


def _broker_identity_selection_reason(diag: dict[str, Any] | None) -> str:
    """
    Diagnostics-only explanation for broker identity grounding/ranking.
    Does not mutate extracted fields.
    """
    if not diag or not isinstance(diag, dict):
        return "No parse_diagnostics available; broker identity selection reason unavailable."

    matches = diag.get("broker_directory_matches") if isinstance(diag.get("broker_directory_matches"), list) else []
    mc = next((m for m in matches if isinstance(m, dict) and m.get("matched_by") == "mc"), None)
    dot = next((m for m in matches if isinstance(m, dict) and m.get("matched_by") == "dot"), None)
    if mc and isinstance(mc.get("broker_display"), str):
        v = str(mc.get("matched_authority_value") or mc.get("mc_number") or "").strip()
        return f"Grounded broker identity via MC match ({v or 'mc'}) to broker_directory_matches broker_display={mc.get('broker_display')!r}."
    if dot and isinstance(dot.get("broker_display"), str):
        v = str(dot.get("matched_authority_value") or dot.get("dot_number") or "").strip()
        return f"Grounded broker identity via DOT match ({v or 'dot'}) to broker_directory_matches broker_display={dot.get('broker_display')!r}."

    # Otherwise use broker confidence matrix top row if present.
    bcm = diag.get("broker_confidence_matrix") if isinstance(diag.get("broker_confidence_matrix"), list) else []
    if bcm:
        top = bcm[0] if isinstance(bcm[0], dict) else None
        if top:
            nm = str(top.get("name") or "").strip()
            grounded = bool(top.get("is_grounded_to_broker_db") is True)
            conf = str(top.get("confidence") or "")
            tot = top.get("total_score")
            if grounded:
                return f"Top broker candidate {nm!r} is grounded to broker DB; confidence={conf!r} total_score={tot!r}."
            return f"Top broker candidate {nm!r} selected from document identity signals (not DB-grounded); confidence={conf!r} total_score={tot!r}."

    # Fall back to ranking preview if available.
    prev = diag.get("pre_ai_score_buckets") if isinstance(diag.get("pre_ai_score_buckets"), dict) else {}
    rp = prev.get("ranking_preview") if isinstance(prev.get("ranking_preview"), dict) else {}
    pref = rp.get("preferred_document_level_broker")
    if isinstance(pref, str) and pref.strip():
        return f"Preferred document-level broker candidate from ranking preview: {pref.strip()!r} (not directory-grounded)."

    return "No grounded broker identity match found in tenant/global broker reference; broker identity remains ungrounded."

# Contract pins (bump when prompt or JSON shape changes).
SEMANTIC_PROMPT_VERSION = "load_lab_semantic_v2_1"
SEMANTIC_SCHEMA_VERSION = "load_lab_candidate_truckerjson_v1"
CRITICAL_EXTRACTION_V11_SCHEMA_VERSION = "critical_extraction_v1_1"

_MAX_TEXT_FOR_MODEL = 100_000
_OPENAI_TIMEOUT_S = 120.0

_ALLOWED_STOP_TYPES = frozenset({"pickup", "delivery", "drop", "other"})

_LEGAL_ENTITY_SUFFIX_RE = re.compile(
    r"\b(inc\.?|llc|ltd\.?|limited|corp\.?|corporation)\b",
    re.IGNORECASE,
)
_BUSINESS_IDENTITY_TOKEN_RE = re.compile(
    r"\b(logistics|transport(?:ation)?|freight|brokerage|supply\s*chain|group)\b",
    re.IGNORECASE,
)

_CARRIER_ROLE_CTX_RE = re.compile(
    r"\b(carrier\s*name|carrier\s*signature|driver\s*phone|attn:|dispatcher|driver)\b",
    re.IGNORECASE,
)


def _carrier_role_penalty(name: str, *, raw_text: str | None) -> int:
    """
    Strong negative signal: candidate is presented in explicit carrier/driver/signature context.

    This is intentionally *not* broker-DB dependent.
    """
    n = (name or "").strip()
    if not n:
        return 0
    t = raw_text or ""
    if not t:
        return 0
    # quick path: if the name itself looks like a carrier legal registration line.
    if " dba " in n.casefold():
        return 6
    if re.match(r"^\d{4,}\b", n):
        return 6
    # contextual penalty: carrier labels near the name.
    idx = t.casefold().find(n.casefold())
    if idx < 0:
        return 0
    window = t[max(0, idx - 180) : idx + len(n) + 180]
    return 6 if _CARRIER_ROLE_CTX_RE.search(window) else 0


def _document_broker_identity_score(m: dict[str, Any], *, raw_text: str | None) -> int:
    score = 0
    if m.get("is_document_identity_level") is True:
        score += 6
    if m.get("is_header_level") is True:
        score += 2
    nm0 = str(m.get("name") or "")
    if _LEGAL_ENTITY_SUFFIX_RE.search(nm0) or _BUSINESS_IDENTITY_TOKEN_RE.search(nm0):
        score += 1
    # Prefer repeated document-level mentions (coarse but stable).
    nm = str(m.get("name") or "").strip()
    if raw_text and nm:
        score += min((raw_text.casefold().count(nm.casefold())), 10)
    return score


def _best_ranked_document_level_broker(diag: dict[str, Any] | None, *, raw_text: str | None = None) -> str | None:
    """
    Best-effort ranking for a document-level booking broker candidate.

    Priority (Phase 2):
    - MC/DOT grounded broker_directory_matches with high confidence
    - other broker_directory_matches with broker_display
    - header-level party mention names
    """
    if not diag or not isinstance(diag, dict):
        return None
    matches = diag.get("broker_directory_matches")
    if isinstance(matches, list):
        # Prefer authority matches
        for rec in matches:
            if not isinstance(rec, dict):
                continue
            if rec.get("matched_by") in ("mc", "dot") and isinstance(rec.get("broker_display"), str):
                return rec["broker_display"].strip() or None
        # Any other grounded broker_display
        for rec in matches:
            if isinstance(rec, dict) and isinstance(rec.get("broker_display"), str):
                v = rec["broker_display"].strip()
                if v:
                    return v
    pm = diag.get("party_mentions")
    if isinstance(pm, list):
        raw = raw_text or ""
        best_name: str | None = None
        best_score: int = -10**9
        for m in pm:
            if not isinstance(m, dict):
                continue
            nm = m.get("name")
            if not isinstance(nm, str) or not nm.strip():
                continue
            # Only consider document-level-ish candidates (this allows corporate-info wins even if not header).
            if m.get("is_document_identity_level") is not True and m.get("is_header_level") is not True:
                continue
            name = nm.strip()
            score = _document_broker_identity_score(m, raw_text=raw)
            score -= _carrier_role_penalty(name, raw_text=raw)
            if score > best_score:
                best_score = score
                best_name = name
        return best_name
    return None


def _party_label_for_name(diag: dict[str, Any] | None, name: str) -> set[str]:
    if not diag or not isinstance(diag, dict) or not name:
        return set()
    pm = diag.get("party_mentions")
    if not isinstance(pm, list):
        return set()
    out: set[str] = set()
    for m in pm:
        if not isinstance(m, dict):
            continue
        nm = m.get("name")
        if isinstance(nm, str) and nm.strip().casefold() == name.strip().casefold():
            labels = m.get("nearby_labels")
            if isinstance(labels, list):
                out |= {str(x) for x in labels if isinstance(x, str)}
    return out


def _looks_like_decimal_number(s: str) -> bool:
    try:
        s2 = (s or "").strip()
        if not s2:
            return False
        if s2.count(".") != 1:
            return False
        left, right = s2.split(".", 1)
        return right.isdigit() and len(right) in (1, 2) and any(c.isdigit() for c in left)
    except Exception:
        return False


def _numeric_gating_on_reference(
    *,
    extracted: dict[str, Any],
    diag: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    """
    Post-AI numeric guardrail:
    - decimal / money-like / weight-like values should not become broker_load_reference without strong label support.
    """
    review_flags: list[dict[str, Any]] = []
    warnings: list[str] = []

    ref = (extracted.get("broker_load_reference") or "").strip()
    if not ref:
        return extracted, review_flags, warnings

    # If the model chose a decimal-ish value as reference, treat as suspicious.
    if _looks_like_decimal_number(ref):
        review_flags.append(
            {
                "id": "decimal_reference_suspicious",
                "severity": "warning",
                "detail": f"broker_load_reference looks decimal-like ({ref!r}); likely money/weight/rate unless strongly labeled.",
            }
        )
        warnings.append("[review] broker_load_reference looks like a decimal amount; verify reference vs rate/weight.")
        # Prefer leaving unknown over forcing wrong reference.
        extracted["broker_load_reference"] = None

    # If diagnostics indicate money/weight signals and no explicit reference-like candidates, downgrade.
    if diag and isinstance(diag, dict) and extracted.get("broker_load_reference"):
        nums = diag.get("numeric_candidates")
        if isinstance(nums, list):
            any_money = any(isinstance(x, dict) and x.get("kind_hint") == "money_like" for x in nums)
            any_weight = any(isinstance(x, dict) and x.get("kind_hint") == "weight_like" for x in nums)
            if (any_money or any_weight) and _looks_like_decimal_number(ref):
                extracted["broker_load_reference"] = None

    return extracted, review_flags, warnings


def _rank_reference_candidates(diag: dict[str, Any] | None) -> dict[str, Any]:
    """
    Diagnostics-only: rank reference candidates by kind and evidence.
    Returns { best_by_kind: {kind: candidate}, primary_reference: candidate|None }.
    """
    if not diag or not isinstance(diag, dict):
        return {"best_by_kind": {}, "primary_reference": None}
    cands = diag.get("reference_candidates")
    if not isinstance(cands, list):
        return {"best_by_kind": {}, "primary_reference": None}

    def score(c: dict[str, Any]) -> int:
        s = 0
        kind = str(c.get("kind") or "")
        zone = str(c.get("zone") or "")
        label = str(c.get("label") or "").casefold()
        val = str(c.get("value") or "")
        line = str(c.get("line_text") or "").casefold()
        if zone == "header_title_zone":
            s += 2
        if any(x in label for x in ("el", "freight", "bill", "po", "pickup", "delivery", "load", "order", "reference")):
            s += 3
        # Preference buckets
        if kind in ("broker_load_number", "shipment_number", "dispatch_number"):
            s += 10
        elif kind in ("order_number", "load_number", "order_token"):
            s += 8
        elif kind in ("el_number",):
            s += 6
        elif kind in ("freight_bill_number", "invoice_number", "audit_id"):
            # Accounting labels must not become primary by default.
            s -= 40
        elif kind in ("po_number",):
            s += 3
        # avoid decimals as IDs
        if _looks_like_decimal_number(val):
            s -= 20
        # If the line shows this value as the integer part of a decimal (e.g. "42180.00"), downrank hard.
        if val and (f"{val}." in line or re.search(rf"\\b{re.escape(val)}\\.\\d{{1,2}}\\b", line)):
            s -= 15
        # Alphanumeric/order-style token beats unlabeled numeric candidate
        if any(ch.isalpha() for ch in val) and any(ch.isdigit() for ch in val):
            s += 4
        # Downrank values near weight/qty/rate/miles
        if any(x in line for x in ("weight", "wgt", "lbs", "qty", "rate", "miles", "distance", "$")):
            s -= 8
        return s

    scored = [c for c in cands if isinstance(c, dict) and isinstance(c.get("value"), str)]
    scored.sort(key=lambda x: score(x), reverse=True)

    best_by_kind: dict[str, Any] = {}
    for c in scored:
        k = str(c.get("kind") or "reference")
        if k not in best_by_kind:
            best_by_kind[k] = c

    # Primary reference preference order (broker_load_reference)
    for k in (
        "broker_load_number",
        "shipment_number",
        "dispatch_number",
        "order_number",
        "order_token",
        "load_number",
        "el_number",
        "po_number",
        "reference",
    ):
        if k in best_by_kind:
            return {"best_by_kind": best_by_kind, "primary_reference": best_by_kind[k]}
    return {"best_by_kind": best_by_kind, "primary_reference": None}


def _apply_reference_role_ranking(
    *,
    extracted: dict[str, Any],
    diag: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    """
    Phase 2+: numeric/reference role handling beyond decimal blocking.
    - Choose broker_load_reference from ranked labeled reference candidates when available.
    - Add diagnostics-only ranked output under parse_diagnostics.reference_ranking.
    """
    review_flags: list[dict[str, Any]] = []
    warnings: list[str] = []
    if not diag or not isinstance(diag, dict):
        return extracted, review_flags, warnings

    ranking = _rank_reference_candidates(diag)
    diag["reference_ranking"] = ranking
    primary = ranking.get("primary_reference") if isinstance(ranking, dict) else None

    if isinstance(primary, dict):
        val = str(primary.get("value") or "").strip()
        kind = str(primary.get("kind") or "")
        if val and not _looks_like_decimal_number(val):
            # Only override if model left it blank or filled something suspicious.
            current = (extracted.get("broker_load_reference") or "").strip()
            if not current:
                extracted["broker_load_reference"] = val
            # If we have a strong labeled order/load reference, override ambiguous numeric.
            if (
                current
                and current.strip() != val
                and kind in ("order_number", "order_token", "load_number")
                and current.isdigit()
                and len(current) >= 5
            ):
                # Preserve the old value as an additional reference candidate.
                refs0 = extracted.get("references")
                if not isinstance(refs0, list):
                    refs0 = []
                refs0.append({"kind": "prior_broker_load_reference", "value": current[:120]})
                extracted["references"] = refs0
                extracted["broker_load_reference"] = val
                review_flags.append(
                    {
                        "id": "reference_overridden_by_ranked_order_load",
                        "severity": "warning",
                        "detail": f"Overrode broker_load_reference={current!r} with ranked {kind}={val!r}.",
                    }
                )
                warnings.append("[review] Overrode ambiguous broker_load_reference with ranked order/load reference; verify.")
            # If current looks decimal-like and we have a better candidate, replace.
            if current and _looks_like_decimal_number(current):
                extracted["broker_load_reference"] = val
                review_flags.append(
                    {
                        "id": "reference_replaced_decimal",
                        "severity": "warning",
                        "detail": f"Replaced decimal-like broker_load_reference with labeled {kind} candidate {val!r}.",
                    }
                )
                warnings.append("[review] Replaced decimal-like reference with labeled document reference; verify.")

            # Preserve alternates in extracted.references (diagnostics + stable parse field).
            refs = extracted.get("references")
            if not isinstance(refs, list):
                refs = []
            seen = {(str(r.get("kind")), str(r.get("value"))) for r in refs if isinstance(r, dict)}
            best_by_kind = ranking.get("best_by_kind") if isinstance(ranking, dict) else {}
            if isinstance(best_by_kind, dict):
                # Keep up to 6 best distinct references (including the "other" RXO token like LZ179967).
                for k2, c2 in list(best_by_kind.items())[:10]:
                    if not isinstance(c2, dict):
                        continue
                    v2 = str(c2.get("value") or "").strip()
                    if not v2 or _looks_like_decimal_number(v2):
                        continue
                    item = {"kind": str(k2), "value": v2[:120]}
                    key = (item["kind"], item["value"])
                    if key in seen:
                        continue
                    # Don't duplicate the primary as a secondary reference entry.
                    if item["value"] == val and item["kind"] == kind:
                        continue
                    refs.append(item)
                    seen.add(key)
                    if len(refs) >= 6:
                        break
            extracted["references"] = refs

    return extracted, review_flags, warnings


def _cleanup_trailer_and_temp_fields(extracted: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str], list[str]]:
    """
    Deterministic cleanup to protect canonical workspace mapping:
    - trailer_type / trailer_size flip (e.g. '53 ft' belongs in size)
    - temperature_requirement must be a value, not a section label
    """
    field_conf: dict[str, str] = {}
    warnings: list[str] = []

    tt = (extracted.get("trailer_type") or "").strip()
    ts = (extracted.get("trailer_size") or "").strip()

    # If trailer_type looks like a size, move it to trailer_size.
    if tt and (("ft" in tt.casefold()) or re.search(r"\b\d{2}\s*ft\b", tt, re.I) or tt.strip().isdigit()):
        if not ts:
            extracted["trailer_size"] = tt
            extracted["trailer_type"] = None
        else:
            # If trailer_size looks like a type and trailer_type looks like a size, swap.
            if any(x in ts.casefold() for x in ("van", "reefer", "flat", "step", "dry")):
                extracted["trailer_type"], extracted["trailer_size"] = ts, tt
        field_conf.update({"trailer_type": "low", "trailer_size": "low"})
        warnings.append("[review] Trailer type/size looked flipped; normalized (type vs size).")

    # If trailer_size is empty but we can infer it from equipment_type (common: 'Van - 53 Feet')
    ts = (extracted.get("trailer_size") or "").strip()
    if not ts:
        eq = (extracted.get("equipment_type") or "").strip()
        m = re.search(r"\b(\d{2})\s*(?:ft|feet)\b", eq, re.I)
        if m:
            extracted["trailer_size"] = f"{m.group(1)} ft"
            field_conf["trailer_size"] = "low"

    # If trailer_type is empty but we can infer it from equipment_type ('Van', 'Reefer', etc.)
    tt = (extracted.get("trailer_type") or "").strip()
    if not tt:
        eq = (extracted.get("equipment_type") or "").strip()
        if eq:
            head = eq.split("-", 1)[0].strip()
            if head and head.casefold() in ("van", "reefer", "flatbed", "flat", "step deck", "stepdeck", "dry van"):
                extracted["trailer_type"] = "Van" if head.casefold() in ("van", "dry van") else head.title()
                field_conf["trailer_type"] = "low"

    # Temperature requirement: reject obvious label-as-value.
    temp = (extracted.get("temperature_requirement") or "").strip()
    if temp and temp.casefold() in (
        "special temp instructions",
        "temperature",
        "temp",
        "temp instructions",
    ):
        extracted["temperature_requirement"] = None
        field_conf["temperature_requirement"] = "low"
        warnings.append("[review] temperature_requirement looked like a section label; cleared.")

    return extracted, field_conf, warnings


def _normalize_stop_appointments(stops: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str], list[str]]:
    """
    Normalize appointment_type separately from appointment_time_text.
    Examples:
      'Appt 10:30' -> type=APPT, time='10:30'
      'FCFS 02:00 to 23:59' -> type=FCFS, time='02:00 to 23:59'
    """
    field_conf: dict[str, str] = {}
    warnings: list[str] = []

    for s in stops:
        if not isinstance(s, dict):
            continue
        txt = (s.get("appointment_time_text") or "").strip()
        if not txt:
            continue
        low = txt.casefold()
        if low.startswith("appt"):
            s["appointment_type"] = "APPT"
            s["appointment_time_text"] = txt.split(" ", 1)[1].strip() if " " in txt else None
        elif low.startswith("fcfs"):
            s["appointment_type"] = "FCFS"
            s["appointment_time_text"] = txt.split(" ", 1)[1].strip() if " " in txt else None
        # If we normalized anything, stop-level confidence is “low” for now (we don't have per-stop confidence map yet).
    # Workspace contract only supports field_confidence dict[str,str]; keep a general hint.
    # (UI surfaces this; detailed per-stop confidence can remain in diagnostics later.)
    return stops, field_conf, warnings


def _normalize_broker_display_name(name: str | None) -> str | None:
    """
    Canonicalize broker display names to avoid random variants.
    Preferred source is broker directory grounding; this is a fallback normalization only.
    """
    if not isinstance(name, str):
        return None
    s = name.strip()
    if not s:
        return None
    # If the string starts with a short ALLCAPS brand token, prefer that when the remainder looks like legal suffixes.
    m = re.match(r"^([A-Z]{2,6})\\b(.*)$", s)
    if m:
        brand = m.group(1)
        tail = (m.group(2) or "").casefold()
        if any(x in tail for x in ("llc", "inc", "corp", "corporation", "company", "capacity solutions")):
            return brand
    # Common case: legal entity names where brand is a leading token but not necessarily ALLCAPS.
    if "capacity solutions" in s.casefold() and s.casefold().startswith("rxo"):
        return "RXO"
    return s


def _norm_auth_digits(v: Any) -> str | None:
    if not isinstance(v, str):
        return None
    d = re.sub(r"\D+", "", v.strip())
    return d if d else None


def _authority_entry_kind(ent: dict[str, Any]) -> str:
    k = str(ent.get("type") or ent.get("kind") or "").strip().casefold()
    if k == "mc":
        return "mc"
    if k == "dot":
        return "dot"
    return ""


def _authority_entries_from_diag(diag: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not diag or not isinstance(diag, dict):
        return []
    ac = diag.get("authority_candidates")
    if not isinstance(ac, dict):
        return []
    ent = ac.get("entries")
    if not isinstance(ent, list):
        return []
    return [e for e in ent if isinstance(e, dict)]


def _apply_broker_authority_context_repair(
    *,
    extracted: dict[str, Any],
    diag: dict[str, Any],
    broker_name: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str], dict[str, str]]:
    """
    Deterministic broker MC/DOT repair using authority_candidates[].role_hint.

    - Never assign carrier_context MC/DOT to broker snapshot fields.
    - Prefer broker_context (or unknown with broker-supporting surrounding text) MC/DOT.
    - broker_dot_number_snapshot is cleared unless a broker_context DOT exists matching the value.
    """
    flags: list[dict[str, Any]] = []
    warnings: list[str] = []
    field_conf: dict[str, str] = {}
    entries = _authority_entries_from_diag(diag)
    if not entries:
        return extracted, flags, warnings, field_conf

    bn_cf = (broker_name or "").casefold()
    name_tokens = [t for t in re.split(r"\W+", bn_cf) if len(t) > 3]

    _dom_list = diag.get("broker_match_domains") if isinstance(diag.get("broker_match_domains"), list) else []
    broker_domain_hints = [str(d).strip().casefold() for d in _dom_list if isinstance(d, str) and str(d).strip()]

    def _unknown_supports_broker(e: dict[str, Any]) -> bool:
        if e.get("role_hint") != "unknown":
            return False
        sur = (e.get("surrounding_text") or "").casefold()
        if name_tokens and any(t in sur for t in name_tokens):
            return True
        for dom in broker_domain_hints:
            if dom and dom in sur:
                return True
        return any(
            x in sur
            for x in (
                "corporate information",
                "freight broker",
                "invoice instructions",
                "quickpay",
            )
        )

    carrier_mc = {
        v
        for e in entries
        if _authority_entry_kind(e) == "mc" and e.get("role_hint") == "carrier_context" and (v := _norm_auth_digits(e.get("value")))
    }
    carrier_dot = {
        v
        for e in entries
        if _authority_entry_kind(e) == "dot" and e.get("role_hint") == "carrier_context" and (v := _norm_auth_digits(e.get("value")))
    }

    broker_mc_ordered: list[str] = []
    for e in entries:
        if _authority_entry_kind(e) != "mc" or e.get("role_hint") != "broker_context":
            continue
        v = _norm_auth_digits(e.get("value"))
        if v and v not in carrier_mc and v not in broker_mc_ordered:
            broker_mc_ordered.append(v)
    for e in entries:
        if _authority_entry_kind(e) != "mc" or e.get("role_hint") != "unknown":
            continue
        v = _norm_auth_digits(e.get("value"))
        if not v or v in carrier_mc or v in broker_mc_ordered:
            continue
        if _unknown_supports_broker(e):
            broker_mc_ordered.append(v)

    broker_dot_allowed = {
        v
        for e in entries
        if _authority_entry_kind(e) == "dot" and e.get("role_hint") == "broker_context" and (v := _norm_auth_digits(e.get("value")))
    }

    cur_mc = _norm_auth_digits(extracted.get("broker_mc_number_snapshot"))
    cur_dot = _norm_auth_digits(extracted.get("broker_dot_number_snapshot"))

    if cur_mc and cur_mc in carrier_mc:
        replacement = next((x for x in broker_mc_ordered if x not in carrier_mc), None)
        if replacement:
            extracted["broker_mc_number_snapshot"] = replacement
            flags.append(
                {
                    "id": "broker_authority_context_mismatch_mc",
                    "severity": "warning",
                    "detail": f"broker_mc_number_snapshot {cur_mc!r} matched a carrier-context authority line; replaced with {replacement!r}.",
                }
            )
            warnings.append("[review] Broker MC/DOT repaired using authority role hints (carrier vs broker context).")
            field_conf["broker_mc_number_snapshot"] = "low"
        else:
            extracted["broker_mc_number_snapshot"] = None
            flags.append(
                {
                    "id": "broker_authority_carrier_mc_cleared",
                    "severity": "warning",
                    "detail": f"Cleared broker_mc_number_snapshot {cur_mc!r} (carrier-context only; no broker-context MC found).",
                }
            )
            warnings.append("[review] Cleared broker MC that came from carrier-context authority.")
            field_conf["broker_mc_number_snapshot"] = "low"
        cur_mc = _norm_auth_digits(extracted.get("broker_mc_number_snapshot"))

    if cur_dot:
        if cur_dot in carrier_dot or cur_dot not in broker_dot_allowed:
            extracted["broker_dot_number_snapshot"] = None
            flags.append(
                {
                    "id": "broker_authority_dot_cleared_or_carrier",
                    "severity": "warning",
                    "detail": f"Cleared broker_dot_number_snapshot {cur_dot!r} (carrier-context or not broker-context DOT).",
                }
            )
            warnings.append("[review] Broker DOT cleared: only broker-context DOT lines may populate broker_dot_number_snapshot.")
            field_conf["broker_dot_number_snapshot"] = "low"

    return extracted, flags, warnings, field_conf


def _apply_broker_display_name_normalization(
    *,
    extracted: dict[str, Any],
    diag: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, str], list[str]]:
    """
    Normalization-only (not a parsing fix):
    - If grounded to a broker_directory_match, use broker_display consistently.
    - Else apply conservative display-name normalization (e.g. 'RXO Capacity Solutions, LLC' -> 'RXO').
    """
    field_conf: dict[str, str] = {}
    warnings: list[str] = []

    cur = (extracted.get("broker_name_snapshot") or "").strip()
    if not cur:
        return extracted, field_conf, warnings

    grounded = None
    if diag and isinstance(diag, dict):
        matches = diag.get("broker_directory_matches")
        if isinstance(matches, list):
            # Prefer highest-confidence grounded match display when present.
            for rec in matches:
                if not isinstance(rec, dict):
                    continue
                bd = rec.get("broker_display")
                if isinstance(bd, str) and bd.strip():
                    grounded = bd.strip()
                    if rec.get("confidence") == "high":
                        break

    if grounded and grounded.casefold() != cur.casefold():
        extracted["broker_name_snapshot"] = grounded
        field_conf["broker_name_snapshot"] = "low"
        warnings.append("[review] Normalized broker_name_snapshot to broker directory display name.")
        return extracted, field_conf, warnings

    norm = _normalize_broker_display_name(cur)
    if norm and norm != cur:
        extracted["broker_name_snapshot"] = norm
        # This is cosmetic normalization; don't force warnings spam, but keep confidence low.
        field_conf["broker_name_snapshot"] = "low"
    return extracted, field_conf, warnings


def _compute_pre_ai_score_buckets(diag: dict[str, Any], *, raw_text: str | None) -> dict[str, Any]:
    """
    Phase 2: explicit, explainable score buckets (not magic prompt-only).
    These are coarse indicators used for ranking / review flags.
    """
    pm = diag.get("party_mentions") if isinstance(diag.get("party_mentions"), list) else []
    matches = diag.get("broker_directory_matches") if isinstance(diag.get("broker_directory_matches"), list) else []

    header_names: set[str] = set()
    stop_names: set[str] = set()
    contact_names: set[str] = set()
    customs_names: set[str] = set()

    for m in pm:
        if not isinstance(m, dict):
            continue
        nm = (m.get("name") or "").strip()
        if not nm:
            continue
        if m.get("is_header_level") is True:
            header_names.add(nm)
        if m.get("is_stop_level") is True:
            stop_names.add(nm)
        if m.get("is_contact_block") is True:
            contact_names.add(nm)
        labels = m.get("nearby_labels")
        if isinstance(labels, list):
            labels_cf = {str(x).casefold() for x in labels if isinstance(x, str)}
            if any("custom" in s for s in labels_cf):
                customs_names.add(nm)

    has_mc_or_dot = any(
        isinstance(rec, dict) and rec.get("matched_by") in ("mc", "dot") for rec in matches
    )
    grounded_displays = [
        rec.get("broker_display")
        for rec in matches
        if isinstance(rec, dict) and isinstance(rec.get("broker_display"), str) and rec.get("broker_display").strip()
    ]

    out = {
        "document_level": {
            "header_party_count": len(header_names),
            "contact_block_party_count": len(contact_names),
            "broker_directory_match_count": len(matches),
            "has_mc_or_dot_match": bool(has_mc_or_dot),
        },
        "local_stop_level": {
            "stop_party_count": len(stop_names),
        },
        "customs_signals": {
            "customs_labeled_party_count": len(customs_names),
        },
        "ranking_preview": {
            "preferred_document_level_broker": _best_ranked_document_level_broker(diag, raw_text=raw_text),
            "grounded_broker_displays": grounded_displays[:10],
        },
    }
    return out


def _classify_broker_role_candidates(diag: dict[str, Any], *, raw_text: str | None) -> dict[str, Any]:
    """
    Phase 3-ish structure (still diagnostics-only):
    - booking_broker_candidates[]
    - customs_broker_candidates[]
    - secondary_broker_candidates[]
    """
    pm = diag.get("party_mentions") if isinstance(diag.get("party_mentions"), list) else []
    matches = diag.get("broker_directory_matches") if isinstance(diag.get("broker_directory_matches"), list) else []
    raw = (raw_text or "").casefold()

    def occ(name: str) -> int:
        if not raw or not name:
            return 0
        return min(raw.count(name.casefold()), 20)

    # Map grounded broker_display -> match records
    grounded: dict[str, list[dict[str, Any]]] = {}
    for rec in matches:
        if not isinstance(rec, dict):
            continue
        bd = rec.get("broker_display")
        if isinstance(bd, str) and bd.strip():
            grounded.setdefault(bd.strip(), []).append(rec)

    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for m in pm:
        if not isinstance(m, dict):
            continue
        name = (m.get("name") or "").strip()
        if not name:
            continue
        k = name.casefold()
        if k in seen:
            continue
        seen.add(k)

        labels = m.get("nearby_labels")
        labels_cf = {str(x).casefold() for x in labels} if isinstance(labels, list) else set()
        is_customs = any("custom" in x for x in labels_cf) or "customs broker" in labels_cf
        is_broker_labeled = "broker" in labels_cf
        is_doc_identity = m.get("is_document_identity_level") is True
        is_header = m.get("is_header_level") is True

        score = 0
        score += occ(name) * 2
        if is_doc_identity:
            score += 6
        if is_header:
            score += 1
        if is_broker_labeled:
            score += 1
        if is_customs:
            score -= 2  # customs != booking broker by default
        # Grounding boost (especially authority)
        g = grounded.get(name) or []
        if any(isinstance(r, dict) and r.get("matched_by") in ("mc", "dot") for r in g):
            score += 10
        elif g:
            score += 4

        candidates.append(
            {
                "name": name,
                "score": score,
                "signals": {
                    "occurrences": occ(name),
                    "is_document_identity_level": bool(is_doc_identity),
                    "is_header_level": bool(is_header),
                    "is_broker_labeled": bool(is_broker_labeled),
                    "is_customs_labeled": bool(is_customs),
                    "broker_directory_matches": g[:5],
                },
            }
        )

    candidates.sort(key=lambda x: int(x.get("score") or 0), reverse=True)

    booking = [c for c in candidates if not c["signals"]["is_customs_labeled"]][:10]
    customs = [c for c in candidates if c["signals"]["is_customs_labeled"]][:10]
    secondary = [c for c in candidates if c not in booking][:10]

    return {
        "booking_broker_candidates": booking,
        "customs_broker_candidates": customs,
        "secondary_broker_candidates": secondary,
    }

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _raw_text_from_run(run: LoadLabExtractionRun) -> str:
    pkg = run.normalized_package or {}
    raw = pkg.get("raw_full_text")
    return raw if isinstance(raw, str) else ""


def _warning_base(warnings: list[Any] | None) -> list[Any]:
    return load_lab_review_v3.warning_base_without_semantic_or_lab_review(warnings)


def _system_prompt() -> str:
    return (
        "You are extracting structured truck load booking data from a rate confirmation or similar PDF text. "
        "Return JSON only, matching the provided JSON schema. "
        "Use null for unknown scalar fields. For lists, use [] when unknown. "
        "Map stops in sequence order (0-based sequence). stop_type must be one of: pickup, delivery, drop, other. "
        "appointment_date must be YYYY-MM-DD or null. "
        "Do not invent broker MC/DOT numbers; use null if not clearly present in the text. "
        "CRITICAL role rules: document-level identity beats stop-level one-off labels; "
        "MC-backed broker evidence outranks customs/local mentions; "
        "do not treat weight-like / money-like decimals as primary load references unless label evidence is strong. "
        "Populate extracted.references with {kind,value} objects for each distinct labeled identifier you see "
        "(load_number, order_number, bol_number, po_number, pro_number, shipment_number, broker_load_number, etc.); "
        "use parse_diagnostics.reference_candidates as hints, not ground truth."
    )


def _deterministic_validate(resp: LoadDocumentParseResponse) -> dict[str, Any]:
    issues: list[str] = []
    ex = resp.extracted
    if ex.rate is not None and ex.rate < 0:
        issues.append("extracted.rate must be >= 0 when set")
    if ex.customer_rate is not None and ex.customer_rate < 0:
        issues.append("extracted.customer_rate must be >= 0 when set")
    if ex.miles is not None and ex.miles < 0:
        issues.append("extracted.miles must be >= 0 when set")
    if ex.estimated_weight is not None and ex.estimated_weight < 0:
        issues.append("extracted.estimated_weight must be >= 0 when set")
    for i, stop in enumerate(ex.stops):
        if stop.stop_type not in _ALLOWED_STOP_TYPES:
            issues.append(f"stops[{i}].stop_type invalid: {stop.stop_type!r}")
    checks = {
        "rates_non_negative": not any("rate" in x for x in issues),
        "miles_non_negative": not any("miles" in x for x in issues),
        "stop_types_known": not any("stop_type" in x for x in issues),
    }
    return {"ok": len(issues) == 0, "issues": issues, "checks": checks}


async def _openai_chat_json_schema(
    *,
    api_key: str,
    model: str,
    system: str,
    user_text: str,
    schema: dict[str, Any],
    schema_name: str,
) -> dict[str, Any]:
    """POST /v1/chat/completions with json_schema; falls back to json_object on unsupported model."""
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body_schema = {
        "model": model,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_text},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "strict": False, "schema": schema},
        },
    }
    async with httpx.AsyncClient(timeout=_OPENAI_TIMEOUT_S) as client:
        r = await client.post(url, headers=headers, json=body_schema)
        if r.status_code == 200:
            return r.json()
        err_snip = (r.text or "")[:800]
        # Some models return 400 for json_schema — retry plain json_object.
        if r.status_code == 400 and "json_schema" in err_snip.lower():
            body_obj = {
                "model": model,
                "temperature": 0.1,
                "messages": [
                    {"role": "system", "content": system + " Respond with a single JSON object only."},
                    {
                        "role": "user",
                        "content": (
                            "Extract load fields. Required top-level keys: document (object with filename), "
                            "extracted (object with broker fields, references array, stops array), "
                            "extraction_warnings (array of strings, may be empty).\n\n---\n\n"
                            f"{user_text}"
                        ),
                    },
                ],
                "response_format": {"type": "json_object"},
            }
            r2 = await client.post(url, headers=headers, json=body_obj)
            r2.raise_for_status()
            return r2.json()
        r.raise_for_status()
        return r.json()


def _parse_openai_payload(data: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None, str | None]:
    """Returns (content_json_str, usage_dict, error_message)."""
    try:
        choice0 = (data.get("choices") or [{}])[0]
        msg = choice0.get("message") or {}
        content = msg.get("content")
        if not isinstance(content, str) or not content.strip():
            return None, data.get("usage") if isinstance(data.get("usage"), dict) else None, "Empty model message"
        return content.strip(), data.get("usage") if isinstance(data.get("usage"), dict) else None, None
    except Exception as exc:  # noqa: BLE001
        return None, None, str(exc)[:500]


def _coerce_model_payload_to_schema(obj: Any) -> dict[str, Any]:
    """Best-effort prune/coerce model JSON into our strict schema shape."""
    allowed_ex_keys = set(LoadParseExtractedFields.model_fields.keys())
    allowed_stop_keys = set(LoadParseStopItem.model_fields.keys())
    allowed_ref_keys = set(LoadParseReferenceItem.model_fields.keys())

    o = obj if isinstance(obj, dict) else {}
    doc = o.get("document") if isinstance(o.get("document"), dict) else {}
    ex = o.get("extracted") if isinstance(o.get("extracted"), dict) else {}
    warnings = o.get("extraction_warnings") if isinstance(o.get("extraction_warnings"), list) else []

    cleaned_ex: dict[str, Any] = {}
    for k in allowed_ex_keys:
        if k in ex:
            cleaned_ex[k] = ex.get(k)

    # references: coerce each item to {kind,value}
    refs_in = cleaned_ex.get("references")
    if isinstance(refs_in, list):
        refs_out: list[dict[str, Any]] = []
        for it in refs_in:
            if not isinstance(it, dict):
                continue
            r: dict[str, Any] = {}
            for rk in allowed_ref_keys:
                if rk in it:
                    r[rk] = it.get(rk)
            if isinstance(r.get("kind"), str) and isinstance(r.get("value"), str):
                refs_out.append({"kind": r["kind"], "value": r["value"]})
            if len(refs_out) >= 40:
                break
        cleaned_ex["references"] = refs_out

    # stops: coerce each item to allowed keys only
    stops_in = cleaned_ex.get("stops")
    if isinstance(stops_in, list):
        stops_out: list[dict[str, Any]] = []
        for it in stops_in:
            if not isinstance(it, dict):
                continue
            s: dict[str, Any] = {}
            for sk in allowed_stop_keys:
                if sk in it:
                    s[sk] = it.get(sk)
            # require minimal fields
            if isinstance(s.get("stop_type"), str) and isinstance(s.get("sequence"), int):
                stops_out.append(s)
            if len(stops_out) >= 60:
                break
        cleaned_ex["stops"] = stops_out

    cleaned = {
        "document": {"filename": str(doc.get("filename") or "")[:512]},
        "extracted": cleaned_ex,
        "extraction_warnings": [str(x)[:500] for x in warnings if isinstance(x, (str, int, float))][:50],
    }
    return cleaned


async def semantic_extract_run(
    db: AsyncSession,
    *,
    tenant_id: int,
    run_id: int,
    force: bool = False,
    mode: str = "guarded",
    response_contract: str = "truckerjson",
) -> LoadLabExtractionRun | None:
    run = await load_lab_v1.get_run(db, tenant_id, run_id)
    if run is None:
        return None

    raw_full = _raw_text_from_run(run).strip()
    base_warnings = _warning_base(run.warnings)

    def _persist() -> None:
        run.updated_at = _utcnow()

    # Idempotent cache
    if (
        not force
        and run.semantic_extract_status == "success"
        and run.parse_response is not None
    ):
        return run

    mode_cf = (mode or "guarded").strip().casefold()
    if mode_cf not in ("guarded", "pure_ai", "ai_validate_only"):
        mode_cf = "guarded"

    rc_raw = (response_contract or "truckerjson").strip().casefold()
    use_critical_v11 = rc_raw in ("critical_v1_1", "critical_extraction_v1_1")
    if rc_raw not in ("truckerjson", "critical_v1_1", "critical_extraction_v1_1"):
        use_critical_v11 = False
        rc_raw = "truckerjson"

    run.semantic_prompt_version = SEMANTIC_PROMPT_VERSION
    run.semantic_schema_version = (
        CRITICAL_EXTRACTION_V11_SCHEMA_VERSION if use_critical_v11 else SEMANTIC_SCHEMA_VERSION
    )

    if run.status != "text_extracted":
        run.semantic_extract_status = "skipped_bad_status"
        run.semantic_model_name = None
        run.parse_response = None if force else run.parse_response
        run.semantic_validation_result = {
            "ok": False,
            "issues": [f"Run status must be text_extracted (got {run.status!r})."],
        }
        run.ai_model_output = {
            "outcome": "skipped_bad_status",
            "prompt_version": SEMANTIC_PROMPT_VERSION,
            "schema_version": run.semantic_schema_version,
        }
        run.warnings = base_warnings
        load_lab_review_v3.clear_lab_review_if_no_candidate(run)
        _persist()
        await db.commit()
        await db.refresh(run)
        return run

    if not raw_full:
        run.semantic_extract_status = "skipped_no_text"
        run.semantic_model_name = None
        run.semantic_validation_result = {"ok": False, "issues": ["No raw_full_text in normalized_package."]}
        run.ai_model_output = {
            "outcome": "skipped_no_text",
            "prompt_version": SEMANTIC_PROMPT_VERSION,
            "schema_version": run.semantic_schema_version,
        }
        run.warnings = base_warnings
        if force:
            run.parse_response = None
        load_lab_review_v3.clear_lab_review_if_no_candidate(run)
        _persist()
        await db.commit()
        await db.refresh(run)
        return run

    key = (settings.openai_api_key or "").strip()
    if not key:
        run.semantic_extract_status = "skipped_missing_key"
        run.semantic_model_name = None
        run.semantic_validation_result = {"ok": False, "issues": ["OPENAI_API_KEY not configured on API."]}
        run.ai_model_output = {
            "outcome": "skipped_missing_key",
            "prompt_version": SEMANTIC_PROMPT_VERSION,
            "schema_version": run.semantic_schema_version,
        }
        run.warnings = base_warnings + ["[semantic] OPENAI_API_KEY not configured; extraction skipped."]
        if force:
            run.parse_response = None
        load_lab_review_v3.clear_lab_review_if_no_candidate(run)
        _persist()
        await db.commit()
        await db.refresh(run)
        return run

    model = (settings.openai_extraction_model or "gpt-4o-mini").strip() or "gpt-4o-mini"
    run.semantic_model_name = model

    text_for_model = raw_full
    truncated = False
    if len(text_for_model) > _MAX_TEXT_FOR_MODEL:
        text_for_model = text_for_model[:_MAX_TEXT_FOR_MODEL]
        truncated = True

    if use_critical_v11:
        schema = CriticalExtractionV11Root.model_json_schema()
        system_for_model = build_critical_v11_system_prompt()
        schema_name_openai = "critical_extraction_v1_1"
    else:
        schema = LoadLabSemanticModelOutput.model_json_schema()
        system_for_model = _system_prompt()
        schema_name_openai = "load_lab_semantic_extract"
    # Build Phase 2 pre-AI evidence packet (diagnostics + broker directory grounding).
    diag: dict[str, Any] | None = None
    reference_merge_pack: dict[str, Any] | None = None
    try:
        pkg = run.normalized_package or {}
        pages = pkg.get("page_texts") if isinstance(pkg, dict) else None
        page_texts: list[str] | None = None
        if isinstance(pages, list):
            page_texts = []
            for it in pages:
                if isinstance(it, dict) and isinstance(it.get("text"), str):
                    page_texts.append(it["text"])
        diag = build_parse_diagnostics(
            raw_full_text=raw_full,
            page_texts=page_texts,
            filename=run.filename,
            extraction_method=(pkg.get("extraction_method") if isinstance(pkg, dict) else None) or "unknown",
            extraction_path=run.extraction_path,
        )
        pm = diag.get("party_mentions") if isinstance(diag, dict) else None
        auth = diag.get("authority_candidates") if isinstance(diag, dict) else None
        matches = await ground_party_mentions_to_brokers(db, tenant_id=tenant_id, party_mentions=pm, authority_candidates=auth)
        diag["broker_directory_matches"] = matches
        diag["pre_ai_score_buckets"] = _compute_pre_ai_score_buckets(diag, raw_text=raw_full)
        diag.update(_classify_broker_role_candidates(diag, raw_text=raw_full))
        try:
            signals = await load_broker_match_signals(db, tenant_id)
            merged_domains: set[str] = set()
            td = signals.get("tenant_domains")
            gd = signals.get("global_domains")
            if isinstance(td, set):
                merged_domains |= td
            if isinstance(gd, set):
                merged_domains |= gd
            diag["broker_match_domains"] = sorted(merged_domains)[:120]
            diag["broker_confidence_matrix"] = build_broker_confidence_matrix(
                diag=diag, raw_text=raw_full, signals=signals
            )
        except Exception:
            diag.setdefault("broker_match_domains", [])
            diag.setdefault("broker_confidence_matrix", [])
        # Diagnostics-only: explain broker identity selection/grounding separately from reference selection.
        try:
            diag["broker_identity_selection_reason"] = _broker_identity_selection_reason(diag)
        except Exception:
            diag["broker_identity_selection_reason"] = "broker_identity_selection_reason_unavailable"
        try:
            reference_merge_pack = augment_diagnostic_reference_resolution(
                diag, raw_full, page_texts, run.filename
            )
        except Exception:
            reference_merge_pack = None
    except Exception:
        diag = None
        reference_merge_pack = None

    if use_critical_v11:
        if mode_cf == "pure_ai":
            user_body = (
                f"Document filename: {run.filename}\n\n"
                f"--- BEGIN EXTRACTED PDF TEXT ---\n{text_for_model}\n--- END ---\n"
            )
        else:
            user_body = (
                f"Document filename: {run.filename}\n\n"
                "Structured pre-extraction evidence (hints only; verify against the PDF text):\n\n"
                "--- BEGIN PARSE_DIAGNOSTICS (JSON) ---\n"
                + (json.dumps(diag)[:20000] if diag is not None else "{}")
                + "\n--- END PARSE_DIAGNOSTICS ---\n\n"
                f"--- BEGIN EXTRACTED PDF TEXT ---\n{text_for_model}\n--- END ---\n"
            )
    elif mode_cf == "pure_ai":
        # Minimal instruction: rely on schema only. Do not send diagnostics hints.
        user_body = (
            f"Filename for document.filename: {run.filename}\n\n"
            f"--- BEGIN EXTRACTED PDF TEXT ---\n{text_for_model}\n--- END ---\n"
        )
    else:
        user_body = (
            f"Filename for document.filename: {run.filename}\n\n"
            "You will receive structured pre-extraction evidence (party mentions, numeric candidates, zones). "
            "Use it to resolve roles carefully, but do not assume any single hint is truth.\n\n"
            "--- BEGIN PARSE_DIAGNOSTICS (JSON) ---\n"
            + (json.dumps(diag)[:20000] if diag is not None else "{}")
            + "\n--- END PARSE_DIAGNOSTICS ---\n\n"
            f"--- BEGIN EXTRACTED PDF TEXT ---\n{text_for_model}\n--- END ---\n"
        )
    if truncated:
        user_body += f"\n(note: text truncated to {_MAX_TEXT_FOR_MODEL} characters for the model)\n"

    ai_meta: dict[str, Any] = {
        "outcome": "pending",
        "prompt_version": SEMANTIC_PROMPT_VERSION,
        "schema_version": run.semantic_schema_version,
        "model": model,
        "response_contract": rc_raw,
    }
    # Forensics (temporary): persist exact OpenAI I/O for a specific run.
    forensic_enabled = int(run_id) == 20
    if forensic_enabled:
        ai_meta["forensics"] = {
            "schema_name": schema_name_openai,
            "schema_version": run.semantic_schema_version,
            "prompt_version": SEMANTIC_PROMPT_VERSION,
            "model": model,
            "system_prompt": system_for_model,
            "user_prompt": user_body,
            "parse_diagnostics_json_full": diag,
            "text_truncated_for_model": bool(truncated),
            "max_text_for_model": _MAX_TEXT_FOR_MODEL,
        }

    try:
        data = await _openai_chat_json_schema(
            api_key=key,
            model=model,
            system=system_for_model,
            user_text=user_body,
            schema=schema,
            schema_name=schema_name_openai,
        )
    except httpx.HTTPStatusError as exc:
        resp = exc.response
        body = (resp.text or "")[:1500] if resp is not None else ""
        code = resp.status_code if resp is not None else None
        run.semantic_extract_status = "openai_failed"
        run.parse_response = None if force else run.parse_response
        run.semantic_validation_result = {"ok": False, "issues": [f"OpenAI HTTP {code}: {body[:500]}"]}
        run.pipeline_error = f"Load Lab semantic: OpenAI HTTP error ({code})"
        ai_meta["outcome"] = "openai_http_error"
        ai_meta["http_detail"] = body[:800]
        run.ai_model_output = ai_meta
        run.warnings = base_warnings + [f"[semantic] OpenAI request failed: {run.pipeline_error}"]
        load_lab_review_v3.clear_lab_review_if_no_candidate(run)
        _persist()
        await db.commit()
        await db.refresh(run)
        return run
    except Exception as exc:  # noqa: BLE001
        run.semantic_extract_status = "openai_failed"
        run.parse_response = None if force else run.parse_response
        run.semantic_validation_result = {"ok": False, "issues": [f"OpenAI error: {exc!s}"[:500]]}
        run.pipeline_error = "Load Lab semantic: OpenAI request failed"
        ai_meta["outcome"] = "openai_exception"
        ai_meta["exception"] = str(exc)[:800]
        run.ai_model_output = ai_meta
        run.warnings = base_warnings + [f"[semantic] {str(exc)[:300]}"]
        load_lab_review_v3.clear_lab_review_if_no_candidate(run)
        _persist()
        await db.commit()
        await db.refresh(run)
        return run

    content, usage, cerr = _parse_openai_payload(data)
    ai_meta["usage"] = usage
    ai_meta["raw_response_excerpt"] = json.dumps(data)[:8000]
    if forensic_enabled:
        ai_meta.setdefault("forensics", {})["openai_raw_response_json"] = data
        ai_meta.setdefault("forensics", {})["openai_message_content"] = (content or "")[:50000]
    if cerr or not content:
        run.semantic_extract_status = "openai_failed"
        run.parse_response = None if force else run.parse_response
        run.semantic_validation_result = {"ok": False, "issues": [cerr or "No content in response"]}
        run.pipeline_error = "Load Lab semantic: empty or invalid OpenAI message"
        ai_meta["outcome"] = "openai_bad_message"
        run.ai_model_output = ai_meta
        run.warnings = base_warnings + [f"[semantic] {cerr or 'empty message'}"]
        load_lab_review_v3.clear_lab_review_if_no_candidate(run)
        _persist()
        await db.commit()
        await db.refresh(run)
        return run

    crit: CriticalExtractionV11Root | None = None
    crit_glog: list[str] = []
    model_out: LoadLabSemanticModelOutput | None = None
    try:
        raw_obj = json.loads(content)
        if use_critical_v11:
            coerced_c = coercive_prune_critical_payload(raw_obj)
            crit = CriticalExtractionV11Root.model_validate(coerced_c)
            crit, crit_glog = apply_critical_extraction_v11_guardrails(crit, raw_text=raw_full)
        else:
            coerced = _coerce_model_payload_to_schema(raw_obj)
            model_out = LoadLabSemanticModelOutput.model_validate(coerced)
    except Exception as exc:  # noqa: BLE001
        run.semantic_extract_status = "validation_failed"
        run.parse_response = None
        run.semantic_validation_result = {
            "ok": False,
            "issues": [f"Pydantic validate failed: {exc!s}"[:800]],
            "raw_model_json": content[:12000],
        }
        run.pipeline_error = "Load Lab semantic: model output failed Pydantic validation"
        ai_meta["outcome"] = "pydantic_reject"
        ai_meta["message_content"] = content[:12000]
        if forensic_enabled:
            ai_meta.setdefault("forensics", {})["openai_message_content"] = content[:50000]
        run.ai_model_output = ai_meta
        run.warnings = base_warnings + [f"[semantic] Invalid JSON shape: {exc!s}"[:400]]
        load_lab_review_v3.clear_lab_review_if_no_candidate(run)
        _persist()
        await db.commit()
        await db.refresh(run)
        return run

    if use_critical_v11 and crit is not None:
        ex_map = map_critical_v11_to_extracted_fields(crit)
        crit_warnings = [f"[critical v1.1] guardrail events: {len(crit_glog)}"]
        if truncated:
            crit_warnings.append(f"[semantic] Model input text was truncated to {_MAX_TEXT_FOR_MODEL} characters")
        full_cv = LoadDocumentParseResponse(
            document=LoadParseDocumentMeta(filename=run.filename[:512]),
            extracted=ex_map,
            raw_text=raw_full,
            warnings=crit_warnings,
            field_confidence={},
            context={
                "load_lab_semantic": True,
                "load_lab_response_contract": rc_raw,
                "semantic_prompt_version": SEMANTIC_PROMPT_VERSION,
                "semantic_schema_version": CRITICAL_EXTRACTION_V11_SCHEMA_VERSION,
                "semantic_model": model,
                "load_lab_semantic_mode": mode_cf,
                "critical_extraction_v1_1": crit.model_dump(mode="json"),
                "critical_extraction_v1_1_guardrails": crit_glog,
            },
        )
        det_cv = _deterministic_validate(full_cv)
        if not det_cv["ok"]:
            run.semantic_extract_status = "validation_failed"
            run.parse_response = None
            run.semantic_validation_result = {**det_cv, "candidate_preview": full_cv.model_dump(mode="json")}
            run.pipeline_error = "Load Lab semantic: deterministic validation failed (critical v1.1)"
            ai_meta["outcome"] = "deterministic_failed"
            ai_meta["message_content"] = content[:12000]
            run.ai_model_output = ai_meta
            run.warnings = base_warnings + crit_warnings + [f"[semantic] {x}" for x in det_cv.get("issues", [])]
            load_lab_review_v3.clear_lab_review_if_no_candidate(run)
            _persist()
            await db.commit()
            await db.refresh(run)
            return run
        payload_cv = full_cv.model_dump(mode="json")
        if isinstance(diag, dict):
            d2 = dict(diag)
            d2["critical_extraction_v1_1_guardrails"] = crit_glog
            payload_cv["parse_diagnostics"] = d2
        else:
            payload_cv["parse_diagnostics"] = {"critical_extraction_v1_1_guardrails": crit_glog}
        run.semantic_extract_status = "success"
        run.parse_response = payload_cv
        run.semantic_validation_result = det_cv
        run.pipeline_error = None
        ai_meta["outcome"] = "success"
        ai_meta["message_content"] = content[:12000]
        run.ai_model_output = ai_meta
        run.warnings = base_warnings + crit_warnings
        load_lab_review_v3.attach_lab_review_to_run(run)
        load_lab_review_v3.merge_lab_review_warnings(run, base_warnings + crit_warnings)
        try:
            await record_extraction_field_learning_load_lab_ai_snapshot(
                db, tenant_id=tenant_id, run=run, parse_response=payload_cv
            )
        except Exception:  # noqa: BLE001
            pass
        _persist()
        await db.commit()
        await db.refresh(run)
        return run

    if model_out is None:
        run.semantic_extract_status = "validation_failed"
        run.parse_response = None
        run.pipeline_error = "Load Lab semantic: internal state (no model output)"
        run.warnings = base_warnings
        _persist()
        await db.commit()
        await db.refresh(run)
        return run

    # Filename: prefer run.filename if model diverged slightly
    doc_meta = model_out.document.model_copy(update={"filename": run.filename[:512]})

    merged_ex = model_out.extracted.model_dump(mode="json")
    if reference_merge_pack:
        try:
            merged_ex = merge_structured_references_into_extracted_dict(merged_ex, reference_merge_pack)
        except Exception:
            pass
    extracted_model = StrictExtracted.model_validate(merged_ex)

    full = LoadDocumentParseResponse(
        document=doc_meta,
        extracted=extracted_model,
        raw_text=raw_full,
        warnings=list(model_out.extraction_warnings),
        field_confidence={},
        context={
            "load_lab_semantic": True,
            "load_lab_response_contract": rc_raw,
            "semantic_prompt_version": SEMANTIC_PROMPT_VERSION,
            "semantic_schema_version": run.semantic_schema_version,
            "semantic_model": model,
            "load_lab_semantic_mode": mode_cf,
        },
    )

    payload_before_repairs: dict[str, Any] | None = None
    extracted_before_repairs: dict[str, Any] | None = None
    if forensic_enabled:
        try:
            payload_before_repairs = full.model_dump(mode="json")
            extracted_before_repairs = (
                payload_before_repairs.get("extracted")
                if isinstance(payload_before_repairs.get("extracted"), dict)
                else None
            )
            ai_meta.setdefault("forensics", {})["payload_model_output_before_repairs"] = payload_before_repairs
        except Exception:
            payload_before_repairs = None
            extracted_before_repairs = None

    # Reuse the exact diag packet we built pre-AI (includes broker_directory_matches when available).

    try:
        full = LoadDocumentParseResponse.model_validate(full.model_dump(mode="json"))
    except Exception as exc:  # noqa: BLE001
        run.semantic_extract_status = "validation_failed"
        run.parse_response = None
        run.semantic_validation_result = {
            "ok": False,
            "issues": [f"Full response validation failed: {exc!s}"[:800]],
        }
        run.pipeline_error = "Load Lab semantic: assembled candidate failed validation"
        ai_meta["outcome"] = "assemble_failed"
        ai_meta["message_content"] = content[:12000]
        run.ai_model_output = ai_meta
        run.warnings = base_warnings + [f"[semantic] Assemble failed: {exc!s}"[:400]]
        load_lab_review_v3.clear_lab_review_if_no_candidate(run)
        _persist()
        await db.commit()
        await db.refresh(run)
        return run

    det = _deterministic_validate(full)
    sem_warnings = [f"[semantic] {w}" for w in model_out.extraction_warnings]
    if truncated:
        sem_warnings.append("[semantic] Model input text was truncated for token limits")

    if not det["ok"]:
        run.semantic_extract_status = "validation_failed"
        run.parse_response = None
        run.semantic_validation_result = {**det, "candidate_preview": full.model_dump(mode="json")}
        run.pipeline_error = "Load Lab semantic: deterministic validation failed"
        ai_meta["outcome"] = "deterministic_failed"
        ai_meta["message_content"] = content[:12000]
        run.ai_model_output = ai_meta
        run.warnings = base_warnings + sem_warnings + [f"[semantic] {x}" for x in det["issues"]]
        load_lab_review_v3.clear_lab_review_if_no_candidate(run)
        _persist()
        await db.commit()
        await db.refresh(run)
        return run

    ai_extracted_snapshot: dict[str, Any] | None = None
    email_before_post_ai_guardrails: str | None = None
    try:
        ai_extracted_snapshot = model_out.extracted.model_dump(mode="json")
        dump_pre = full.model_dump(mode="json")
        extr_pre = dump_pre.get("extracted") if isinstance(dump_pre.get("extracted"), dict) else {}
        evp = extr_pre.get("broker_contact_email_snapshot")
        email_before_post_ai_guardrails = evp.strip() if isinstance(evp, str) and evp.strip() else None
    except Exception:
        ai_extracted_snapshot = None
        email_before_post_ai_guardrails = None

    # Phase 2: post-AI guardrails (skipped in pure_ai / ai_validate_only modes).
    if mode_cf == "guarded":
        try:
            if diag is not None and isinstance(payload := full.model_dump(mode="json"), dict):
                ex = payload.get("extracted") if isinstance(payload.get("extracted"), dict) else None
                if ex is None:
                    raise RuntimeError("missing extracted block")
                chosen = (ex.get("broker_name_snapshot") or "").strip()
                doc_name = (_best_ranked_document_level_broker(diag, raw_text=payload.get("raw_text")) or "").strip() or None

                pm = diag.get("party_mentions") if isinstance(diag.get("party_mentions"), list) else []
                stop_names = {
                    m.get("name")
                    for m in pm
                    if isinstance(m, dict)
                    and isinstance(m.get("name"), str)
                    and m.get("is_stop_level") is True
                    and m.get("name").strip()
                }
                review_flags = diag.get("review_flags") if isinstance(diag.get("review_flags"), list) else []
                warnings_out = list(payload.get("warnings") or [])
                field_conf = (
                    payload.get("field_confidence")
                    if isinstance(payload.get("field_confidence"), dict)
                    else {}
                )

                # Hard MC-over-customs rule: if chosen broker is customs-labeled but we have MC/DOT grounded doc-level broker,
                # do not collapse customs into booking broker.
                chosen_labels = _party_label_for_name(diag, chosen) if chosen else set()
                doc_labels = _party_label_for_name(diag, doc_name) if doc_name else set()
                has_mc_doc_match = False
                if isinstance(diag.get("broker_directory_matches"), list):
                    has_mc_doc_match = any(
                        isinstance(rec, dict)
                        and rec.get("matched_by") in ("mc", "dot")
                        and isinstance(rec.get("broker_display"), str)
                        and doc_name
                        and rec.get("broker_display").strip().casefold() == doc_name.strip().casefold()
                        for rec in diag["broker_directory_matches"]
                    )

                if doc_name and chosen and chosen.strip().casefold() != doc_name.strip().casefold():
                    # Document-over-local: stop-level choice loses to best-ranked doc-level.
                    if chosen in stop_names:
                        review_flags = list(review_flags) + [
                            {
                                "id": "document_over_local_broker_conflict",
                                "severity": "warning",
                                "detail": f"Model chose broker_name_snapshot={chosen!r} (stop-level); ranked document-level candidate={doc_name!r}.",
                            }
                        ]
                        ex["broker_name_snapshot"] = doc_name
                        warnings_out.append(
                            "[review] Document-level broker identity conflicted with stop-level broker label; chose best-ranked document-level candidate."
                        )
                        field_conf = {**field_conf, "broker_name_snapshot": "low"}

                    # Document-identity ranking override: if model picked a "Broker:" labeled header party but
                    # our ranked document-level candidate is different, prefer the ranked one and require review.
                    if ("broker" in {x.casefold() for x in chosen_labels}) and (chosen not in stop_names):
                        review_flags = list(review_flags) + [
                            {
                                "id": "document_identity_vs_broker_label_conflict",
                                "severity": "warning",
                                "detail": f"Model chose broker_name_snapshot={chosen!r} (broker-labeled); ranked document-level candidate={doc_name!r}.",
                            }
                        ]
                        ex["broker_name_snapshot"] = doc_name
                        summary = (
                            f"Chose {doc_name} because document-level identity / ranked broker evidence outweighed "
                            f"a conflicting broker-labeled mention for {chosen}."
                        )
                        warnings_out.append("[review] " + summary)
                        if isinstance(diag, dict):
                            diag["broker_resolution_summary"] = summary
                        field_conf = {**field_conf, "broker_name_snapshot": "low"}

                    # MC-over-customs: customs-labeled booking broker loses to MC/DOT grounded doc-level broker.
                    if has_mc_doc_match and any("custom" in x.casefold() for x in chosen_labels):
                        review_flags = list(review_flags) + [
                            {
                                "id": "mc_over_customs_broker_override",
                                "severity": "warning",
                                "detail": f"Chosen booking broker {chosen!r} had customs-like labels {sorted(chosen_labels)!r}; overriding to MC/DOT-grounded {doc_name!r}.",
                            }
                        ]
                        # Preserve customs candidate separately if empty.
                        if not (ex.get("customs_broker_name") or "").strip():
                            ex["customs_broker_name"] = chosen
                        ex["broker_name_snapshot"] = doc_name
                        warnings_out.append(
                            "[review] Customs-labeled party was not used as booking broker; chose MC/DOT-grounded document-level broker instead."
                        )
                        field_conf = {**field_conf, "broker_name_snapshot": "low", "customs_broker_name": "low"}

                # Numeric gating on canonical reference mapping.
                ex2, ref_flags, ref_warnings = _numeric_gating_on_reference(extracted=ex, diag=diag)
                if ref_flags:
                    review_flags = list(review_flags) + ref_flags
                if ref_warnings:
                    warnings_out.extend(ref_warnings)
                ex = ex2
                if any(isinstance(f, dict) and f.get("id") == "decimal_reference_suspicious" for f in ref_flags):
                    field_conf = {**field_conf, "broker_load_reference": "low"}

                # Reference-role ranking (EL/Freight Bill/PO/etc.)
                ex3, rr_flags, rr_warnings = _apply_reference_role_ranking(extracted=ex, diag=diag)
                if rr_flags:
                    review_flags = list(review_flags) + rr_flags
                if rr_warnings:
                    warnings_out.extend(rr_warnings)
                ex = ex3

                # Cleanup mapping hazards: trailer fields + temperature labels + appointment normalization.
                ex4, fc4, w4 = _cleanup_trailer_and_temp_fields(ex)
                if w4:
                    warnings_out.extend(w4)
                if fc4:
                    field_conf = {**field_conf, **fc4}
                ex = ex4
                if isinstance(ex.get("stops"), list):
                    norm_stops, _fc_s, w_s = _normalize_stop_appointments(ex["stops"])
                    ex["stops"] = norm_stops
                    if w_s:
                        warnings_out.extend(w_s)

                # Broker display normalization (grounded display preferred; otherwise conservative normalization).
                ex5, fc5, w5 = _apply_broker_display_name_normalization(extracted=ex, diag=diag)
                if w5:
                    warnings_out.extend(w5)
                if fc5:
                    field_conf = {**field_conf, **fc5}
                ex = ex5

                ex6, fl_auth, w_auth, fc_auth = _apply_broker_authority_context_repair(
                    extracted=ex,
                    diag=diag,
                    broker_name=(ex.get("broker_name_snapshot") or "").strip(),
                )
                ex = ex6
                if fl_auth:
                    review_flags = list(review_flags) + fl_auth
                if w_auth:
                    warnings_out.extend(w_auth)
                if fc_auth:
                    field_conf = {**field_conf, **fc_auth}

                diag["review_flags"] = review_flags
                payload["extracted"] = ex
                payload["warnings"] = warnings_out
                payload["field_confidence"] = field_conf
                full = LoadDocumentParseResponse.model_validate(payload)
        except Exception:
            pass

    if forensic_enabled and isinstance(ai_meta.get("forensics"), dict):
        try:
            final_payload = full.model_dump(mode="json")
            final_ex = final_payload.get("extracted") if isinstance(final_payload.get("extracted"), dict) else None
            changes: dict[str, Any] = {}
            if isinstance(extracted_before_repairs, dict) and isinstance(final_ex, dict):
                for k, v in final_ex.items():
                    if extracted_before_repairs.get(k) != v:
                        changes[k] = {"before": extracted_before_repairs.get(k), "after": v}
            ai_meta["forensics"]["payload_after_repairs"] = final_payload
            ai_meta["forensics"]["extracted_field_changes"] = changes
        except Exception:
            pass

    run.semantic_extract_status = "success"
    payload = full.model_dump(mode="json")
    if diag is not None:
        try:
            ex_fin = payload.get("extracted") if isinstance(payload.get("extracted"), dict) else {}
            pkg = run.normalized_package if isinstance(run.normalized_package, dict) else None
            doms = diag.get("broker_match_domains") if isinstance(diag.get("broker_match_domains"), list) else []
            email_diag = await build_broker_contact_email_parse_diagnostics(
                db,
                tenant_id=tenant_id,
                final_extracted=ex_fin,
                ai_extracted=ai_extracted_snapshot,
                email_before_post_ai_guardrails=email_before_post_ai_guardrails,
                raw_pdf_text=payload.get("raw_text") if isinstance(payload.get("raw_text"), str) else raw_full,
                normalized_package=pkg,
                broker_match_domains=doms,
            )
            diag.update(email_diag)
        except Exception:
            pass
        payload["parse_diagnostics"] = diag
    run.parse_response = payload
    run.semantic_validation_result = det
    run.pipeline_error = None
    ai_meta["outcome"] = "success"
    ai_meta["message_content"] = content[:12000]
    run.ai_model_output = ai_meta
    run.warnings = base_warnings + sem_warnings
    load_lab_review_v3.attach_lab_review_to_run(run)
    load_lab_review_v3.merge_lab_review_warnings(run, base_warnings + sem_warnings)
    try:
        await record_extraction_field_learning_load_lab_ai_snapshot(
            db, tenant_id=tenant_id, run=run, parse_response=payload
        )
    except Exception:  # noqa: BLE001
        pass
    _persist()
    await db.commit()
    await db.refresh(run)
    return run
