from __future__ import annotations

import re
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import zxingcpp

# --- Applicant upload latency (strict monotonic budgets inside decode thread) ---
PDF417_APPLICANT_FAST_BUDGET_SEC = 1.5
PDF417_APPLICANT_THOROUGH_FALLBACK_BUDGET_SEC = 4.0
# asyncio guard (slightly above fast + thorough + PIL overhead)
PDF417_APPLICANT_THREAD_TIMEOUT_SEC = (
    PDF417_APPLICANT_FAST_BUDGET_SEC + PDF417_APPLICANT_THOROUGH_FALLBACK_BUDGET_SEC + 0.75
)

_FIELD_CODES = (
    "DAQ", "DCS", "DAC", "DAD", "DAA",
    "DBA", "DBD", "DBB", "DBC", "DAU",
    "DAG", "DAI", "DAJ", "DAK",
    "DCA", "DCB", "DCD", "DCF", "DCG", "DCK",
    "DDE", "DDF", "DDG",
)
_FIELD_CODES_SET = frozenset(_FIELD_CODES)
_FIELD_CODE_RE = re.compile("|".join(re.escape(c) for c in _FIELD_CODES))

PDF417_INTAKE_METADATA_KEYS: frozenset[str] = frozenset({"field_sources", "pdf417_text"})

_MAX_DEBUG_ATTEMPTS = 120
# FAST (applicant): LocalAverage only — two passes; responsive UI.
_ZXING_TRIES_FAST = (
    (zxingcpp.Binarizer.LocalAverage, True),
    (zxingcpp.Binarizer.LocalAverage, False),
)
# THOROUGH: add GlobalHistogram for hard photos / ops / debug script.
_ZXING_TRIES_THOROUGH = (
    (zxingcpp.Binarizer.LocalAverage, True),
    (zxingcpp.Binarizer.LocalAverage, False),
    (zxingcpp.Binarizer.GlobalHistogram, False),
)


def _binarizer_label(b: zxingcpp.Binarizer) -> str:
    return getattr(b, "name", None) or str(b).split(".")[-1]


def _merge_field_sources(existing: dict | None, incoming: dict | None) -> dict:
    merged = dict(existing or {})
    for key, value in (incoming or {}).items():
        if value:
            merged[key] = value
    return merged


def meaningful_license_field_count(extracted: dict[str, Any]) -> int:
    n = 0
    for k, v in extracted.items():
        if k in PDF417_INTAKE_METADATA_KEYS:
            continue
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        if isinstance(v, dict):
            continue
        n += 1
    return n


@dataclass(frozen=True)
class Pdf417DecodeMeta:
    winning_candidate: str | None
    winning_engine: str | None
    attempts: list[dict[str, Any]]
    """``fast`` | ``fast+thorough_fallback`` | ``thorough``"""
    pipeline: str = "thorough"
    fast_elapsed_ms: float | None = None
    thorough_elapsed_ms: float | None = None
    fast_candidate_count: int = 0
    thorough_candidate_count: int = 0

    def as_debug_dict(self) -> dict[str, Any]:
        return {
            "decode_winning_candidate": self.winning_candidate,
            "decode_winning_engine": self.winning_engine,
            "decode_attempt_count": len(self.attempts),
            "decode_attempts": self.attempts[:_MAX_DEBUG_ATTEMPTS],
            "decode_pipeline": self.pipeline,
            "decode_fast_elapsed_ms": self.fast_elapsed_ms,
            "decode_thorough_elapsed_ms": self.thorough_elapsed_ms,
            "decode_fast_candidate_count": self.fast_candidate_count,
            "decode_thorough_candidate_count": self.thorough_candidate_count,
        }


def _try_pyzbar_pdf417(pil_image: Image.Image) -> str | None:
    try:
        from pyzbar.pyzbar import ZBarSymbol
        from pyzbar.pyzbar import decode as zbar_decode
    except ImportError:
        return None
    try:
        codes = zbar_decode(pil_image, symbols=[ZBarSymbol.PDF417])
    except Exception:
        return None
    for code in codes:
        raw = getattr(code, "data", None)
        if raw:
            try:
                return raw.decode("utf-8", errors="replace")
            except Exception:
                return str(raw)
    return None


def _zxing_read(
    pil_image: Image.Image,
    *,
    binarizer: zxingcpp.Binarizer,
    try_invert: bool,
) -> str | None:
    barcodes = zxingcpp.read_barcodes(
        pil_image,
        formats=zxingcpp.BarcodeFormat.PDF417,
        try_rotate=True,
        try_downscale=True,
        try_invert=try_invert,
        binarizer=binarizer,
    )
    for barcode in barcodes:
        text = getattr(barcode, "text", None)
        if text:
            return str(text)
    return None


def _resize_lanczos(im: Image.Image, scale: float) -> Image.Image:
    w, h = im.size
    nw = max(8, int(w * scale))
    nh = max(8, int(h * scale))
    return im.resize((nw, nh), Image.Resampling.LANCZOS)


def _gray_variants_full(im: Image.Image, prefix: str) -> Iterator[tuple[str, Image.Image]]:
    """Rich preprocessing for full-frame and rotated full-frame paths."""
    g = ImageOps.grayscale(im)
    ac = ImageOps.autocontrast(g)
    yield f"{prefix}_gray_ac", ac
    yield f"{prefix}_gray_eq", ImageOps.equalize(g)
    yield f"{prefix}_gray_ct25", ImageEnhance.Contrast(ac).enhance(2.5)
    yield f"{prefix}_gray_ct32", ImageEnhance.Contrast(ac).enhance(3.2)
    sharp = ImageEnhance.Sharpness(ImageEnhance.Contrast(ac).enhance(2.2)).enhance(2.0)
    yield f"{prefix}_gray_sharp", sharp
    yield f"{prefix}_gray_unsharp", ac.filter(ImageFilter.UnsharpMask(radius=1.5, percent=130, threshold=2))
    yield f"{prefix}_gray_inv", ImageOps.invert(ac)
    yield f"{prefix}_gray_med3", ac.filter(ImageFilter.MedianFilter(size=3))
    yield f"{prefix}_bw128", ac.point(lambda p, _t=128: 255 if p > _t else 0, mode="1").convert("L")
    yield f"{prefix}_bw100", ac.point(lambda p, _t=100: 255 if p > _t else 0, mode="1").convert("L")
    yield f"{prefix}_bw160", ac.point(lambda p, _t=160: 255 if p > _t else 0, mode="1").convert("L")


def _gray_variants_crop(im: Image.Image, prefix: str) -> Iterator[tuple[str, Image.Image]]:
    """Lighter set for spatial crops (many crops × tries must stay bounded)."""
    g = ImageOps.grayscale(im)
    ac = ImageOps.autocontrast(g)
    yield f"{prefix}_gray_ac", ac
    yield f"{prefix}_gray_ct", ImageEnhance.Contrast(ac).enhance(2.9)
    yield f"{prefix}_gray_sharp", ImageEnhance.Sharpness(ImageEnhance.Contrast(ac).enhance(2.1)).enhance(1.9)
    yield f"{prefix}_gray_inv", ImageOps.invert(ac)
    yield f"{prefix}_bw128", ac.point(lambda p, _t=128: 255 if p > _t else 0, mode="1").convert("L")


def _build_spatial_crops(rgb: Image.Image) -> list[tuple[str, Image.Image]]:
    w, h = rgb.size
    out: list[tuple[str, Image.Image]] = []

    def add_crop(name: str, box: tuple[int, int, int, int]) -> None:
        x0, y0, x1, y1 = box
        x0 = max(0, min(w - 1, x0))
        x1 = max(x0 + 8, min(w, x1))
        y0 = max(0, min(h - 1, y0))
        y1 = max(y0 + 8, min(h, y1))
        out.append((name, rgb.crop((x0, y0, x1, y1))))

    add_crop("crop_lower52", (0, int(h * 0.48), w, h))
    add_crop("crop_lower45", (0, int(h * 0.55), w, h))
    add_crop("crop_lower38", (0, int(h * 0.62), w, h))
    add_crop("crop_lower30", (0, int(h * 0.70), w, h))
    add_crop("crop_lower25", (0, int(h * 0.75), w, h))
    add_crop("crop_lower20", (0, int(h * 0.80), w, h))
    add_crop("crop_lower15", (0, int(h * 0.85), w, h))
    add_crop("crop_lower25_inset", (int(w * 0.04), int(h * 0.75), int(w * 0.96), h))
    add_crop("crop_lower30_inset", (int(w * 0.06), int(h * 0.70), int(w * 0.94), h))
    add_crop("crop_band_bar", (int(w * 0.08), int(h * 0.82), int(w * 0.92), int(h * 0.98)))
    add_crop("crop_center_bottom", (int(w * 0.12), int(h * 0.58), int(w * 0.88), h))
    return out


def _build_fast_candidates(rgb: Image.Image) -> list[tuple[str, Image.Image]]:
    """Small prioritized set for applicant FAST phase (exactly 8 PIL variants)."""
    w, h = rgb.size
    out: list[tuple[str, Image.Image]] = []

    def push(name: str, im: Image.Image) -> None:
        out.append((name, im))

    push("fast_full_rgb", rgb)
    g = ImageOps.grayscale(rgb)
    ac = ImageOps.autocontrast(g)
    push("fast_full_gray_ac", ac)
    sharp = ImageEnhance.Sharpness(ImageEnhance.Contrast(ac).enhance(2.2)).enhance(1.9)
    push("fast_full_gray_sharp", sharp)
    push("fast_full_gray_inv", ImageOps.invert(ac))

    y25 = int(h * 0.75)
    band = rgb.crop((int(w * 0.08), int(h * 0.82), int(w * 0.92), int(h * 0.98)))
    push("fast_crop_band_rgb", band.convert("RGB"))
    push("fast_crop_band_gray_ac", ImageOps.autocontrast(ImageOps.grayscale(band)))
    lower = rgb.crop((0, y25, w, h))
    push("fast_crop_lower25_rgb", lower.convert("RGB"))
    g_lo = ImageOps.autocontrast(ImageOps.grayscale(lower))
    push("fast_crop_lower25_gray_ac", g_lo)
    return out


FAST_DECODE_CANDIDATE_COUNT = 8
"""Number of distinct images in :func:`_build_fast_candidates` (ZXing tries multiply this)."""


def _budget_hit(deadline_mon: float | None) -> bool:
    return deadline_mon is not None and time.monotonic() >= deadline_mon


def _decode_loop(
    candidates: list[tuple[str, Image.Image]],
    attempts: list[dict[str, Any]],
    *,
    deadline_mon: float | None,
    zxing_tries: tuple[tuple[zxingcpp.Binarizer, bool], ...],
    run_pyzbar: bool,
    phase: str,
) -> tuple[str | None, str | None, str | None]:
    """Return ``(text, winning_candidate, engine)``."""
    for cname, pil_im in candidates:
        if _budget_hit(deadline_mon):
            attempts.append({"phase": phase, "engine": "none", "ok": False, "note": "budget_exhausted"})
            break
        for binarizer, try_inv in zxing_tries:
            if _budget_hit(deadline_mon):
                attempts.append({"phase": phase, "engine": "none", "ok": False, "note": "budget_exhausted"})
                return None, None, None
            text = _zxing_read(pil_im, binarizer=binarizer, try_invert=try_inv)
            attempts.append({
                "phase": phase,
                "candidate": cname,
                "engine": "zxing",
                "ok": bool(text),
                "invert": try_inv,
                "binarizer": _binarizer_label(binarizer),
            })
            if text:
                return text, cname, "zxing"
    if run_pyzbar:
        for cname, pil_im in candidates:
            if _budget_hit(deadline_mon):
                attempts.append({"phase": phase, "engine": "pyzbar", "ok": False, "note": "budget_exhausted"})
                break
            text = _try_pyzbar_pdf417(pil_im)
            attempts.append({"phase": phase, "candidate": cname, "engine": "pyzbar", "ok": bool(text)})
            if text:
                return text, cname, "pyzbar"
    return None, None, None


def _enumerate_pdf417_image_candidates(rgb: Image.Image) -> list[tuple[str, Image.Image]]:
    w, h = rgb.size
    acc: list[tuple[str, Image.Image]] = []
    seen: set[int] = set()

    def push(name: str, im: Image.Image) -> None:
        sid = id(im)
        if sid in seen:
            return
        seen.add(sid)
        acc.append((name, im))

    push("full_rgb", rgb)
    for angle, tag in ((90, "r90"), (180, "r180"), (270, "r270")):
        push(f"full_rgb_{tag}", rgb.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC))

    if max(w, h) < 1400:
        push("full_rgb_up135", _resize_lanczos(rgb, 1.35))
        push("full_rgb_up175", _resize_lanczos(rgb, 1.75))
    if max(w, h) < 1100:
        push("full_rgb_up220", _resize_lanczos(rgb, 2.2))
    if w > 2000 or h > 2000:
        push("full_rgb_down2", _resize_lanczos(rgb, 0.5))
    if w > 2800 or h > 2800:
        push("full_rgb_down3", _resize_lanczos(rgb, 0.33))

    for gname, gim in _gray_variants_full(rgb, "full"):
        push(gname, gim)

    crops = _build_spatial_crops(rgb)
    for cname, cim in crops:
        push(f"{cname}_rgb", cim.convert("RGB"))
        for gname, gim in _gray_variants_crop(cim, cname):
            push(gname, gim)
        cw, ch = cim.size
        if cw >= 120 and ch >= 40:
            push(f"{cname}_up2", _resize_lanczos(cim, 2.0))
            push(f"{cname}_up25", _resize_lanczos(cim, 2.5))
        if cw > 900:
            push(f"{cname}_down085", _resize_lanczos(cim, 0.85))

    push("full_rgb_brighter", ImageEnhance.Brightness(rgb).enhance(1.25))
    push("full_rgb_darker", ImageEnhance.Brightness(rgb).enhance(0.82))
    push("full_rgb_sat", ImageEnhance.Color(rgb).enhance(1.35))

    return acc


def decode_pdf417_barcode_with_trace(
    image_path: str | Path,
    *,
    save_candidates_dir: Path | None = None,
    mode: Literal["applicant_two_phase", "thorough", "fast_only"] = "thorough",
) -> tuple[str | None, Pdf417DecodeMeta]:
    attempts: list[dict[str, Any]] = []

    try:
        with Image.open(image_path) as image:
            image = ImageOps.exif_transpose(image)
            rgb = image.convert("RGB")
    except Exception as exc:
        attempts.append({"candidate": "__open__", "engine": "none", "ok": False, "error": type(exc).__name__})
        return None, Pdf417DecodeMeta(None, None, attempts, pipeline="open_error")

    if mode == "fast_only":
        t0 = time.monotonic()
        deadline = t0 + PDF417_APPLICANT_FAST_BUDGET_SEC
        fast_c = _build_fast_candidates(rgb)
        text, winner, engine = _decode_loop(
            fast_c,
            attempts,
            deadline_mon=deadline,
            zxing_tries=_ZXING_TRIES_FAST,
            run_pyzbar=False,
            phase="fast",
        )
        elapsed_ms = (time.monotonic() - t0) * 1000
        if text:
            return text, Pdf417DecodeMeta(
                winner,
                engine,
                attempts,
                pipeline="fast",
                fast_elapsed_ms=elapsed_ms,
                fast_candidate_count=len(fast_c),
            )
        return None, Pdf417DecodeMeta(
            None,
            None,
            attempts,
            pipeline="fast",
            fast_elapsed_ms=elapsed_ms,
            fast_candidate_count=len(fast_c),
        )

    if mode == "applicant_two_phase":
        t_fast = time.monotonic()
        deadline_fast = t_fast + PDF417_APPLICANT_FAST_BUDGET_SEC
        fast_c = _build_fast_candidates(rgb)
        text, winner, engine = _decode_loop(
            fast_c,
            attempts,
            deadline_mon=deadline_fast,
            zxing_tries=_ZXING_TRIES_FAST,
            run_pyzbar=False,
            phase="fast",
        )
        fast_ms = (time.monotonic() - t_fast) * 1000
        if text:
            return text, Pdf417DecodeMeta(
                winner,
                engine,
                attempts,
                pipeline="fast",
                fast_elapsed_ms=fast_ms,
                fast_candidate_count=len(fast_c),
            )

        t_th = time.monotonic()
        deadline_th = t_th + PDF417_APPLICANT_THOROUGH_FALLBACK_BUDGET_SEC
        thorough_c = _enumerate_pdf417_image_candidates(rgb)
        text2, winner2, engine2 = _decode_loop(
            thorough_c,
            attempts,
            deadline_mon=deadline_th,
            zxing_tries=_ZXING_TRIES_THOROUGH,
            run_pyzbar=True,
            phase="thorough_fallback",
        )
        thorough_ms = (time.monotonic() - t_th) * 1000
        if text2:
            return text2, Pdf417DecodeMeta(
                winner2,
                engine2,
                attempts,
                pipeline="fast+thorough_fallback",
                fast_elapsed_ms=fast_ms,
                thorough_elapsed_ms=thorough_ms,
                fast_candidate_count=len(fast_c),
                thorough_candidate_count=len(thorough_c),
            )
        return None, Pdf417DecodeMeta(
            None,
            None,
            attempts,
            pipeline="fast+thorough_fallback",
            fast_elapsed_ms=fast_ms,
            thorough_elapsed_ms=thorough_ms,
            fast_candidate_count=len(fast_c),
            thorough_candidate_count=len(thorough_c),
        )

    # mode == "thorough" — ops / debug: full sweep, no time budget, pyzbar last
    candidates = _enumerate_pdf417_image_candidates(rgb)
    if save_candidates_dir is not None:
        save_candidates_dir.mkdir(parents=True, exist_ok=True)
        for idx, (cname, cim) in enumerate(candidates):
            safe = re.sub(r"[^\w.\-]+", "_", cname)[:120]
            out_p = save_candidates_dir / f"{idx:03d}_{safe}.png"
            try:
                cim.save(out_p)
            except Exception:
                pass

    text, winner, engine = _decode_loop(
        candidates,
        attempts,
        deadline_mon=None,
        zxing_tries=_ZXING_TRIES_THOROUGH,
        run_pyzbar=True,
        phase="thorough",
    )
    if text:
        return text, Pdf417DecodeMeta(
            winner,
            engine,
            attempts,
            pipeline="thorough",
            thorough_candidate_count=len(candidates),
        )
    return None, Pdf417DecodeMeta(
        None,
        None,
        attempts,
        pipeline="thorough",
        thorough_candidate_count=len(candidates),
    )


def decode_pdf417_barcode_from_image(image_path: str | Path) -> str | None:
    text, _meta = decode_pdf417_barcode_with_trace(image_path, mode="applicant_two_phase")
    return text


def aamva_element_code_count(text: str) -> int:
    return len(_extract_field_map(text))


def apply_pdf417_to_intake(
    intake: dict[str, Any],
    *,
    raw_barcode_text: str | None,
    technical_error: str | None = None,
    decode_meta: Pdf417DecodeMeta | None = None,
) -> dict[str, Any]:
    out = dict(intake)
    debug: dict[str, Any] = {
        "attempted": True,
        "doc_side": "CDL_BACK",
        "decode_succeeded": False,
        "barcode_char_length": 0,
        "aamva_element_count": 0,
        "meaningful_field_count": 0,
        "extracted_intake_keys": [],
        "error": technical_error,
        "pdf417_text_stored": False,
    }
    if decode_meta:
        debug.update(decode_meta.as_debug_dict())

    if technical_error:
        out["license_extract_status"] = "FAILED"
        out["license_extract_debug"] = debug
        out["license_extract_error"] = technical_error
        return out

    if not raw_barcode_text:
        out["license_extract_status"] = "NO_FIELDS_FOUND"
        out["license_extract_debug"] = debug
        out.pop("license_extract_error", None)
        return out

    debug["decode_succeeded"] = True
    debug["barcode_char_length"] = len(raw_barcode_text)
    debug["aamva_element_count"] = aamva_element_code_count(raw_barcode_text)

    extracted = aamva_intake_from_pdf417_text(raw_barcode_text)
    debug["meaningful_field_count"] = meaningful_license_field_count(extracted)

    field_sources = extracted.pop("field_sources", None)
    extracted.pop("pdf417_text", None)

    for key, value in extracted.items():
        if value not in (None, ""):
            out[key] = value
    if field_sources:
        out["field_sources"] = _merge_field_sources(out.get("field_sources"), field_sources)

    keys = sorted(k for k, v in extracted.items() if v not in (None, ""))
    debug["extracted_intake_keys"] = keys[:40]

    if debug["meaningful_field_count"] == 0:
        out["license_extract_status"] = "NO_FIELDS_FOUND"
    else:
        out["license_extract_status"] = "SUCCESS"
    out["license_extract_debug"] = debug
    out.pop("license_extract_error", None)
    return out


def _parse_date(value: str | None) -> str | None:
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    if len(digits) == 8:
        formats = ("%Y%m%d", "%m%d%Y", "%d%m%Y")
        for fmt in formats:
            try:
                return datetime.strptime(digits, fmt).date().isoformat()
            except ValueError:
                continue
        return None
    if len(digits) == 6:
        for fmt in ("%y%m%d", "%m%d%y", "%d%m%y"):
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
    normalized = normalized.replace("^", "\n")
    return normalized


def _clean_value(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = (
        value.replace("<LF>", " ")
        .replace("<CR>", " ")
        .replace("\n", " ")
        .replace("\r", " ")
        .strip(" *-\t")
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or None


def _extract_field_map_by_positions(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    matches = list(_FIELD_CODE_RE.finditer(text))
    for idx, m in enumerate(matches):
        code = m.group(0)
        if code not in _FIELD_CODES_SET:
            continue
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        value = _clean_value(text[start:end])
        if value:
            fields.setdefault(code, value)
    return fields


def _extract_field_map_lines(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    code_pattern = r"(?:%s|Z[A-Z0-9]{2})" % "|".join(_FIELD_CODES)

    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith(("DL", "ID")) and len(line) > 5 and line[2:5] in _FIELD_CODES_SET:
            line = line[2:]

        matches = list(re.finditer(rf"({code_pattern})", line))
        if not matches:
            continue
        for idx, match in enumerate(matches):
            code = match.group(1)
            start = match.end()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(line)
            value = _clean_value(line[start:end])
            if value and code in _FIELD_CODES_SET:
                fields.setdefault(code, value)

    return fields


def _extract_field_map(text: str) -> dict[str, str]:
    normalized = _normalize_text(text)
    by_pos = _extract_field_map_by_positions(normalized)
    if len(by_pos) >= 3:
        return by_pos
    by_lines = _extract_field_map_lines(normalized)
    merged = dict(by_lines)
    for k, v in by_pos.items():
        merged.setdefault(k, v)
    return merged


def aamva_intake_from_pdf417_text(text: str) -> dict[str, Any]:
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
    dak = fields.get("DAK")
    put("address_postal", dak, confidence=0.88)
    if country == "US" and dak:
        put("zip_code", dak, confidence=0.88)
    put("address_country", country, confidence=0.95)

    if payload:
        payload["field_sources"] = source_fields
        payload["pdf417_text"] = text

    return payload


def extract_pdf417_fields(
    image_path: str | Path,
    *,
    decode_meta_out: list[Pdf417DecodeMeta] | None = None,
) -> dict[str, Any]:
    text, meta = decode_pdf417_barcode_with_trace(image_path, mode="applicant_two_phase")
    if decode_meta_out is not None:
        decode_meta_out.append(meta)
    if not text:
        return {}
    return aamva_intake_from_pdf417_text(text)
