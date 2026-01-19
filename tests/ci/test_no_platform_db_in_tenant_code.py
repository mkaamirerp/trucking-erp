from pathlib import Path

TENANT_DIRS = [
    Path("app/routers/tenant"),
    Path("app/services/tenant"),
    Path("app/repos/tenant"),
    Path("tenant_api"),
]

BAD_STRINGS = [
    "from app.deps.db import get_db",
    "Depends(get_db",
    "PLATFORM_DATABASE_URL",
]

def iter_existing_files():
    for d in TENANT_DIRS:
        if not d.exists():
            continue
        for p in d.rglob("*.py"):
            yield p

def test_tenant_code_does_not_reference_platform_db():
    violations = []
    for p in iter_existing_files():
        txt = p.read_text(encoding="utf-8", errors="ignore")
        for s in BAD_STRINGS:
            if s in txt:
                violations.append(f"{p} contains forbidden reference: {s}")
    assert not violations, "Tenant code references platform DB deps:\n" + "\n".join(violations)
