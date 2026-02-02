#!/usr/bin/env python3
"""
TruckERP Database Safety Kernel (v0.2 - dry-run)

Layers present (dry-run only):
- Context Detection
- Policy (Rules) Evaluation
- Environment Sanitization PLAN

NO enforcement
NO database access
NO command execution
"""

import os
import sys
from datetime import datetime, UTC

from tools.safety_kernel.context import detect
from tools.safety_kernel.rules import check
from tools.safety_kernel.env_sanitizer import plan as plan_env


def print_env_sanitized_view():
    print("Environment (sanitized view):")
    found = False
    for key in sorted(os.environ):
        if "DATABASE" in key or key.endswith("_URL") or key.startswith("DB_"):
            found = True
            print(f"  {key}=<hidden>")
    if not found:
        print("  <no *_URL / *DATABASE* / DB_* variables found>")
    print()


def run_status(argv: list[str]):
    detected = detect(argv)
    rule = check(detected.name, detected.tenant_slug)
    env_plan = plan_env(detected.name, detected.tenant_slug)

    print("🛡️ TruckERP Database Safety Kernel")
    print("--------------------------------")
    print("Version: v0.2 (dry-run)")
    print(f"Timestamp: {datetime.now(UTC).isoformat()}")
    print()

    print("Detected intent:")
    print(f"  context     : {detected.name}")
    print(f"  action      : {detected.action or '<none>'}")
    print(f"  tenant_slug : {detected.tenant_slug or '<none>'}")
    print(f"  notes       : {detected.notes}")
    print()

    print("Rule evaluation (dry-run):")
    print(f"  allowed : {rule.allowed}")
    print(f"  reason  : {rule.reason}")
    print()

    print("Env sanitization plan (dry-run):")
    print(f"  would_remove_keys : {len(env_plan.removed_keys)}")
    if env_plan.removed_keys:
        # show up to first 8 only to keep output readable
        for k in env_plan.removed_keys[:8]:
            print(f"    - {k}")
        if len(env_plan.removed_keys) > 8:
            print(f"    ... +{len(env_plan.removed_keys) - 8} more")
    print(f"  would_set_key     : {env_plan.set_key or '<none>'}")
    print(f"  notes             : {env_plan.notes}")
    print()

    print_env_sanitized_view()
    print("Status: OK (no enforcement active)")


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python -m tools.safety_kernel.kernel status")
        print("  python -m tools.safety_kernel.kernel platform <action>")
        print("  python -m tools.safety_kernel.kernel tenant <action> --tenant=<slug>")
        sys.exit(1)

    # v0.2: everything routes to dry-run status for visibility
    run_status(sys.argv)


if __name__ == "__main__":
    main()
