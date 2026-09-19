"""Typed validation for Fuel master provider-profile sections.

The master JSON is one configuration artifact (syntax = global). After parse,
each provider block is schema-validated independently so one bad provider
cannot disable otherwise-valid profiles.
"""

from __future__ import annotations

from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PROVIDER_PROFILE_INVALID: Final[str] = "PROVIDER_PROFILE_INVALID"

CONTROL_MATCH_KINDS: Final[frozenset[str]] = frozenset(
    {"field_equals", "line_prefix", "line_equals"}
)
CONTROL_HINT_KINDS: Final[frozenset[str]] = frozenset(
    {"field_equals", "line_prefix", "line_contains"}
)


class FuelMasterProfilesSyntaxError(ValueError):
    """Master ``fuel_provider_profiles.json`` cannot be parsed (global failure)."""


class FuelMasterProfilesEnvelopeError(ValueError):
    """Master JSON parsed but registry envelope is invalid (global failure)."""


class FuelProviderProfileInvalidError(ValueError):
    """Known provider exists in master JSON but its section failed schema validation."""

    def __init__(self, provider_code: str, message: str, *, errors: list[str] | None = None) -> None:
        self.provider_code = (provider_code or "").strip().upper()
        self.errors = list(errors or [])
        super().__init__(message)


class LayoutRecognitionModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    required_anchors: list[str] = Field(min_length=1)
    optional_anchors: list[str] = Field(default_factory=list)
    unrecognized_status: str = "PROVIDER_LAYOUT_UNRECOGNIZED"

    @field_validator("required_anchors", "optional_anchors")
    @classmethod
    def _non_empty_strings(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for item in v:
            text = str(item).strip()
            if not text:
                raise ValueError("anchor strings must be non-empty")
            out.append(text)
        return out


class ControlMatchRuleModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    kind: str
    field: str | None = None
    value: Any = None
    prefixes: list[str] | None = None
    requires_contains: list[str] | None = None

    @field_validator("kind")
    @classmethod
    def _kind_allowed(cls, v: str) -> str:
        kind = str(v or "").strip()
        if kind not in CONTROL_MATCH_KINDS:
            raise ValueError(
                f"unsupported control_match_rules kind {kind!r}; "
                f"allowed={sorted(CONTROL_MATCH_KINDS)}"
            )
        return kind

    @model_validator(mode="after")
    def _shape_for_kind(self) -> ControlMatchRuleModel:
        if self.kind == "field_equals":
            if not str(self.field or "").strip():
                raise ValueError("field_equals requires non-empty field")
            if self.value is None:
                raise ValueError("field_equals requires value")
        if self.kind == "line_prefix":
            if not self.prefixes or not any(str(p).strip() for p in self.prefixes):
                raise ValueError("line_prefix requires non-empty prefixes list")
        if self.kind == "line_equals":
            if not str(self.value or "").strip():
                raise ValueError("line_equals requires non-empty value")
        return self


class ControlTypeHintModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    kind: str
    control_type: str = Field(min_length=1)

    @field_validator("kind")
    @classmethod
    def _kind_allowed(cls, v: str) -> str:
        kind = str(v or "").strip()
        if kind not in CONTROL_HINT_KINDS:
            raise ValueError(
                f"unsupported control_type_hints kind {kind!r}; "
                f"allowed={sorted(CONTROL_HINT_KINDS)}"
            )
        return kind


class RowClassificationModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    transaction_field_markers: list[str] = Field(default_factory=list)
    control_match_rules: list[ControlMatchRuleModel] = Field(default_factory=list)
    unknown_is_review: bool = True
    never_infer_purchase_from_amount_alone: bool = True


class FieldSemanticsModel(BaseModel):
    """Extensible; validates nested mapping types when present."""

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="before")
    @classmethod
    def _mapping_values_are_strings(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        for key in (
            "unit_price_basis_by_currency",
            "quantity_unit_by_currency_fallback",
            "unit_price_basis_when_alias_source_present",
        ):
            nested = data.get(key)
            if nested is None:
                continue
            if not isinstance(nested, dict):
                raise ValueError(f"field_semantics.{key} must be an object")
            for k, v in nested.items():
                if not str(k).strip() or not str(v).strip():
                    raise ValueError(f"field_semantics.{key} entries must be non-empty strings")
        return data


class FuelProviderProfileModel(BaseModel):
    """Schema for one provider section in the master profiles JSON."""

    model_config = ConfigDict(extra="allow")

    provider_code: str = Field(min_length=1)
    profile_version: str = Field(min_length=1)
    display_name: str | None = None
    layout_recognition: LayoutRecognitionModel
    row_classification: RowClassificationModel
    field_aliases: dict[str, str] = Field(default_factory=dict)
    field_semantics: FieldSemanticsModel | None = None
    currency_mappings: dict[str, str] = Field(default_factory=dict)
    tax_labels: dict[str, str] = Field(default_factory=dict)
    product_code_legend: dict[str, str] = Field(default_factory=dict)
    header_aliases: dict[str, str] = Field(default_factory=dict)
    control_type_hints: list[ControlTypeHintModel] = Field(default_factory=list)

    @field_validator("provider_code")
    @classmethod
    def _upper_provider(cls, v: str) -> str:
        code = str(v or "").strip().upper()
        if not code:
            raise ValueError("provider_code is required")
        return code

    @field_validator("profile_version")
    @classmethod
    def _version_required(cls, v: str) -> str:
        text = str(v or "").strip()
        if not text:
            raise ValueError("profile_version is required")
        return text

    @field_validator("field_aliases", "currency_mappings", "tax_labels", "product_code_legend", "header_aliases")
    @classmethod
    def _str_maps(cls, v: dict[str, str]) -> dict[str, str]:
        out: dict[str, str] = {}
        for k, val in (v or {}).items():
            ks = str(k).strip()
            vs = str(val).strip()
            if not ks or not vs:
                raise ValueError("mapping keys/values must be non-empty strings")
            out[ks] = vs
        return out

    @model_validator(mode="before")
    @classmethod
    def _reject_profile_code(cls, data: Any) -> Any:
        if isinstance(data, dict) and "profile_code" in data:
            raise ValueError(
                "profile_code is not allowed; identity is provider_code + profile_version"
            )
        return data


def validate_provider_profile_section(
    section: Any,
    *,
    master_key: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Validate one provider section. Returns (normalized_dict, errors).

    On success errors is empty and dict is the validated payload (as dict).
    Does not raise — caller isolates per provider.
    """
    key = str(master_key or "").strip().upper()
    errors: list[str] = []
    if not key:
        return None, ["master key is empty"]
    if not isinstance(section, dict):
        return None, [f"provider section {key!r} must be a JSON object"]
    try:
        model = FuelProviderProfileModel.model_validate(section)
    except Exception as exc:  # pydantic ValidationError or ValueError
        # Flatten without dumping document content beyond field paths.
        msg = str(exc)
        # Keep diagnosable but avoid huge dumps — truncate.
        if len(msg) > 800:
            msg = msg[:800] + "…"
        return None, [msg]
    if model.provider_code != key:
        return None, [
            f"provider_code mismatch for master key {key!r}: "
            f"section has {model.provider_code!r}"
        ]
    return model.model_dump(mode="python"), errors
