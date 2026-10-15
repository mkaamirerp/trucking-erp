"""Frozen capability catalogs. Modules export tuples; nothing here mutates another module."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

from app.authz.registry import CAPABILITIES

PROSPECTIVE_GRANTS = frozenset({"admin", "operational", "read"})
CURRENT_CONTRACTS = frozenset(
    {"admin", "full_access_same_as_admin", "member", "ungated"}
)
ENFORCEMENT_APPROVALS = frozenset({"not_required", "owner_required"})


class CatalogError(ValueError):
    """A module catalog broke isolation or disagreed with the shipped registry."""


@dataclass(frozen=True)
class CapabilitySpec:
    module: str
    resource: str
    action: str
    prospective: str
    current_contract: str
    shipped: bool
    note: str = ""
    enforcement_approval: str = "not_required"

    @property
    def pair(self) -> tuple[str, str]:
        return (self.resource, self.action)


@dataclass(frozen=True)
class ModuleCatalog:
    module: str
    prefixes: tuple[str, ...]
    capabilities: tuple[CapabilitySpec, ...]


def compose(
    modules: tuple[ModuleCatalog, ...],
) -> MappingProxyType[tuple[str, str], CapabilitySpec]:
    """Combine module catalogs. Rejects prefix takeover and duplicate capabilities."""
    owned: dict[str, str] = {}
    found: dict[tuple[str, str], CapabilitySpec] = {}
    seen_modules: set[str] = set()
    for catalog in modules:
        if not catalog.module or catalog.module in seen_modules:
            raise CatalogError(f"duplicate or empty module id {catalog.module!r}")
        seen_modules.add(catalog.module)
        if not catalog.prefixes:
            raise CatalogError(f"module {catalog.module} has no resource prefix")
        for prefix in catalog.prefixes:
            if not prefix or prefix in owned and owned[prefix] != catalog.module:
                raise CatalogError(
                    f"module {catalog.module} cannot take prefix {prefix!r} owned by {owned.get(prefix)!r}"
                )
            owned[prefix] = catalog.module
        for spec in catalog.capabilities:
            _check_spec(catalog, spec)
            if spec.pair in found:
                owner = found[spec.pair].module
                raise CatalogError(
                    f"module {catalog.module} cannot redefine {spec.resource}/{spec.action} owned by {owner}"
                )
            found[spec.pair] = spec
    shipped = {pair for pair, spec in found.items() if spec.shipped}
    if shipped != set(CAPABILITIES):
        raise CatalogError(
            "shipped capability set must match the Phase 0 registry exactly"
        )
    return MappingProxyType(found)


def _check_spec(catalog: ModuleCatalog, spec: CapabilitySpec) -> None:
    if spec.module != catalog.module:
        raise CatalogError(
            f"module {catalog.module} cannot declare a {spec.module} capability"
        )
    if spec.prospective not in PROSPECTIVE_GRANTS:
        raise CatalogError(f"invalid prospective grant on {spec.pair}")
    if spec.current_contract not in CURRENT_CONTRACTS:
        raise CatalogError(f"invalid current contract on {spec.pair}")
    if spec.enforcement_approval not in ENFORCEMENT_APPROVALS:
        raise CatalogError(f"invalid enforcement approval on {spec.pair}")
    if not any(spec.resource.startswith(prefix) for prefix in catalog.prefixes):
        raise CatalogError(
            f"module {catalog.module} cannot own {spec.resource}/{spec.action}"
        )
    if not spec.resource or not spec.action or "." not in spec.resource:
        raise CatalogError(f"malformed capability {spec.pair}")
