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
from app.schemas.load_document_parse import LoadDocumentParseResponse
from app.schemas.load_lab_semantic import LoadLabSemanticModelOutput
from app.services import load_lab as load_lab_v1
from app.services import load_lab_review as load_lab_review_v3
from app.services.load_lab_diagnostics import build_parse_diagnostics
from app.services.load_lab_grounding import ground_party_mentions_to_brokers

# Contract pins (bump when prompt or JSON shape changes).
SEMANTIC_PROMPT_VERSION = "load_lab_semantic_v2"
SEMANTIC_SCHEMA_VERSION = "load_lab_candidate_truckerjson_v1"

_MAX_TEXT_FOR_MODEL = 100_000
_OPENAI_TIMEOUT_S = 120.0

_ALLOWED_STOP_TYPES = frozenset({"pickup", "delivery", "drop", "other"})

_ORG_SUFFIX_RE = re.compile(r"\\b(inc|llc|ltd|limited|corp|corporation|co\\.|company)\\b", re.IGNORECASE)

_CARRIER_ROLE_CTX_RE = re.compile(r"\\b(carrier name|carrier signature|driver phone|attn:|dispatcher|driver)\\b", re.IGNORECASE)


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
    if re.match(r"^\\d{4,}\\b", n):
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
    if _ORG_SUFFIX_RE.search(str(m.get("name") or "")):
        score += 1
    # Prefer repeated document-level mentions (coarse but stable).
    nm = str(m.get("name") or "").strip()
    if raw_text and nm:
        score += min((raw_text.casefold().count(nm.casefold())), 10)
    return score


def _compute_broker_candidate_matrix(diag: dict[str, Any], *, raw_text: str | None) -> dict[str, Any]:
    """
    Debug-only scoring matrix for booking broker ranking.
    Grounding is a strong positive, but not required to win.
    Carrier-role evidence is a strong negative.
    """
    pm = diag.get("party_mentions") if isinstance(diag.get("party_mentions"), list) else []
    matches = diag.get("broker_directory_matches") if isinstance(diag.get("broker_directory_matches"), list) else []
    grounded_names = {str(m.get("broker_display")).strip().casefold() for m in matches if isinstance(m, dict) and m.get("broker_display")}
    out_rows: list[dict[str, Any]] = []
    for m in pm:
        if not isinstance(m, dict):
            continue
        nm = m.get("name")
        if not isinstance(nm, str) or not nm.strip():
            continue
        name = nm.strip()
        grounding = 8 if name.casefold() in grounded_names else 0
        doc_score = _document_broker_identity_score(m, raw_text=raw_text)
        carrier_pen = _carrier_role_penalty(name, raw_text=raw_text)
        total = grounding + doc_score - carrier_pen
        out_rows.append(
            {
                "name": name,
                "total_score": total,
                "dimensions": {
                    "broker_directory_grounding_score": grounding,
                    "document_broker_identity_score": doc_score,
                    "carrier_role_penalty": carrier_pen,
                },
                "signals": {
                    "is_document_identity_level": m.get("is_document_identity_level"),
                    "is_header_level": m.get("is_header_level"),
                    "is_stop_level": m.get("is_stop_level"),
                    "mention_count": m.get("mention_count"),
                },
            }
        )
    out_rows.sort(key=lambda r: int(r.get("total_score") or 0), reverse=True)
    return {
        "broker_confidence_matrix": out_rows[:15],
        "broker_losing_candidates": out_rows[1:6],
        "broker_confidence_factors": (out_rows[0]["dimensions"] if out_rows else {}),
    }


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
        if kind in ("order_number", "load_number", "order_token"):
            s += 8
        elif kind in ("el_number",):
            s += 6
        elif kind in ("freight_bill_number",):
            s += 5
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
    for k in ("order_number", "order_token", "load_number", "el_number", "freight_bill_number", "po_number", "reference"):
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
    # Debug-only scoring comparison / losing candidates.
    try:
        out.update(_compute_broker_candidate_matrix(diag, raw_text=raw_text))
    except Exception:
        pass
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
        "do not treat weight-like / money-like decimals as primary load references unless label evidence is strong."
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


async def semantic_extract_run(
    db: AsyncSession,
    *,
    tenant_id: int,
    run_id: int,
    force: bool = False,
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

    run.semantic_prompt_version = SEMANTIC_PROMPT_VERSION
    run.semantic_schema_version = SEMANTIC_SCHEMA_VERSION

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
            "schema_version": SEMANTIC_SCHEMA_VERSION,
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
            "schema_version": SEMANTIC_SCHEMA_VERSION,
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
            "schema_version": SEMANTIC_SCHEMA_VERSION,
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

    schema = LoadLabSemanticModelOutput.model_json_schema()
    # Build Phase 2 pre-AI evidence packet (diagnostics + broker directory grounding).
    diag: dict[str, Any] | None = None
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
    except Exception:
        diag = None

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
        "schema_version": SEMANTIC_SCHEMA_VERSION,
        "model": model,
    }
    # Forensics (temporary): persist exact OpenAI I/O for a specific run.
    forensic_enabled = int(run_id) == 20
    if forensic_enabled:
        ai_meta["forensics"] = {
            "schema_name": "load_lab_semantic_extract",
            "schema_version": SEMANTIC_SCHEMA_VERSION,
            "prompt_version": SEMANTIC_PROMPT_VERSION,
            "model": model,
            "system_prompt": _system_prompt(),
            "user_prompt": user_body,
            "parse_diagnostics_json_full": diag,
            "text_truncated_for_model": bool(truncated),
            "max_text_for_model": _MAX_TEXT_FOR_MODEL,
        }

    try:
        data = await _openai_chat_json_schema(
            api_key=key,
            model=model,
            system=_system_prompt(),
            user_text=user_body,
            schema=schema,
            schema_name="load_lab_semantic_extract",
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

    try:
        model_out = LoadLabSemanticModelOutput.model_validate_json(content)
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

    # Filename: prefer run.filename if model diverged slightly
    doc_meta = model_out.document.model_copy(update={"filename": run.filename[:512]})

    full = LoadDocumentParseResponse(
        document=doc_meta,
        extracted=model_out.extracted,
        raw_text=raw_full,
        warnings=list(model_out.extraction_warnings),
        field_confidence={},
        context={
            "load_lab_semantic": True,
            "semantic_prompt_version": SEMANTIC_PROMPT_VERSION,
            "semantic_schema_version": SEMANTIC_SCHEMA_VERSION,
            "semantic_model": model,
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

    # Phase 2: post-AI guardrails. Prefer best-ranked document-level booking broker over stop-level one-offs,
    # and enforce numeric gating for references. These adjustments keep the stable parse contract intact.
    try:
        if diag is not None and isinstance(payload := full.model_dump(mode="json"), dict):
            ex = payload.get("extracted") if isinstance(payload.get("extracted"), dict) else None
            if ex is not None:
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
    _persist()
    await db.commit()
    await db.refresh(run)
    return run
