from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageEnhance, ImageOps
import zxingcpp

_FIELD_CODES = (
    "DAQ", "DCS", "DAC", "DAD", "DAA",
    "DBA", "DBD", "DBB", "DBC", "DAU",
    "DAG", "DAI", "DAJ", "DAK",
    "DCA", "DCB", "DCD", "DCF", "DCG", "DCK",
    "DDE", "DDF", "DDG",
)

def _parse_date(value: str | None) -> str | None:
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    if len(digits) != 8:
        return None
    formats = ("%Y%m%d", "%m%d%Y", "%d%m%Y")
    for fmt in formats:
        try:
            return datetime.strptime(digits, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _parse_sex(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip().upper()
    if raw in {"1", "M", "MALE"}:
        return "M"
    if raw in {"2", "F", "FEMALE"}:
        return "F"
    if raw in {"9", "X", "U"}:
        return "X"
    return None


def _parse_country(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip().upper()
    if raw in {"USA", "US", "UNITED STATES"}:
        return "US"
    if raw in {"CAN", "CA", "CANADA"}:
        return "CA"
    return None


def _normalize_text(text: str) -> str:
    normalized = text.replace("\0", "").replace("\x1e", "\n").replace("\x1d", "\n")
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    return normalized


def _clean_value(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = (
        value
        .replace("<LF>", " ")
        .replace("<CR>", " ")
        .replace("\n", " ")
        .replace("\r", " ")
        .strip(" *-\t")
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or None


def _extract_field_map(text: str) -> dict[str, str]:
    normalized = _normalize_text(text)
    fields: dict[str, str] = {}
    code_pattern = r"(?:%s|Z[A-Z0-9]{2})" % "|".join(_FIELD_CODES)

    for raw_line in normalized.split("\n"):
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith(("DL", "ID")) and len(line) > 5 and line[2:5] in _FIELD_CODES:
            line = line[2:]

        if len(line) >= 3 and line[:3] in _FIELD_CODES:
            value = _clean_value(line[3:])
            if value:
                fields.setdefault(line[:3], value)
            continue

        matches = list(re.finditer(rf"({code_pattern})", line))
        if not matches:
            continue
        for idx, match in enumerate(matches):
            code = match.group(1)
            start = match.end()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(line)
            value = _clean_value(line[start:end])
            if value and code in _FIELD_CODES:
                fields.setdefault(code, value)

    return fields


def _candidate_images(image: Image.Image) -> list[tuple[Image.Image, zxingcpp.Binarizer, bool]]:
    width, height = image.size
    lower_half = image.crop((0, max(0, int(height * 0.45)), width, height))
    lower_two_thirds = image.crop((0, max(0, int(height * 0.35)), width, height))

    gray = ImageOps.grayscale(image)
    gray_auto = ImageOps.autocontrast(gray)
    gray_high = ImageEnhance.Contrast(gray_auto).enhance(2.3)
    gray_sharp = ImageEnhance.Sharpness(gray_high).enhance(1.8)
    gray_invert = ImageOps.invert(gray_high)

    lower_gray = ImageOps.autocontrast(ImageOps.grayscale(lower_half))
    lower_high = ImageEnhance.Contrast(lower_gray).enhance(2.6)
    lower_big = lower_high.resize((lower_high.width * 2, lower_high.height * 2))

    lower_two_gray = ImageOps.autocontrast(ImageOps.grayscale(lower_two_thirds))
    lower_two_big = ImageEnhance.Contrast(lower_two_gray).enhance(2.2).resize((lower_two_gray.width * 2, lower_two_gray.height * 2))

    return [
        (image.convert("RGB"), zxingcpp.Binarizer.LocalAverage, True),
        (gray_auto, zxingcpp.Binarizer.LocalAverage, True),
        (gray_high, zxingcpp.Binarizer.LocalAverage, False),
        (gray_sharp, zxingcpp.Binarizer.LocalAverage, False),
        (gray_high, zxingcpp.Binarizer.GlobalHistogram, False),
        (gray_invert, zxingcpp.Binarizer.GlobalHistogram, False),
        (lower_half.convert("RGB"), zxingcpp.Binarizer.LocalAverage, True),
        (lower_high, zxingcpp.Binarizer.LocalAverage, False),
        (lower_high, zxingcpp.Binarizer.GlobalHistogram, False),
        (lower_big, zxingcpp.Binarizer.LocalAverage, False),
        (lower_two_big, zxingcpp.Binarizer.LocalAverage, False),
    ]


def _decode_pdf417_text(image_path: str | Path) -> str | None:
    with Image.open(image_path) as image:
        image = image.convert("RGB")
        for candidate, binarizer, try_invert in _candidate_images(image):
            barcodes = zxingcpp.read_barcodes(
                candidate,
                formats=zxingcpp.BarcodeFormat.PDF417,
                try_rotate=True,
                try_downscale=False,
                try_invert=try_invert,
                binarizer=binarizer,
            )
            for barcode in barcodes:
                text = getattr(barcode, "text", None)
                if text:
                    return str(text)
    return None


def extract_pdf417_fields(image_path: str | Path) -> dict[str, Any]:
    text = _decode_pdf417_text(image_path)
    if not text:
        return {}

    fields = _extract_field_map(text)
    first_name = fields.get("DAC")
    last_name = fields.get("DCS")
    full_name = fields.get("DAA")
    middle_name = fields.get("DAD")

    if full_name and (not first_name or not last_name):
        parts = [part.strip() for part in re.split(r"[,\s]+", full_name) if part.strip()]
        if parts:
            last_name = last_name or parts[0]
        if len(parts) > 1:
            first_name = first_name or parts[1]
        if len(parts) > 2:
            middle_name = middle_name or " ".join(parts[2:])

    payload: dict[str, Any] = {}
    source_fields: dict[str, dict[str, Any]] = {}

    def put(key: str, value: str | None, source_key: str | None = None, confidence: float = 0.93) -> None:
        if not value:
            return
        payload[key] = value
        source_fields[source_key or key] = {"source": "pdf417", "confidence": confidence}

    license_number = fields.get("DAQ")
    region = fields.get("DAJ")
    country = _parse_country(fields.get("DCG"))
    expiry = _parse_date(fields.get("DBA"))
    issue_date = _parse_date(fields.get("DBD"))
    birth_date = _parse_date(fields.get("DBB"))

    put("driver_license_number", license_number, "license_number")
    put("license_number", license_number, "license_number")
    put("license_region", region, "license_state")
    put("license_state", region, "license_state")
    put("license_expiry", expiry)
    put("license_issue_date", issue_date)
    put("license_class", fields.get("DCA"))
    put("cdl_class", fields.get("DCA"), "license_class")
    put("restrictions", fields.get("DCB"))
    put("endorsements", fields.get("DCD"))
    put("first_name", first_name)
    put("middle_name", middle_name, confidence=0.88)
    put("last_name", last_name)
    put("date_of_birth", birth_date)
    put("sex", _parse_sex(fields.get("DBC")))
    put("height", fields.get("DAU"))
    put("address_line", fields.get("DAG"), confidence=0.88)
    put("address_street", fields.get("DAG"), confidence=0.88)
    put("address_city", fields.get("DAI"), confidence=0.88)
    put("address_region", region, confidence=0.88)
    put("address_postal", fields.get("DAK"), confidence=0.88)
    put("address_country", country, confidence=0.95)

    if payload:
        payload["field_sources"] = source_fields
        payload["pdf417_text"] = text

    return payload
