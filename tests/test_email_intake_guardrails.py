from __future__ import annotations

import ast
from pathlib import Path

import pytest


def test_email_intake_has_no_forbidden_runtime_strings() -> None:
    """
    Guardrail: email intake must not re-introduce broker/product-specific runtime strings.

    Allowed exception: a single legacy wire token in `email_intake_routing.py` describing a historical routing_reason.
    """
    repo = Path(__file__).resolve().parents[1]
    targets = [
        repo / "app" / "constants" / "email_intake_routing.py",
        repo / "app" / "services" / "email_intake_routing.py",
        repo / "app" / "services" / "email_engine",
        repo / "app" / "services" / "email_threads.py",
        repo / "apps" / "web" / "src" / "utils" / "emailIntakeRoutingReason.ts",
    ]

    forbidden = [
        "tql_pdf",
        "tql_affiliated",
        "fallback_tql",
        "extract_tql_rate_con_hints",
        "guess_broker_load_reference",
        "@tql.com",
        "@tqltrucks.com",
        "@tql.net",
        "total quality logistics",
    ]
    allowed_exact_lines = {
        'LEGACY_EMAIL_INTAKE_AUTO_DIGITAL_PDF_RATE_CONFIRMATION = "auto_tql_digital_pdf_rate_confirmation"'
    }

    def _iter_files(p: Path) -> list[Path]:
        if p.is_dir():
            out: list[Path] = []
            for ext in ("*.py", "*.ts", "*.tsx"):
                out.extend(sorted(p.rglob(ext)))
            return out
        return [p]

    for root in targets:
        for f in _iter_files(root):
            text = f.read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines()
            for idx, line in enumerate(lines, start=1):
                if line.strip() in allowed_exact_lines:
                    continue
                low = line.lower()
                for token in forbidden:
                    assert token not in low, f"forbidden token {token!r} in {f}:{idx}: {line.strip()!r}"


def test_feature_code_imports_product_parser_via_canonical_module() -> None:
    """
    Guardrail: feature code should import the product parser via `load_document_product_parser`,
    not by adding new public entrypoints or importing guarded parser directly.

    This is a lightweight static check to prevent accidental duplication.
    """
    repo = Path(__file__).resolve().parents[1]
    allow_guarded_import_files = {
        repo / "app" / "services" / "load_document_product_parser.py",
        repo / "app" / "services" / "load_document_parse_orchestrator.py",
    }

    for py in (repo / "app").rglob("*.py"):
        if py in allow_guarded_import_files:
            continue
        src = py.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(src)
        except SyntaxError:
            # Not expected, but don't make this guardrail block unrelated failures.
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "app.services.load_document_parse_guarded":
                names = {n.name for n in node.names}
                if "parse_pdf_bytes_to_load_document_response" in names:
                    pytest.fail(
                        f"Import guarded parser directly in feature code: {py}. "
                        "Use app.services.load_document_product_parser instead."
                    )
