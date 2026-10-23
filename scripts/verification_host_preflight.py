#!/usr/bin/env python3
"""Fail-closed verification preflight. Exit 78 when verification must not run."""

from __future__ import annotations

import sys

_REPO_ROOT = __file__.rsplit("/scripts/", 1)[0]
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.core.verification_host_guard import (  # noqa: E402
    VerificationHostDenied,
    assert_disposable_verification_host,
    collect_verification_denial_reasons,
)

EXIT_DENIED = 78


def main() -> int:
    try:
        assert_disposable_verification_host()
    except VerificationHostDenied as exc:
        print(f"VERIFICATION_PREFLIGHT_DENIED: {exc}", file=sys.stderr)
        for reason in collect_verification_denial_reasons():
            print(f"  - {reason}", file=sys.stderr)
        return EXIT_DENIED
    print("VERIFICATION_PREFLIGHT_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
