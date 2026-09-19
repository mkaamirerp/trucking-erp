"""Generic Fuel provider profile loader and applicators.

Architecture lock: ONE Fuel parser/handoff/validator + ONE master provider
profile JSON (``app/contracts/fuel_provider_profiles.json``) with one current
evidenced section per provider (``BVD``, ``NATIONWIDE``, …).

Provider-specific source labels live in profile JSON only — never hardcoded in
this module (no BVD ``CUR`` / ``Billed``, no Nationwide ``Currency`` literals).
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from app.schemas.fuel_provider_profile import (
    PROVIDER_PROFILE_INVALID,
    FuelMasterProfilesEnvelopeError,
    FuelMasterProfilesSyntaxError,
    FuelProviderProfileInvalidError,
    validate_provider_profile_section,
)
from app.services.fuel_ai_contract import (
    AI_FORBIDDEN_AUTHORITY_FIELDS,
    LAYOUT_UNRECOGNIZED,
    contract_ai_forbidden_fields,
)
from app.services.fuel_canonical import EVIDENCED_CURRENCY_CANONICAL, classify_currency

MASTER_PROFILES_PATH: Final[Path] = (
    Path(__file__).resolve().parents[1] / "contracts" / "fuel_provider_profiles.json"
)

# Required top-level provider keys in the master JSON (current evidenced set).
MASTER_PROVIDER_KEYS: Final[frozenset[str]] = frozenset({"BVD", "NATIONWIDE"})

FORBIDDEN_PROVIDER_PARSER_MODULE_SUFFIXES: Final[tuple[str, ...]] = (
    "_bvd_parser.py",
    "_nationwide_parser.py",
    "_wex_parser.py",
    "_comdata_parser.py",
    "bvd_parser.py",
    "nationwide_parser.py",
)

STRUCTURED_BLOCKED = "BLOCKED_BY_SOURCE_EVIDENCE"
REASON_AMOUNT_ONLY = "INSUFFICIENT_TRANSACTION_EVIDENCE_AMOUNT_ONLY"
REASON_NO_MATCH = "ROW_ROLE_UNCLASSIFIED"
REASON_CONTROL_MATCH = "CONTROL_RULE_MATCHED"
REASON_TRANSACTION_MARKERS = "TRANSACTION_FIELD_MARKERS_PRESENT"
LAYOUT_AMBIGUOUS = "PROVIDER_LAYOUT_AMBIGUOUS"

_WS_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class ProviderProfileValidationStatus:
    provider_code: str
    status: str  # VALID | PROVIDER_PROFILE_INVALID
    errors: tuple[str, ...] = ()

    @property
    def is_valid(self) -> bool:
        return self.status == "VALID"


@dataclass(frozen=True)
class ProviderProfileRegistry:
    """Result of parsing + independently validating each provider section."""

    valid_profiles: dict[str, dict[str, Any]]
    invalid_statuses: dict[str, ProviderProfileValidationStatus]
    expected_keys: frozenset[str] | None = None

    def known_codes(self) -> list[str]:
        return sorted(set(self.valid_profiles) | set(self.invalid_statuses))

    def valid_codes(self) -> list[str]:
        return sorted(self.valid_profiles.keys())


@dataclass(frozen=True)
class LayoutMatchResult:
    status: str  # RECOGNIZED | PROVIDER_LAYOUT_UNRECOGNIZED | REVIEW
    matched_anchors: tuple[str, ...]
    missing_required_anchors: tuple[str, ...]
    provider_code: str
    reason: str | None = None

    @property
    def requires_review(self) -> bool:
        return self.status in {LAYOUT_UNRECOGNIZED, "REVIEW", LAYOUT_AMBIGUOUS}


@dataclass(frozen=True)
class ProfileResolveResult:
    status: str  # RECOGNIZED | PROVIDER_LAYOUT_UNRECOGNIZED | PROVIDER_LAYOUT_AMBIGUOUS
    profile: dict[str, Any] | None
    matched_profile_versions: tuple[str, ...]
    reason: str | None = None

    @property
    def requires_review(self) -> bool:
        return self.status != "RECOGNIZED"


@dataclass(frozen=True)
class RowRoleResult:
    role: str  # TRANSACTION | CONTROL | UNKNOWN
    reason: str | None = None

    @property
    def requires_review(self) -> bool:
        return self.role == "UNKNOWN"


def provider_profiles_master_path() -> Path:
    return MASTER_PROFILES_PATH


def normalize_layout_text(text: str) -> str:
    """Case-fold + collapse whitespace. No fuzzy semantic matching."""
    return _WS_RE.sub(" ", (text or "").casefold()).strip()


@lru_cache(maxsize=4)
def load_master_provider_profiles() -> dict[str, Any]:
    """Load the single master Fuel provider-profiles document.

    Top-level keys are provider codes (exactly the evidenced set, currently
    ``BVD`` and ``NATIONWIDE``). Each value is that provider's current profile
    with ``provider_code`` + ``profile_version`` identity (no ``profile_code``).
    """
    path = MASTER_PROFILES_PATH
    if not path.is_file():
        raise FileNotFoundError(f"Fuel provider profiles master not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"Master provider profiles must be a JSON object: {path}")
    keys = {str(k).strip().upper() for k in data.keys()}
    if keys != set(MASTER_PROVIDER_KEYS):
        raise ValueError(
            "Master fuel_provider_profiles.json must contain exactly "
            f"{sorted(MASTER_PROVIDER_KEYS)}; found {sorted(keys)}"
        )
    out: dict[str, Any] = {}
    for raw_key, section in data.items():
        provider = str(raw_key).strip().upper()
        if not isinstance(section, dict):
            raise TypeError(f"Provider section {provider!r} must be a JSON object")
        if "profile_code" in section:
            raise ValueError(
                f"Provider {provider!r} must not include profile_code; "
                "identity is provider_code + profile_version"
            )
        section_provider = str(section.get("provider_code") or "").strip().upper()
        if section_provider != provider:
            raise ValueError(
                f"provider_code mismatch for master key {provider!r}: "
                f"section has {section.get('provider_code')!r}"
            )
        version = str(section.get("profile_version") or "").strip()
        if not version:
            raise ValueError(f"Provider {provider!r} requires profile_version")
        out[provider] = section
    return out


def _clear_profile_caches() -> None:
    load_master_provider_profiles.cache_clear()


def list_master_provider_codes() -> list[str]:
    return sorted(load_master_provider_profiles().keys())


def get_provider_profile_for_code(provider_code: str) -> dict[str, Any] | None:
    """Select the current evidenced profile section for a provider code.

    Catalog/metadata helper — for document intake prefer
    ``resolve_provider_profile_for_document`` so layout anchors are checked.
    Unknown provider → None.
    """
    want = (provider_code or "").strip().upper()
    if not want:
        return None
    master = load_master_provider_profiles()
    section = master.get(want)
    return copy.deepcopy(section) if section is not None else None


def load_provider_profile(provider_code: str) -> dict[str, Any]:
    """Load the current profile for a provider code from the master JSON.

    Accepts only provider codes (``BVD``, ``NATIONWIDE``). Legacy statement_v1
    profile identities are not supported.
    """
    code = (provider_code or "").strip()
    if not code:
        raise ValueError("provider_code is required")
    profile = get_provider_profile_for_code(code)
    if profile is None:
        raise FileNotFoundError(
            f"Fuel provider profile not found in master JSON: {code!r} "
            f"({MASTER_PROFILES_PATH})"
        )
    return profile


def list_provider_profile_codes() -> list[str]:
    """Provider codes with a current profile in the master JSON."""
    return list_master_provider_codes()


def list_provider_profiles_for_provider(provider_code: str) -> list[dict[str, Any]]:
    """Current evidenced profile(s) for a provider from the master JSON.

    Today: exactly one current profile per provider.
    """
    profile = get_provider_profile_for_code(provider_code)
    return [profile] if profile is not None else []


def _haystack_from_pages(pages: Sequence[Any] | None) -> str:
    if not pages:
        return ""
    parts: list[str] = []
    for item in pages:
        if isinstance(item, Mapping):
            parts.append(str(item.get("text") or ""))
        else:
            parts.append(str(item or ""))
    return "\n".join(parts)


def match_provider_layout(
    profile: Mapping[str, Any],
    *,
    page_texts: Sequence[Any] | None = None,
    document_text: str | None = None,
) -> LayoutMatchResult:
    """Deterministic anchor match with presentation normalization."""
    layout = profile.get("layout_recognition") or {}
    required = [str(a) for a in (layout.get("required_anchors") or [])]
    text = document_text if document_text is not None else _haystack_from_pages(page_texts)
    norm_text = normalize_layout_text(text)
    matched: list[str] = []
    missing: list[str] = []
    for anchor in required:
        if normalize_layout_text(anchor) in norm_text:
            matched.append(anchor)
        else:
            missing.append(anchor)
    provider = str(profile.get("provider_code") or "").strip().upper()
    if not required:
        return LayoutMatchResult(
            status="REVIEW",
            matched_anchors=(),
            missing_required_anchors=(),
            provider_code=provider,
            reason="NO_LAYOUT_ANCHORS_CONFIGURED",
        )
    if missing:
        status = str(layout.get("unrecognized_status") or LAYOUT_UNRECOGNIZED)
        return LayoutMatchResult(
            status=status,
            matched_anchors=tuple(matched),
            missing_required_anchors=tuple(missing),
            provider_code=provider,
            reason="REQUIRED_ANCHORS_MISSING",
        )
    return LayoutMatchResult(
        status="RECOGNIZED",
        matched_anchors=tuple(matched),
        missing_required_anchors=(),
        provider_code=provider,
        reason=None,
    )


def resolve_provider_profile_for_document(
    provider_code: str,
    *,
    page_texts: Sequence[Any] | None = None,
    document_text: str | None = None,
) -> ProfileResolveResult:
    """Provider selected → check current profile layout anchors.

    Safe outcomes:
    * exactly one recognized layout → that profile
    * zero matches → ``PROVIDER_LAYOUT_UNRECOGNIZED`` / REVIEW
    * multiple matches (future multi-layout) → ambiguous / REVIEW

    Never silently picks an unmatched profile.
    """
    candidates = list_provider_profiles_for_provider(provider_code)
    if not candidates:
        return ProfileResolveResult(
            status=LAYOUT_UNRECOGNIZED,
            profile=None,
            matched_profile_versions=(),
            reason="NO_PROFILES_FOR_PROVIDER",
        )
    recognized: list[dict[str, Any]] = []
    for profile in candidates:
        match = match_provider_layout(
            profile, page_texts=page_texts, document_text=document_text
        )
        if match.status == "RECOGNIZED":
            recognized.append(profile)
    versions = tuple(str(p.get("profile_version") or "") for p in recognized)
    if len(recognized) == 1:
        return ProfileResolveResult(
            status="RECOGNIZED",
            profile=recognized[0],
            matched_profile_versions=versions,
            reason=None,
        )
    if len(recognized) == 0:
        return ProfileResolveResult(
            status=LAYOUT_UNRECOGNIZED,
            profile=None,
            matched_profile_versions=(),
            reason="ZERO_LAYOUT_MATCHES",
        )
    return ProfileResolveResult(
        status=LAYOUT_AMBIGUOUS,
        profile=None,
        matched_profile_versions=versions,
        reason="MULTIPLE_LAYOUT_MATCHES",
    )


def profile_currency_map(profile: Mapping[str, Any] | None) -> dict[str, str]:
    """Profile evidenced mappings win when present; else shared evidenced map."""
    out = dict(EVIDENCED_CURRENCY_CANONICAL)
    if profile:
        for raw, canon in (profile.get("currency_mappings") or {}).items():
            out[str(raw).strip().upper()] = str(canon).strip().upper()
    return out


def apply_currency_mapping(
    currency_raw: str | None,
    *,
    profile: Mapping[str, Any] | None = None,
) -> tuple[str | None, str | None]:
    preserved, shared = classify_currency(currency_raw)
    if preserved is None:
        return None, None
    mapped = profile_currency_map(profile).get(preserved.upper())
    return preserved, mapped if mapped is not None else shared


def _norm_token(value: Any) -> str:
    return normalize_layout_text(str(value if value is not None else ""))


def _control_rule_matches(
    rule: Mapping[str, Any],
    *,
    provider_raw: Mapping[str, Any] | None,
    line_text: str | None,
) -> bool:
    """Evaluate one deterministic control rule. Never scans arbitrary field values."""
    kind = str(rule.get("kind") or "").strip()
    if kind == "field_equals":
        field = str(rule.get("field") or "")
        if not field or not provider_raw or field not in provider_raw:
            return False
        expected = rule.get("value")
        return _norm_token(provider_raw.get(field)) == _norm_token(expected)
    if kind == "line_prefix":
        # Inspect only the dedicated row/line label text — not provider_raw values.
        line = normalize_layout_text(line_text or "")
        if not line:
            return False
        prefixes = [normalize_layout_text(str(p)) for p in (rule.get("prefixes") or [])]
        requires = [normalize_layout_text(str(p)) for p in (rule.get("requires_contains") or [])]
        if not any(line.startswith(p) for p in prefixes if p):
            return False
        return all(r in line for r in requires if r)
    if kind == "line_equals":
        line = normalize_layout_text(line_text or "")
        expected = normalize_layout_text(str(rule.get("value") or ""))
        return bool(line) and line == expected
    return False


def classify_source_row_role(
    *,
    profile: Mapping[str, Any],
    provider_raw: Mapping[str, Any] | None = None,
    line_text: str | None = None,
) -> RowRoleResult:
    """Return TRANSACTION | CONTROL | UNKNOWN with an explicit reason.

    Control matching uses profile ``control_match_rules`` only (field_equals /
    line_prefix / line_equals). Does not substring-search transaction values.
    """
    rules = profile.get("row_classification") or {}
    control_rules = list(rules.get("control_match_rules") or [])
    # Backward-compatible: migrate legacy control_indicators → line_prefix if present
    # and no control_match_rules yet (should not happen after profile updates).
    if not control_rules and rules.get("control_indicators"):
        control_rules = [
            {"kind": "line_prefix", "prefixes": [str(x)]}
            for x in rules.get("control_indicators") or []
        ]

    for rule in control_rules:
        if isinstance(rule, Mapping) and _control_rule_matches(
            rule, provider_raw=provider_raw, line_text=line_text
        ):
            return RowRoleResult(role="CONTROL", reason=REASON_CONTROL_MATCH)

    txn_fields = [str(x) for x in (rules.get("transaction_field_markers") or [])]
    if provider_raw and txn_fields:
        if all(
            field in provider_raw and provider_raw.get(field) not in (None, "")
            for field in txn_fields
        ):
            return RowRoleResult(role="TRANSACTION", reason=REASON_TRANSACTION_MARKERS)

    if rules.get("never_infer_purchase_from_amount_alone") and _looks_amount_only(provider_raw):
        return RowRoleResult(role="UNKNOWN", reason=REASON_AMOUNT_ONLY)
    return RowRoleResult(role="UNKNOWN", reason=REASON_NO_MATCH)


def _is_money_only_key(key: str) -> bool:
    """Generic money-key heuristic — no provider column vocabulary."""
    k = key.strip().casefold()
    if not k:
        return False
    if k in {"amount", "total", "total_amount", "declared_amount", "declared amount"}:
        return True
    if "amount" in k or "amt" in k:
        return True
    return False


def _looks_amount_only(provider_raw: Mapping[str, Any] | None) -> bool:
    """True when every present key is money-like (amount alone never proves purchase)."""
    if not provider_raw:
        return False
    keys = [str(k) for k in provider_raw.keys()]
    if not keys:
        return False
    return all(_is_money_only_key(k) for k in keys)


def apply_field_aliases(
    provider_raw: Mapping[str, Any],
    *,
    profile: Mapping[str, Any],
    existing: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Map evidenced provider labels → canonical Fuel fields. Preserve provider_raw.

    Operates on canonical keys after alias application. Does not hardcode
    provider source labels such as BVD ``CUR`` / ``Billed``.
    """
    forbidden = contract_ai_forbidden_fields() | AI_FORBIDDEN_AUTHORITY_FIELDS
    aliases: Mapping[str, Any] = profile.get("field_aliases") or {}
    out: dict[str, Any] = dict(existing or {})
    out["provider_raw"] = dict(provider_raw)
    aliased_from: dict[str, str] = {}

    for src_label, target in aliases.items():
        if src_label not in provider_raw:
            continue
        value = provider_raw[src_label]
        if value is None or (isinstance(value, str) and value.strip() == ""):
            continue
        if not isinstance(target, str):
            continue
        if target in forbidden:
            continue
        if out.get(target) is None:
            out[target] = value
            aliased_from[target] = src_label

    semantics = profile.get("field_semantics") or {}

    # Currency: only from canonical currency_raw (populated via profile aliases).
    raw = out.get("currency_raw")
    if raw is not None:
        preserved, canonical = apply_currency_mapping(str(raw), profile=profile)
        if preserved is not None:
            out["currency_raw"] = preserved
        if out.get("currency") is None and canonical is not None:
            out["currency"] = canonical

    # Price basis: profile rules only (no hardcoded source-column names).
    if out.get("unit_price") is not None and out.get("unit_price_basis") is None:
        # 1) when a specific provider_raw key that aliased into unit_price is present
        basis_by_source = semantics.get("unit_price_basis_when_alias_source_present") or {}
        src = aliased_from.get("unit_price")
        if src and src in basis_by_source:
            out["unit_price_basis"] = basis_by_source[src]
        # 2) optional default when unit_price was set from any alias
        elif src and semantics.get("unit_price_basis_when_unit_price_aliased"):
            out["unit_price_basis"] = semantics["unit_price_basis_when_unit_price_aliased"]
        # 3) currency-scoped basis (profile-local; e.g. Nationwide CAD/USD)
        if out.get("unit_price_basis") is None:
            by_ccy = semantics.get("unit_price_basis_by_currency") or {}
            ccy = str(out.get("currency") or out.get("currency_raw") or "").strip().upper()
            if ccy and ccy in by_ccy:
                out["unit_price_basis"] = by_ccy[ccy]

    # Quantity UOM: explicit source wins; profile currency fallback is profile-scoped.
    if out.get("quantity_unit") is None and out.get("quantity") is not None:
        uom_fb = semantics.get("quantity_unit_by_currency_fallback") or {}
        ccy = str(out.get("currency") or out.get("currency_raw") or "").strip().upper()
        if ccy and ccy in uom_fb:
            out["quantity_unit"] = uom_fb[ccy]

    legend = profile.get("product_code_legend") or {}
    code = out.get("product_code_raw") or out.get("product")
    if code is not None and out.get("product_description_raw") is None:
        desc = legend.get(str(code).strip().upper()) or legend.get(str(code).strip())
        if desc:
            out["product_description_raw"] = desc
            if out.get("product") is None:
                out["product"] = desc
        elif out.get("product") is None and out.get("product_code_raw") is None:
            out["product"] = str(code)

    for key in list(out.keys()):
        if key in forbidden:
            out.pop(key, None)

    return out


def suggest_control_type(
    *,
    profile: Mapping[str, Any],
    provider_raw: Mapping[str, Any] | None = None,
    line_text: str | None = None,
) -> str:
    """Map control identity to canonical control_type using profile hints.

    Hints apply to ``line_text`` (normalized) or a named ``provider_raw`` field —
    never to arbitrary transaction value bags.
    """
    hints = profile.get("control_type_hints") or {}
    # New shape: list of {match_kind, ...}
    if isinstance(hints, list):
        for hint in hints:
            if not isinstance(hint, Mapping):
                continue
            kind = str(hint.get("kind") or "line_contains")
            ctype = str(hint.get("control_type") or "UNKNOWN")
            if kind == "field_equals":
                field = str(hint.get("field") or "")
                if (
                    provider_raw
                    and field in provider_raw
                    and _norm_token(provider_raw.get(field)) == _norm_token(hint.get("value"))
                ):
                    return ctype
            elif kind == "line_prefix":
                line = normalize_layout_text(line_text or "")
                for p in hint.get("prefixes") or []:
                    if line.startswith(normalize_layout_text(str(p))):
                        return ctype
            elif kind == "line_contains":
                line = normalize_layout_text(line_text or "")
                needle = normalize_layout_text(str(hint.get("value") or ""))
                if needle and needle in line:
                    return ctype
        return "UNKNOWN"

    # Legacy dict shape: needle → control_type, applied only to line_text.
    if isinstance(hints, Mapping):
        line = normalize_layout_text(line_text or "")
        for needle, ctype in hints.items():
            n = normalize_layout_text(str(needle))
            if n and n in line:
                return str(ctype)
    return "UNKNOWN"


def apply_header_aliases(
    provider_raw: Mapping[str, Any],
    *,
    profile: Mapping[str, Any],
) -> dict[str, Any]:
    aliases: Mapping[str, Any] = profile.get("header_aliases") or {}
    header: dict[str, Any] = {}
    for src, target in aliases.items():
        if src in provider_raw and isinstance(target, str):
            header[target] = provider_raw[src]
    return header


def structured_export_status(profile: Mapping[str, Any]) -> dict[str, Any]:
    block = profile.get("structured_export") or {}
    return {
        "status": str(block.get("status") or STRUCTURED_BLOCKED),
        "reason": block.get("reason"),
        "provider_code": profile.get("provider_code"),
        "profile_version": profile.get("profile_version"),
    }


def assert_no_separate_provider_parser_engines(services_dir: Path | None = None) -> list[str]:
    """Architectural guard: provider profiles must not spawn per-provider parser modules."""
    root = services_dir or (Path(__file__).resolve().parent)
    offenders: list[str] = []
    for path in root.glob("*.py"):
        name = path.name.lower()
        for suffix in FORBIDDEN_PROVIDER_PARSER_MODULE_SUFFIXES:
            if name == suffix or name.endswith(suffix):
                offenders.append(path.name)
    return sorted(set(offenders))


def combined_parser_rule_version(
    *,
    handoff_version: str,
    profile: Mapping[str, Any] | None,
) -> str:
    """Persistable provenance: handoff + provider + profile_version stamp."""
    if not profile:
        return handoff_version
    provider = str(profile.get("provider_code") or "").strip().upper()
    version = str(profile.get("profile_version") or "").strip()
    parts = [handoff_version]
    if provider:
        parts.append(provider)
    if version:
        parts.append(version)
    return "+".join(parts) if len(parts) > 1 else handoff_version


def audit_generic_provider_source_literals() -> list[str]:
    """Return provider-specific source labels that must not appear in this module."""
    text = Path(__file__).read_text(encoding="utf-8")
    cut = text.find("def audit_generic_provider_source_literals")
    check = text[:cut] if cut >= 0 else text
    forbidden_literals = (
        '"CUR"',
        "'CUR'",
        '"Billed"',
        "'Billed'",
        '"Currency"',
        "'Currency'",
        '"Ex-GST',
        "'Ex-GST",
        '"Final AMT"',
        "'Final AMT'",
        '"Auth Code"',
        "'Auth Code'",
    )
    return [lit for lit in forbidden_literals if lit in check]
