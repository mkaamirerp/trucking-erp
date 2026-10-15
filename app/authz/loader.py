"""Validate and load the static Phase 0 policy. Not called from application startup."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.authz.catalog import CAPABILITY_PAIRS
from app.authz.registry import (
    ADMIN_ROLES,
    CAPABILITIES,
    KNOWN_ROLES,
    POLICY_VERSION,
)

_PACKAGE_DIR = Path(__file__).resolve().parent
MODEL_PATH = _PACKAGE_DIR / "casbin" / "model.conf"
POLICY_PATH = _PACKAGE_DIR / "casbin" / "policy.csv"

_VERSION_RE = re.compile(r"#\s*policy_version:\s*(\d+)\s*$")
_TENANT_DOM_RE = re.compile(r"^[1-9][0-9]*$")
_EFFECTS = frozenset({"allow", "deny"})
_SECTION_RE = re.compile(r"^\[([A-Za-z0-9_]+)\]$")

# Complete Phase 0 model. Section order, names, and the single definition in each
# section are the contract. Whitespace is normalized; comments are not definitions.
_APPROVED_MODEL: tuple[tuple[str, str], ...] = (
    ("request_definition", "r = sub, dom, obj, act"),
    ("policy_definition", "p = sub, dom, obj, act, eft"),
    (
        "policy_effect",
        "e = some(where (p.eft == allow)) && !some(where (p.eft == deny))",
    ),
    (
        "matchers",
        'm = r.sub == p.sub && (p.dom == "*" || r.dom == p.dom) && r.obj == p.obj && r.act == p.act',
    ),
)


class PolicyLoadError(Exception):
    """Policy or model failed validation. Callers must not fall open."""


@dataclass(frozen=True)
class PolicyRow:
    subject: str
    domain: str
    resource: str
    action: str
    effect: str
    line: int

    @property
    def key(self) -> tuple[str, str, str, str]:
        return (self.subject, self.domain, self.resource, self.action)


@dataclass(frozen=True)
class LoadedPolicy:
    version: int
    enforcer: object
    model_path: Path
    policy_path: Path
    rows: tuple[PolicyRow, ...]


def load_shipped_policy() -> LoadedPolicy:
    """Load the version-controlled Phase 0 files. Does not attach to FastAPI."""
    return load_policy(MODEL_PATH, POLICY_PATH, shipped=True)


def load_policy(model_path: Path, policy_path: Path, *, shipped: bool) -> LoadedPolicy:
    model_file = Path(model_path)
    policy_file = Path(policy_path)
    model_text = _read_utf8(model_file, "model")
    policy_text = _read_utf8(policy_file, "policy")
    _validate_model_contract(model_text)
    version, rows = parse_policy(policy_text)
    if version != POLICY_VERSION:
        raise PolicyLoadError(
            f"policy version {version} does not match expected {POLICY_VERSION}"
        )
    _validate_rows(rows, shipped=shipped)
    # Construct only after validation. A failure above does not return an enforcer.
    enforcer = _build_enforcer(model_file, policy_file)
    return LoadedPolicy(
        version=version,
        enforcer=enforcer,
        model_path=model_file,
        policy_path=policy_file,
        rows=tuple(rows),
    )


def _read_utf8(path: Path, label: str) -> str:
    try:
        data = path.read_bytes()
    except FileNotFoundError as exc:
        raise PolicyLoadError(f"{label} file missing: {path}") from exc
    except OSError as exc:
        raise PolicyLoadError(f"{label} file unreadable: {path}") from exc
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PolicyLoadError(f"{label} file is not valid UTF-8: {path}") from exc


def parse_policy(text: str) -> tuple[int, list[PolicyRow]]:
    version: int | None = None
    rows: list[PolicyRow] = []
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            match = _VERSION_RE.match(line)
            if match:
                if version is not None:
                    raise PolicyLoadError(f"duplicate policy_version at line {line_no}")
                version = int(match.group(1))
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 6 or parts[0] != "p":
            raise PolicyLoadError(f"malformed policy row at line {line_no}")
        _, subject, domain, resource, action, effect = parts
        if subject not in KNOWN_ROLES:
            raise PolicyLoadError(f"unknown role {subject!r} at line {line_no}")
        if domain != "*" and _TENANT_DOM_RE.match(domain) is None:
            raise PolicyLoadError(f"invalid policy domain {domain!r} at line {line_no}")
        if (resource, action) not in CAPABILITY_PAIRS:
            raise PolicyLoadError(
                f"unknown capability {resource}/{action} at line {line_no}"
            )
        if effect not in _EFFECTS:
            raise PolicyLoadError(f"invalid effect {effect!r} at line {line_no}")
        rows.append(
            PolicyRow(
                subject=subject,
                domain=domain,
                resource=resource,
                action=action,
                effect=effect,
                line=line_no,
            )
        )
    if version is None:
        raise PolicyLoadError("missing policy_version header")
    return version, rows


def _normalize_model_line(line: str) -> str:
    return " ".join(line.split())


def _validate_model_contract(text: str) -> None:
    """Require the approved sections and their single definitions, nothing else."""
    approved = {name: _normalize_model_line(definition) for name, definition in _APPROVED_MODEL}
    expected_order = [name for name, _ in _APPROVED_MODEL]
    found: dict[str, list[str]] = {}
    order: list[str] = []
    current: str | None = None

    for line_no, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith(";"):
            continue
        header = _SECTION_RE.match(stripped)
        if header:
            name = header.group(1)
            if name not in approved:
                raise PolicyLoadError(f"unexpected model section [{name}] at line {line_no}")
            if name in found:
                raise PolicyLoadError(f"duplicate model section [{name}] at line {line_no}")
            current = name
            found[name] = []
            order.append(name)
            continue
        if current is None:
            raise PolicyLoadError(f"malformed model structure at line {line_no}")
        found[current].append(_normalize_model_line(stripped))

    if order != expected_order:
        raise PolicyLoadError("model sections do not match the approved Phase 0 model")
    for name, definition in approved.items():
        definitions = found.get(name, [])
        if definitions != [definition]:
            raise PolicyLoadError(
                f"model section [{name}] does not match the approved definition"
            )


def _validate_rows(rows: list[PolicyRow], *, shipped: bool) -> None:
    seen: set[tuple[str, str, str, str, str]] = set()
    effects_for_key: dict[tuple[str, str, str, str], set[str]] = {}
    for row in rows:
        identity = (*row.key, row.effect)
        if identity in seen:
            raise PolicyLoadError(f"duplicate policy row at line {row.line}")
        seen.add(identity)
        effects_for_key.setdefault(row.key, set()).add(row.effect)
    if not shipped:
        return
    if any(row.effect != "allow" for row in rows):
        raise PolicyLoadError("shipped policy may contain allow rows only")
    if any(row.domain != "*" for row in rows):
        raise PolicyLoadError("shipped policy domain must be *")
    if any(row.subject not in ADMIN_ROLES for row in rows):
        raise PolicyLoadError("shipped policy may grant only the four admin roles")
    expected = {
        (role, "*", resource, action)
        for role in ADMIN_ROLES
        for resource, action in CAPABILITIES
    }
    actual = {row.key for row in rows}
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise PolicyLoadError(
            f"shipped policy matrix mismatch missing={missing!r} extra={extra!r}"
        )


def _build_enforcer(model_file: Path, policy_file: Path) -> object:
    try:
        import casbin
    except ImportError as exc:
        raise PolicyLoadError(
            "casbin package is not installed; Phase 0 cannot load policy"
        ) from exc
    try:
        return casbin.Enforcer(str(model_file), str(policy_file))
    except (RuntimeError, ValueError) as exc:
        raise PolicyLoadError(f"casbin rejected policy: {exc}") from exc
