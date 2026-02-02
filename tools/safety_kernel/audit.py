"""
Audit trail (append-only).

Dry-run only: records kernel invocations and decisions.
"""

from datetime import datetime, UTC
import getpass
import json
import os
from pathlib import Path


AUDIT_LOG_PATH = Path("tools/safety_kernel/audit.log")


def append_event(event: dict) -> None:
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "ts": datetime.now(UTC).isoformat(),
        "user": getpass.getuser(),
        "cwd": os.getcwd(),
        **event,
    }

    with AUDIT_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")
