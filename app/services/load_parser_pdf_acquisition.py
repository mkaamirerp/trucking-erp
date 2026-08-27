"""Load / Rate-Con PDF acquisition classifier (Slice 3A).

Classifies each page as usable embedded text vs OCR-required.
Does **not** run OCR. Does **not** perform semantic/business parsing.
Does **not** use image/XObject presence as the decision.

Reuses ``extract_text_and_pages_from_pdf_bytes`` — no duplicate PDF extraction.
"""

from __future__ import annotations

import re
from typing import Any

from app.services.pdf_text_extract import extract_text_and_pages_from_pdf_bytes

# Tunable mechanical usability thresholds (not freight-vocabulary based).
MIN_ALPHANUMERIC_CHARS = 40
MIN_WORD_LIKE_TOKENS = 5

_CONTROL_JUNK_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WHITESPACE_RE = re.compile(r"\s+")
_WORD_LIKE_RE = re.compile(r"[A-Za-z0-9]{2,}")
_ALPHANUM_RE = re.compile(r"[A-Za-z0-9]")

SOURCE_EMBEDDED = "embedded_text"
SOURCE_OCR_REQUIRED = "ocr_required"
PDF_DIGITAL = "digital_text"
PDF_SCANNED = "scanned_image"
PDF_MIXED = "mixed"


def normalize_text_for_usability_scoring(raw: str | None) -> str:
    """Mechanical normalize for scoring only: drop control junk, collapse whitespace."""
    if raw is None:
        return ""
    cleaned = _CONTROL_JUNK_RE.sub(" ", str(raw))
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
    return cleaned


def count_alphanumeric_chars(scored: str) -> int:
    return len(_ALPHANUM_RE.findall(scored))


def count_word_like_tokens(scored: str) -> int:
    return len(_WORD_LIKE_RE.findall(scored))


def page_has_usable_embedded_text(
    raw_page_text: str | None,
    *,
    min_alphanumeric_chars: int = MIN_ALPHANUMERIC_CHARS,
    min_word_like_tokens: int = MIN_WORD_LIKE_TOKENS,
) -> tuple[bool, dict[str, int]]:
    """Return (usable, metrics) for one page's embedded extract.

    Metrics are derived from the scoring-normalized form, not freight keywords.
    """
    scored = normalize_text_for_usability_scoring(raw_page_text)
    alnum = count_alphanumeric_chars(scored)
    words = count_word_like_tokens(scored)
    usable = alnum >= int(min_alphanumeric_chars) and words >= int(min_word_like_tokens)
    return usable, {
        "alphanumeric_chars": alnum,
        "word_like_tokens": words,
        "raw_char_len": len(raw_page_text or ""),
        "scored_char_len": len(scored),
    }


def classify_pages_from_embedded_texts(
    page_texts: list[str],
    *,
    min_alphanumeric_chars: int = MIN_ALPHANUMERIC_CHARS,
    min_word_like_tokens: int = MIN_WORD_LIKE_TOKENS,
    extraction_warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Classify already-extracted page strings into the acquisition contract.

    Choice for ``text`` on OCR-required pages (Slice 3A):
    - Downstream evidence ``text`` is ``""`` so weak garbage is not treated as authoritative.
    - Original weak extract is preserved in ``weak_embedded_text`` when non-empty (diagnostics only).
    Usable pages keep the **original** extracted page text in ``text`` (not the scoring form).
    """
    pages_out: list[dict[str, Any]] = []
    for idx, raw in enumerate(page_texts):
        original = raw if isinstance(raw, str) else str(raw or "")
        usable, metrics = page_has_usable_embedded_text(
            original,
            min_alphanumeric_chars=min_alphanumeric_chars,
            min_word_like_tokens=min_word_like_tokens,
        )
        page_number = idx + 1
        if usable:
            pages_out.append(
                {
                    "page_number": page_number,
                    "source": SOURCE_EMBEDDED,
                    "usable_embedded_text": True,
                    "requires_ocr": False,
                    "text": original,
                    "metrics": metrics,
                }
            )
        else:
            page: dict[str, Any] = {
                "page_number": page_number,
                "source": SOURCE_OCR_REQUIRED,
                "usable_embedded_text": False,
                "requires_ocr": True,
                "text": "",
                "metrics": metrics,
            }
            # Diagnostics only — not authoritative evidence.
            if original.strip():
                page["weak_embedded_text"] = original
            pages_out.append(page)

    embedded_count = sum(1 for p in pages_out if p["source"] == SOURCE_EMBEDDED)
    ocr_count = sum(1 for p in pages_out if p["source"] == SOURCE_OCR_REQUIRED)
    page_count = len(pages_out)

    if page_count == 0:
        pdf_type = PDF_SCANNED
        requires_ocr = True
    elif ocr_count == 0:
        pdf_type = PDF_DIGITAL
        requires_ocr = False
    elif embedded_count == 0:
        pdf_type = PDF_SCANNED
        requires_ocr = True
    else:
        pdf_type = PDF_MIXED
        requires_ocr = True

    return {
        "pdf_type": pdf_type,
        "page_count": page_count,
        "requires_ocr": requires_ocr,
        "pages": pages_out,
        "warnings": list(extraction_warnings or []),
        "usability_thresholds": {
            "min_alphanumeric_chars": int(min_alphanumeric_chars),
            "min_word_like_tokens": int(min_word_like_tokens),
        },
    }


def acquire_load_parser_pdf_pages(
    pdf_bytes: bytes,
    *,
    min_alphanumeric_chars: int = MIN_ALPHANUMERIC_CHARS,
    min_word_like_tokens: int = MIN_WORD_LIKE_TOKENS,
) -> dict[str, Any]:
    """Extract embedded text via shared pypdf helper, then classify pages (no OCR)."""
    _full, page_texts, warnings = extract_text_and_pages_from_pdf_bytes(pdf_bytes)
    return classify_pages_from_embedded_texts(
        list(page_texts),
        min_alphanumeric_chars=min_alphanumeric_chars,
        min_word_like_tokens=min_word_like_tokens,
        extraction_warnings=warnings,
    )
