"""Structural safety gate for Load / Rate Confirmation PDF uploads.

This is a deliberately conservative, non-executing gate. It proves that pypdf can
parse the document and rejects PDF features that can carry or trigger active content.
It is not an antivirus engine and does not claim that arbitrary bytes are malware-free.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any

from pypdf import PdfReader
from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject

MAX_LOAD_PDF_BYTES = 20 * 1024 * 1024
MAX_LOAD_PDF_PAGES = 100
MAX_PDF_OBJECTS_SCANNED = 50_000
MAX_PDF_OBJECT_DEPTH = 100

_BLOCKED_KEYS = frozenset(
    {
        "/AA",
        "/EmbeddedFiles",
        "/EF",
        "/JavaScript",
        "/JS",
        "/Launch",
        "/OpenAction",
        "/RichMedia",
        "/RichMediaContent",
        "/XFA",
    }
)
_BLOCKED_ACTION_TYPES = frozenset(
    {
        "/GoToE",
        "/GoToR",
        "/ImportData",
        "/JavaScript",
        "/Launch",
        "/Movie",
        "/Rendition",
        "/RichMediaExecute",
        "/Sound",
        "/SubmitForm",
    }
)


class UnsafeLoadPdfError(ValueError):
    """The upload is not a safe, supported PDF for the Load parser."""


@dataclass(frozen=True)
class LoadPdfSafetyResult:
    page_count: int
    objects_scanned: int


def validate_load_parser_pdf(
    pdf_bytes: bytes,
    *,
    max_bytes: int = MAX_LOAD_PDF_BYTES,
    max_pages: int = MAX_LOAD_PDF_PAGES,
) -> LoadPdfSafetyResult:
    """Validate a PDF without executing document actions or embedded content.

    Benign AcroForm dictionaries are allowed (the Armstrong sample contains an empty
    one), but XFA, JavaScript, automatic actions, launch actions, and embedded files
    are rejected.
    """
    if not pdf_bytes:
        raise UnsafeLoadPdfError("Empty PDF file")
    if len(pdf_bytes) > int(max_bytes):
        raise UnsafeLoadPdfError("PDF exceeds the 20 MB parser limit")
    if not pdf_bytes.startswith(b"%PDF-"):
        raise UnsafeLoadPdfError("Expected a PDF file")

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes), strict=True)
    except Exception as exc:
        raise UnsafeLoadPdfError(
            f"Malformed or unsupported PDF ({type(exc).__name__})"
        ) from exc

    if reader.is_encrypted:
        raise UnsafeLoadPdfError(
            "Encrypted or password-protected PDFs are not supported"
        )

    try:
        page_count = len(reader.pages)
    except Exception as exc:
        raise UnsafeLoadPdfError(
            f"Malformed PDF page tree ({type(exc).__name__})"
        ) from exc
    if page_count < 1:
        raise UnsafeLoadPdfError("PDF contains no pages")
    if page_count > int(max_pages):
        raise UnsafeLoadPdfError(
            f"PDF exceeds the {int(max_pages)} page parser limit"
        )

    try:
        root = reader.trailer["/Root"]
        objects_scanned = _scan_reachable_pdf_objects(root)
    except UnsafeLoadPdfError:
        raise
    except Exception as exc:
        raise UnsafeLoadPdfError(
            f"Malformed PDF object graph ({type(exc).__name__})"
        ) from exc

    return LoadPdfSafetyResult(
        page_count=page_count,
        objects_scanned=objects_scanned,
    )


def _scan_reachable_pdf_objects(root: Any) -> int:
    stack: list[tuple[Any, int]] = [(root, 0)]
    seen_indirect: set[tuple[int, int]] = set()
    seen_direct: set[int] = set()
    objects_scanned = 0

    while stack:
        obj, depth = stack.pop()
        if depth > MAX_PDF_OBJECT_DEPTH:
            raise UnsafeLoadPdfError("PDF object graph is too deeply nested")

        if isinstance(obj, IndirectObject):
            ref = (int(obj.idnum), int(obj.generation))
            if ref in seen_indirect:
                continue
            seen_indirect.add(ref)
            obj = obj.get_object()

        if not isinstance(
            obj,
            (DictionaryObject, ArrayObject, dict, list, tuple),
        ):
            continue
        direct_id = id(obj)
        if direct_id in seen_direct:
            continue
        seen_direct.add(direct_id)

        objects_scanned += 1
        if objects_scanned > MAX_PDF_OBJECTS_SCANNED:
            raise UnsafeLoadPdfError("PDF object graph is too large")

        if isinstance(obj, (DictionaryObject, dict)):
            for raw_key, value in obj.items():
                key = str(raw_key)
                if key in _BLOCKED_KEYS:
                    raise UnsafeLoadPdfError(
                        f"PDF contains blocked active content ({key})"
                    )
                if key == "/S" and str(value) in _BLOCKED_ACTION_TYPES:
                    raise UnsafeLoadPdfError(
                        f"PDF contains blocked action type ({str(value)})"
                    )
                if key == "/Type" and str(value) == "/EmbeddedFile":
                    raise UnsafeLoadPdfError("PDF contains an embedded file")
                stack.append((value, depth + 1))
        else:
            stack.extend((value, depth + 1) for value in obj)

    return objects_scanned

