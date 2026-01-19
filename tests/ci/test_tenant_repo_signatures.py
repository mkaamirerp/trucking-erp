import ast
from pathlib import Path

# Adjust if your tenant repos live elsewhere
CANDIDATE_DIRS = [
    Path("app/repos/tenant"),
    Path("tenant_api/repos"),
]

IGNORE_METHODS = {"__init__", "__repr__", "__str__"}

def iter_py_files(base: Path):
    if not base.exists():
        return
    for p in base.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        yield p

def public_methods_in_classes(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    name = item.name
                    if name in IGNORE_METHODS or name.startswith("_"):
                        continue
                    yield (node.name, item)

def has_tenant_id_arg(func) -> bool:
    args = [a.arg for a in func.args.args]
    return "tenant_id" in args

def test_tenant_repo_methods_require_tenant_id():
    checked = 0
    failures = []

    for base in CANDIDATE_DIRS:
        for path in iter_py_files(base):
            src = path.read_text(encoding="utf-8")
            tree = ast.parse(src, filename=str(path))

            for cls_name, func in public_methods_in_classes(tree):
                checked += 1
                if not has_tenant_id_arg(func):
                    failures.append(f"{path}:{func.lineno} {cls_name}.{func.name} missing tenant_id arg")

    # If repo dir isn't present yet, don't fail CI.
    if checked == 0:
        return

    assert not failures, "Tenant repo signature violations:\n" + "\n".join(failures)
