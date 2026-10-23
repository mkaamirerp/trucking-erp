#!/usr/bin/env python3
"""One-off: frozen TQLRC 10-call batch for digital PDF architecture experiment."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from app.schemas.load_document_parse_semantic import ParseDocumentSemanticModelOutput
from app.services.load_parser_openai_handoff_v2 import (
    build_load_rate_con_openai_handoff_v2_payload,
    build_v2_openai_system_prompt,
    build_v2_openai_user_message,
)
from app.services.load_parser_pdf_acquisition import acquire_load_parser_pdf_pages
from app.services.load_parser_rate_con_field_rules import get_load_rate_con_field_rules
import httpx

from app.document_platform.capabilities.openai.chat_json_schema import (
    OPENAI_CHAT_COMPLETIONS_URL,
    _build_user_content,
    extract_chat_completion_content_json,
)

TQL_PDF = _REPO / "TQLRC.pdf"
TQL_SHA256 = "05849ad1a1256eff16b7cc117d0b694c55e1b599d9ad6e0da3ba36a2ee8c8b89"
MODEL = "gpt-5-mini"
# gpt-5-mini rejects temperature=0.1 (OpenAI: only default 1). Experiment omits temperature.
SCHEMA_NAME = "load_document_parse_guarded_truckerjson_v1"
EMPTY_EXCLUSION = {
    "names": [],
    "mc_numbers": [],
    "usdot_numbers": [],
    "phones": [],
    "emails": [],
    "email_domains": [],
    "addresses": [],
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_json(obj: object) -> str:
    return _sha256_text(json.dumps(obj, ensure_ascii=True, sort_keys=True, separators=(",", ":")))


def classify_pickup(stops: list) -> str:
    for stop in stops or []:
        if not isinstance(stop, dict):
            continue
        if str(stop.get("stop_type") or "").upper() not in ("PICKUP", "PU"):
            continue
        blob = json.dumps(stop, ensure_ascii=True).upper()
        if "JD FACTORS" in blob or "MISSISSAUGA" in blob:
            return "JD_FACTORS"
        if "CHARLOTTE" in blob:
            return "CHARLOTTE"
        return "OTHER"
    return "OTHER"


def _pick_field(extracted: dict, *keys: str) -> str:
    for k in keys:
        v = extracted.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


async def _frozen_openai_call(
    *,
    api_key: str,
    model: str,
    system: str,
    user_text: str,
    schema: dict,
    schema_name: str,
    pdf_bytes: bytes,
) -> dict:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    user_content = _build_user_content(
        user_text=user_text,
        input_file_bytes=pdf_bytes,
        input_filename="TQLRC.pdf",
    )
    body: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "strict": False, "schema": schema},
        },
    }
    if not model.startswith("gpt-5"):
        body["temperature"] = 0.1
    async with httpx.AsyncClient(timeout=180.0) as client:
        r = await client.post(OPENAI_CHAT_COMPLETIONS_URL, headers=headers, json=body)
        r.raise_for_status()
        return extract_chat_completion_content_json(r.json())


async def main() -> int:
    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        print("OPENAI_API_KEY required", file=sys.stderr)
        return 2
    if not TQL_PDF.is_file():
        print(f"Missing {TQL_PDF}", file=sys.stderr)
        return 2

    pdf_bytes = TQL_PDF.read_bytes()
    if _sha256_bytes(pdf_bytes) != TQL_SHA256:
        print("TQL PDF SHA256 mismatch", file=sys.stderr)
        return 2

    acquisition = acquire_load_parser_pdf_pages(pdf_bytes)
    page_objs = list(acquisition.get("pages") or [])
    handoff_pages = [
        {"page_number": int(p.get("page_number") or i + 1), "text": str(p.get("text") or "")}
        for i, p in enumerate(page_objs)
        if isinstance(p, dict) and not p.get("requires_ocr")
    ]
    raw_text = "\n".join(p["text"] for p in handoff_pages)

    handoff_new = build_load_rate_con_openai_handoff_v2_payload(
        tenant_identity_exclusion=EMPTY_EXCLUSION,
        pages=handoff_pages,
        filename="TQLRC.pdf",
        include_page_text_in_ai_handoff=False,
        page_count=len(handoff_pages),
    )
    handoff_old = build_load_rate_con_openai_handoff_v2_payload(
        tenant_identity_exclusion=EMPTY_EXCLUSION,
        pages=handoff_pages,
        filename="TQLRC.pdf",
        include_page_text_in_ai_handoff=True,
    )

    system = build_v2_openai_system_prompt(pdf_bytes_attached=True)
    user_text = build_v2_openai_user_message(handoff_new, pdf_bytes_attached=True)
    schema = ParseDocumentSemanticModelOutput.model_json_schema()
    field_rules = get_load_rate_con_field_rules()

    user_old = build_v2_openai_user_message(handoff_old, pdf_bytes_attached=False)

    meta = {
        "pdf_sha256": _sha256_bytes(pdf_bytes),
        "system_prompt_sha256": _sha256_text(system),
        "user_message_sha256": _sha256_text(user_text),
        "user_message_old_arch_sha256": _sha256_text(user_old),
        "schema_sha256": _sha256_json(schema),
        "field_rules_sha256": _sha256_json(field_rules),
        "tenant_exclusion_sha256": _sha256_json(EMPTY_EXCLUSION),
        "model": MODEL,
        "temperature": "omitted (gpt-5-mini default only)",
        "schema_name": SCHEMA_NAME,
        "pdf_attached": True,
        "user_message_char_count": len(user_text),
        "user_message_old_char_count": len(user_old),
        "document_pages_text_in_handoff": handoff_new["document"]["pages"],
        "raw_text_char_count_local": len(raw_text),
        "jd_in_user_message": "JD FACTORS" in user_text,
    }
    print("=== FROZEN REQUEST META ===")
    print(json.dumps(meta, indent=2))

    out_path = Path("/tmp/tqlrc_gpt5mini_frozen10.json")
    runs: list[dict] = []
    for i in range(1, 11):
        parsed = await _frozen_openai_call(
            api_key=api_key,
            model=MODEL,
            system=system,
            user_text=user_text,
            schema=schema,
            schema_name=SCHEMA_NAME,
            pdf_bytes=pdf_bytes,
        )
        extracted = parsed.get("extracted") or {}
        stops = extracted.get("stops") or []
        pickup_cls = classify_pickup(stops)
        delivery = next(
            (
                s
                for s in stops
                if str(s.get("stop_type") or "").upper() in ("DELIVERY", "DEL", "DROP")
            ),
            {},
        )
        run = {
            "run": i,
            "pickup_class": pickup_cls,
            "broker": _pick_field(extracted.get("broker_company") or {}, "name")
            or extracted.get("broker_company"),
            "load_reference": extracted.get("principal_load_identifier"),
            "rate": (extracted.get("rate") or extracted.get("customer_rate")),
            "pickup_stop": next(
                (s for s in stops if str(s.get("stop_type") or "").upper() in ("PICKUP", "PU")),
                None,
            ),
            "delivery_stop": delivery,
            "stop_count": len(stops),
            "commodity": extracted.get("commodity"),
            "weight": extracted.get("estimated_weight"),
            "warnings": parsed.get("warnings") or [],
            "raw_openai": parsed,
        }
        runs.append(run)
        print(f"Run {i}: pickup={pickup_cls} ref={run['load_reference']} rate={run['rate']}")

    summary = {
        "meta": meta,
        "pickup_counts": {
            "CHARLOTTE": sum(1 for r in runs if r["pickup_class"] == "CHARLOTTE"),
            "JD_FACTORS": sum(1 for r in runs if r["pickup_class"] == "JD_FACTORS"),
            "OTHER": sum(1 for r in runs if r["pickup_class"] == "OTHER"),
        },
        "runs": runs,
    }
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
