#!/usr/bin/env python3
"""
Run truckerjson then critical_v1_1 semantic extraction per Load Lab run, capture
parse_response from each response body, and emit a field-by-field comparison report.

Intended: docker cp into truckerp-api, run with app env (JWT + httpx to localhost:8000).

  docker cp tools/run_load_lab_contract_pair_eval.py truckerp-api:/tmp/
  docker exec truckerp-api bash -lc 'set -a && . /run/secrets/truckerp.env && set +a && cd /app && python3 /tmp/run_load_lab_contract_pair_eval.py'

Does not change API defaults.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from typing import Any

import httpx

# Must match a platform member of tenant demo (owner); adjust if your DB differs.
_TENANT_ID = 53
_PLATFORM_USER = "488d1f5e-09f9-49aa-b67d-25e62e04d644"
_TENANT_SLUG = "demo"
SESSION_VERSION = 2

# Evaluation set: docs/LOAD_LAB_REAL_PDF_EVALUATION.md
RUN_IDS = [38, 39, 40, 41, 42, 43]

NONSENSE_REFS = re.compile(
    r"^(yes|relates|will|must|information|inaccuracy)\b$",
    re.IGNORECASE,
)
BASE = "http://127.0.0.1:8000"
HOST = f"{_TENANT_SLUG}.truckerp.me"

REFUSE_WORDS = (
    "remittance",
    "bill to",
    "bill-to",
    "mailing",
    "corporate office",
    "payment",
    "invoice#",
    "invoice #",
)


@dataclass
class Cell:
    mark: str
    note: str = ""
    safer: str = "n/a"  # yes | no | n/a
    guardrail: bool = False


def _get(d: Any, path: str) -> Any:
    cur = d
    for p in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    return cur


def _fmt(v: Any) -> str:
    if v is None:
        return "∅"
    if isinstance(v, (dict, list)):
        j = json.dumps(v, default=str)[: 800]
        return j if len(j) < 800 else j[:797] + "..."
    s = str(v).strip()
    return s if len(s) <= 200 else s[:197] + "..."


def _token_bad_ref(s: str | None) -> bool:
    if not s or not str(s).strip():
        return False
    t = str(s).strip()
    if NONSENSE_REFS.match(t):
        return True
    if len(t) <= 2 and t.isalpha():
        return True
    return False


def _stops_list(ex: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(ex, dict):
        return []
    s = ex.get("stops")
    return [x for x in s if isinstance(x, dict)] if isinstance(s, list) else []


def _mark_scalar(
    label: str,
    t_val: Any,
    c_val: Any,
    *,
    ref_field: bool = False,
) -> tuple[Cell, Cell]:
    """Return (truckerjson_cell, critical_cell) with marks."""
    t_cell = Cell("missing" if t_val is None and t_val != 0 and t_val is not False else "present")
    c_cell = Cell("missing" if c_val is None and c_val != 0 and c_val is not False else "present")

    te = t_val
    ce = c_val
    if ref_field:
        tw = _token_bad_ref(str(te) if te is not None else "")
        cw = _token_bad_ref(str(ce) if ce is not None else "")
        if tw:
            t_cell.mark, t_cell.note = "wrong", "nonsense/weak ref token"
        else:
            t_cell.mark = "needs_review" if te not in (None, "") else "missing"
        if cw:
            c_cell.mark, c_cell.note = "wrong", "nonsense/weak ref token"
        else:
            c_cell.mark = "correct" if ce and not cw else ("missing" if not ce and ce != 0 else "needs_review")
        # if critical blank and legacy had nonsense -> safer
        if tw and (ce is None or ce == ""):
            c_cell.mark, c_cell.note = "missing", "suppressed vs legacy nonsense (good)"
            c_cell.safer, t_cell.safer = "yes", "no"
        elif not tw and ce is None and te:
            c_cell.mark, c_cell.note = "missing", "dropped value vs legacy"
            c_cell.safer = "no"
    else:
        eq = (te is None and ce is None) or (te == ce) or (str(te).strip() == str(ce).strip() if te is not None and ce is not None else False)
        if eq:
            t_cell.mark, c_cell.mark = "correct", "correct"
        elif te is not None and ce is None:
            t_cell.mark = "correct" if label else "needs_review"
            c_cell.mark, c_cell.note = "missing", "dropped in critical"
            c_cell.safer = "no"
        elif te is None and ce is not None:
            t_cell.mark = "missing"
            c_cell.mark = "needs_review"
        else:
            t_cell.mark, c_cell.mark = "wrong", "wrong"
    return t_cell, c_cell


def _critical_rate(ctx: dict[str, Any] | None) -> str:
    if not isinstance(ctx, dict):
        return "∅"
    crit = ctx.get("critical_extraction_v1_1")
    if not isinstance(crit, dict):
        return "∅"
    rt = crit.get("carrier_rate_total")
    if not isinstance(rt, dict):
        return _fmt(crit.get("rate"))  # fall back
    amt = rt.get("amount")
    cur = rt.get("currency")
    return f"amount={amt!r} currency={cur!r}"


def main() -> int:
    sys.path.insert(0, "/app")
    from app.utils.jwt_auth import create_access_token  # type: ignore

    token = create_access_token(
        user_id=_PLATFORM_USER,
        tenant_id=_TENANT_ID,
        tenant_slug=_TENANT_SLUG,
        roles=["TENANT_OWNER"],
        sv=SESSION_VERSION,
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Host": HOST,
    }

    rows_out: list[str] = []
    captured: list[dict[str, Any]] = []

    rows_out.append("# Load Lab — truckerjson vs critical_v1_1 (real run comparison)\n")
    rows_out.append(
        f"Generated on host API; tenant `{_TENANT_SLUG}` (`tenant_id={_TENANT_ID}`). "
        "Each run: **POST** `truckerjson` first (capture), then `critical_v1_1` (capture). "
        "Default in code remains **truckerjson**; this is evidence only.\n"
    )
    rows_out.append("\n| run_id | filename | contract | http | semantic status |\n| --- | --- | --- | --- | --- |")

    with httpx.Client(timeout=300.0) as client:
        for rid in RUN_IDS:
            for contract, name in (("truckerjson", "truckerjson"), ("critical_v1_1", "critical_v1_1")):
                url = f"{BASE}/api/v1/load-lab/runs/{rid}/semantic-extract?force=true&response_contract={contract}"
                r = client.post(url, headers=headers, content="")
                try:
                    body = r.json()
                except Exception:
                    body = {"error": r.text[:2000]}
                st = "?"
                fn = "?"
                if isinstance(body, dict) and "semantic_extract_status" in body:
                    st = str(body.get("semantic_extract_status", ""))
                    fn = str(body.get("filename", "?"))
                rows_out.append(f"| {rid} | {fn} | {name} | {r.status_code} | {st} |")
                if r.status_code != 200 or not isinstance(body, dict):
                    captured.append(
                        {
                            "run_id": rid,
                            "contract": name,
                            "error": f"http_{r.status_code}",
                            "body_snippet": str(body)[:500],
                        }
                    )
                    continue
                pr = body.get("parse_response")
                ctx = (pr or {}).get("context") if isinstance(pr, dict) else None
                gr = None
                if isinstance(pr, dict) and isinstance(pr.get("parse_diagnostics"), dict):
                    gr = (pr.get("parse_diagnostics") or {}).get("critical_extraction_v1_1_guardrails")
                rec = {
                    "run_id": rid,
                    "contract": name,
                    "filename": body.get("filename"),
                    "http": r.status_code,
                    "semantic_extract_status": body.get("semantic_extract_status"),
                    "parse_response": pr,
                    "guardrails_count": len(gr) if isinstance(gr, list) else 0,
                }
                captured.append(rec)
                # Snapshot after each contract (only last parse on run is in DB; this preserves both).
                tag = "truck" if name == "truckerjson" else "crit"
                try:
                    with open(f"/tmp/contract_pair_{rid}_{tag}.json", "w", encoding="utf-8") as jf:
                        json.dump(pr or {}, jf, indent=2, default=str)
                except OSError as e:  # noqa: BLE001
                    print(f"warn: could not write /tmp/contract_pair_{rid}_{tag}.json: {e}", file=sys.stderr)

    # Pair and compare
    by_run: dict[int, dict[str, Any]] = {}
    for c in captured:
        rid = c.get("run_id")
        if rid is None:
            continue
        by_run.setdefault(int(rid), {})[c.get("contract", "")] = c

    rows_out.append("\n## Field-by-field comparison (extracted + notes)\n")
    rows_out.append(
        "\n| run | PDF | field | truckerjson | critical_v1_1 | T mark | C mark | guardrail? | safer C? | note |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"
    )

    for rid in RUN_IDS:
        pair = by_run.get(rid, {})
        t = pair.get("truckerjson")
        c = pair.get("critical_v1_1")
        if not t or not c or t.get("parse_response") is None or c.get("parse_response") is None:
            fn = (t or c or {}).get("filename", "?")
            rows_out.append(
                f"| {rid} | {fn} | * | — | — | error | error | | | "
                f"missing pair or empty parse: t={t is not None} c={c is not None} "
                f"st T={t and t.get('semantic_extract_status')} C={c and c.get('semantic_extract_status')} |"
            )
            continue
        pr_t = t["parse_response"] if isinstance(t.get("parse_response"), dict) else {}
        pr_c = c["parse_response"] if isinstance(c.get("parse_response"), dict) else {}
        ex_t = pr_t.get("extracted") if isinstance(pr_t.get("extracted"), dict) else {}
        ex_c = pr_c.get("extracted") if isinstance(pr_c.get("extracted"), dict) else {}
        ctx_c = pr_c.get("context") if isinstance(pr_c.get("context"), dict) else {}
        gcount = t.get("guardrails_count", 0)  # from truckerjson pass — usually 0
        gcount = c.get("guardrails_count", 0)

        fn = t.get("filename", "?")
        bname_t = ex_t.get("broker_name_snapshot")
        bname_c = ex_c.get("broker_name_snapshot")
        ref_t = ex_t.get("broker_load_reference")
        ref_c = ex_c.get("broker_load_reference")
        rate_t = ex_t.get("rate")
        rate_c = ex_c.get("rate")
        crit_rate_s = _critical_rate(ctx_c)

        # broker name
        b_eq = (bname_t == bname_c) or (str(bname_t or "").strip() == str(bname_c or "").strip())
        t_m = "correct" if bname_t else "missing"
        c_m = "correct" if bname_c else "missing"
        if b_eq and bname_t:
            t_m = c_m = "correct"
        elif not b_eq:
            t_m, c_m = "needs_review", "needs_review"
        rows_out.append(
            f"| {rid} | {fn} | broker_name | {_fmt(bname_t)} | {_fmt(bname_c)} | {t_m} | {c_m} | | n/a | |"
        )

        # ref
        tr_t, tr_c = _mark_scalar("ref", ref_t, ref_c, ref_field=True)
        rows_out.append(
            f"| {rid} | {fn} | broker_load_reference | {_fmt(ref_t)} | {_fmt(ref_c)} | {tr_t.mark} | {tr_c.mark} | "
            f"{'Y' if gcount else 'N'} | {tr_c.safer} | T:{tr_t.note} C:{tr_c.note} |"
        )

        # rate + currency (critical struct)
        rows_out.append(
            f"| {rid} | {fn} | rate (extracted.rate) | {_fmt(rate_t)} | {_fmt(rate_c)} | "
            f"{'correct' if rate_t == rate_c else 'needs_review'} | "
            f"{'correct' if rate_t == rate_c else 'needs_review'} | | n/a | "
            f"critical `carrier_rate_total` in context: {crit_rate_s} |"
        )

        # equipment
        for fld in ("equipment_type", "trailer_type", "trailer_size"):
            vt, vc = ex_t.get(fld), ex_c.get(fld)
            eq = vt == vc
            rows_out.append(
                f"| {rid} | {fn} | {fld} | {_fmt(vt)} | {_fmt(vc)} | "
                f"{'correct' if eq else 'needs_review'} | {'correct' if eq else 'needs_review'} | | n/a | |"
            )

        for fld in ("temperature_requirement", "commodity", "estimated_weight"):
            vt, vc = ex_t.get(fld), ex_c.get(fld)
            eq = vt == vc
            m_t = m_c = "correct" if eq or (vt is None and vc is None) else "needs_review"
            rows_out.append(
                f"| {rid} | {fn} | {fld} | {_fmt(vt)} | {_fmt(vc)} | {m_t} | {m_c} | | n/a | |"
            )

        # stops: summary per index
        st_t, st_c = _stops_list(ex_t), _stops_list(ex_c)
        n = max(len(st_t), len(st_c))
        for i in range(n):
            a = st_t[i] if i < len(st_t) else {}
            b = st_c[i] if i < len(st_c) else {}
            for k in (
                "sequence",
                "stop_type",
                "facility_name",
                "street",
                "city",
                "state_or_province",
                "postal_code",
                "appointment_date",
                "appointment_time_text",
            ):
                va, vb = a.get(k) if isinstance(a, dict) else None, b.get(k) if isinstance(b, dict) else None
                if va is None and vb is None and k in ("sequence", "street", "appointment_date", "appointment_time_text"):
                    continue
                mark_t = "missing" if va is None or va == "" else ("correct" if va == vb else "needs_review")
                mark_c = "missing" if vb is None or vb == "" else ("correct" if va == vb else "needs_review")
                note = ""
                loc = f" {a.get('city', '')!s} {a.get('state_or_province', '')!s}".lower()
                if k in ("city", "state_or_province", "street", "postal_code", "facility_name") and (va or vb):
                    for w in REFUSE_WORDS:
                        if w in loc and i < 2:
                            note += f" [check: '{w}' in stop context] "
                rows_out.append(
                    f"| {rid} | {fn} | stops[{i}].{k} | {_fmt(va)} | {_fmt(vb)} | {mark_t} | {mark_c} | | n/a | {note} |"
                )
        if n == 0:
            rows_out.append(
                f"| {rid} | {fn} | stops[] | ∅ | ∅ | missing | missing | | | |"
            )
        else:
            order_note = "OK" if len(st_t) == len(st_c) else f"count diff T={len(st_t)} C={len(st_c)}"
            rows_out.append(
                f"| {rid} | {fn} | stops[] order/count | {len(st_t)} stops | {len(st_c)} stops | — | — | | | {order_note} |"
            )

    rows_out.append("\n## Interpretation (evidence-based, not a default switch)\n\n")
    rows_out.append(
        "- **guardrail_changed**: see `parse_diagnostics.critical_extraction_v1_1_guardrails` in critical pass (count logged per run in capture; full payload in `parse_response` only on critical rows).\n"
        "- **safer (critical vs legacy)**: for `broker_load_reference`, if legacy is **wrong** (nonsense token) and critical is **null**, treat as **safer** on that field.\n"
        "- Stops: address fields need human verification against the PDF; rows marked `needs_review` on any diff.\n"
    )
    rows_out.append("\n## Raw JSON\n\n")
    rows_out.append("Per-run `parse_response` objects are not embedded here (large). Re-run the script and add file export if you need archives.\n")

    text = "\n".join(rows_out)
    print(text)

    with open("/tmp/LOAD_LAB_CONTRACT_COMPARISON_REPORT.md", "w", encoding="utf-8") as f:
        f.write(text)

    print("\n---\nWrote /tmp/LOAD_LAB_CONTRACT_COMPARISON_REPORT.md in container.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
