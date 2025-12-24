import re
from datetime import date, datetime
from typing import Optional


_phone_keep = re.compile(r"[^0-9+]+")
_digits_only = re.compile(r"\D+")


def normalize_country_code(value: str) -> str:
    v = (value or "").strip()
    if not v:
        raise ValueError("country_code is required")
    if not v.startswith("+"):
        v = "+" + v
    if not re.fullmatch(r"\+[0-9]{1,4}", v):
        raise ValueError("country_code must look like +1, +52, +44")
    return v


def normalize_phone_number(value: str) -> str:
    v = (value or "").strip()
    if not v:
        raise ValueError("phone_number is required")

    # allow user to paste things like (416) 555-1212, 416-555-1212, +1 416 555 1212
    # store digits only (no + here; + lives in country_code)
    v = _phone_keep.sub("", v)  # keep digits and +
    v = v.replace("+", "")      # strip plus if present
    v = _digits_only.sub("", v)

    if not (7 <= len(v) <= 15):
        raise ValueError("phone_number must be 7 to 15 digits after cleanup")
    return v


def parse_date_flexible(value: Optional[str]) -> Optional[date]:
    if value is None:
        return None
    v = str(value).strip()
    if not v:
        return None

    # Accept ISO first
    try:
        return date.fromisoformat(v)
    except Exception:
        pass

    # Accept MM/DD/YYYY
    for fmt in ("%m/%d/%Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(v, fmt).date()
        except Exception:
            pass

    # Accept exactly 8 digits MMDDYYYY
    if re.fullmatch(r"\d{8}", v):
        mm = int(v[0:2])
        dd = int(v[2:4])
        yyyy = int(v[4:8])
        return date(yyyy, mm, dd)

    # Reject ambiguous formats like 2312025 (7 digits) or DDMMYYYY without separators
    raise ValueError("Invalid date format. Use YYYY-MM-DD, MM/DD/YYYY, or 8 digits MMDDYYYY.")
def normalize_name(value: str) -> str:
    # Trim, collapse multiple spaces, keep letters/numbers/common name chars
    v = (value or "").strip()
    if not v:
        raise ValueError("name is required")
    v = " ".join(v.split())  # collapse whitespace
    if len(v) > 100:
        raise ValueError("name must be at most 100 characters")
    return v
