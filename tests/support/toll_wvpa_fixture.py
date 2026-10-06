"""Controlled WVPA monthly-statement PDF fixture (no customer PII)."""

from __future__ import annotations

from decimal import Decimal

from app.models.toll import PDF_PROFILE_EZPASS_WVPA_MONTHLY

WVPA_PERIOD_START = "3/1/2023"
WVPA_PERIOD_END = "3/31/2023"
WVPA_SOURCE_TRIP_COUNT = 74
WVPA_SOURCE_TRIP_CHARGE = Decimal("854.47")
WVPA_ACCOUNT = "000000001"
WVPA_GROUP_A = "02400000001"
WVPA_GROUP_B = "02400000002"
WVPA_GROUP_ZERO = "02400000003"
WVPA_PLATE_B = "PA00000"
WVPA_AGENCIES = ("ILTOLL", "WVPA", "SCC", "ITRCC", "PBA", "OTC")


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _page_stream(lines: list[str]) -> str:
    commands = ["BT /F1 9 Tf 36 760 Td"]
    for index, line in enumerate(lines):
        if index:
            commands.append("0 -12 Td")
        commands.append(f"({_pdf_escape(line)}) Tj")
    commands.append("ET")
    return "\n".join(commands)


def build_text_pdf(pages: list[list[str]]) -> bytes:
    """Minimal digital PDF whose embedded text pypdf can extract."""
    catalog_id = 1
    pages_id = 2
    font_id = 3
    next_id = 4
    page_objs: list[tuple[int, int, str]] = []
    for lines in pages:
        page_id = next_id
        content_id = next_id + 1
        next_id += 2
        stream = _page_stream(lines)
        page_objs.append((page_id, content_id, stream))
    kids = " ".join(f"{page_id} 0 R" for page_id, _content_id, _stream in page_objs)
    obj_map: dict[int, str] = {
        catalog_id: "<< /Type /Catalog /Pages 2 0 R >>",
        pages_id: f"<< /Type /Pages /Kids [{kids}] /Count {len(page_objs)} >>",
        font_id: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    for page_id, content_id, stream in page_objs:
        obj_map[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Contents {content_id} 0 R /Resources << /Font << /F1 3 0 R >> >> >>"
        )
        obj_map[content_id] = f"<< /Length {len(stream.encode('latin-1'))} >>\nstream\n{stream}\nendstream"
    body = b"%PDF-1.4\n"
    offsets = {0: 0}
    for obj_id in range(1, next_id):
        offsets[obj_id] = len(body)
        payload = obj_map[obj_id]
        body += f"{obj_id} 0 obj\n{payload}\nendobj\n".encode("latin-1")
    xref_at = len(body)
    body += f"xref\n0 {next_id}\n".encode("ascii")
    body += b"0000000000 65535 f \n"
    for obj_id in range(1, next_id):
        body += f"{offsets[obj_id]:010d} 00000 n \n".encode("ascii")
    body += (
        f"trailer << /Size {next_id} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode("ascii")
    )
    return body


def wvpa_trip_charges() -> list[Decimal]:
    charges = [Decimal("10.00")] * 50
    charges.extend([Decimal("15.00")] * 20)
    charges.extend([Decimal("18.00")] * 3)
    charges.append(Decimal("0.47"))
    assert len(charges) == WVPA_SOURCE_TRIP_COUNT
    assert sum(charges, Decimal("0.00")) == WVPA_SOURCE_TRIP_CHARGE
    return charges


def wvpa_transaction_lines() -> list[str]:
    charges = wvpa_trip_charges()
    lines: list[str] = []
    for index, charge in enumerate(charges):
        agency = WVPA_AGENCIES[index % len(WVPA_AGENCIES)]
        raw_charge = f"({charge:.2f})"
        if index == 0:
            lines.append(
                f"03/01/2023 {agency} 02/13/2023 14:22 02/13/2023 14:45 I-90-WEST 12 I-94-EAST 08 {raw_charge}"
            )
        elif index % 11 == 0:
            lines.append(f"03/02/2023 {agency} 03/02/2023 09:10 Morgantown-Plaza 3 {raw_charge}")
        else:
            day = 1 + (index % 28)
            lines.append(
                f"03/{day:02d}/2023 {agency} 03/{day:02d}/2023 10:00 03/{day:02d}/2023 10:20 Entry-Loc 1 Exit-Loc 2 {raw_charge}"
            )
    return lines


def build_wvpa_monthly_statement_pdf(*, reconciled: bool = True) -> bytes:
    """Build a 7-page WVPA-shaped digital PDF the shared extractor can read."""
    tx_lines = wvpa_transaction_lines()
    if not reconciled:
        tx_lines = tx_lines[:-1]
    header = [
        "E-ZPass Network Monthly Statement",
        "West Virginia Parkways Authority",
        "WVPA Monthly Toll Statement",
        f"Statement Date: 4/5/2023",
        f"Account Number: {WVPA_ACCOUNT}",
        f"Statement Period: {WVPA_PERIOD_START} to {WVPA_PERIOD_END}",
        "Start Balance: $100.00",
        "End Balance: $50.00",
        "Total Payment Amount: $200.00",
        "Total Payment Count: 1",
        f"Total Number of Trips: {WVPA_SOURCE_TRIP_COUNT}",
        f"Total Trip Charges: {WVPA_SOURCE_TRIP_CHARGE:.2f}",
        f"Transactions for Transponder# {WVPA_GROUP_A}",
        "Post Date Agency Entry Time Exit Time Entry Location Entry Lane Exit Location Exit Lane Transponder # Plate # Trip Charge",
    ]
    pages: list[list[str]] = [header + tx_lines[:8]]
    remaining = tx_lines[8:40]
    while remaining:
        chunk = remaining[:12]
        remaining = remaining[12:]
        pages.append(
            [
                "West Virginia Parkways Authority",
                f"Transactions for Transponder# {WVPA_GROUP_A}",
                "Post Date Agency Entry Time Exit Time Entry Location Entry Lane Exit Location Exit Lane Transponder # Plate # Trip Charge",
                *chunk,
            ]
        )
    group_b = tx_lines[40:]
    pages.append(
        [
            "West Virginia Parkways Authority",
            f"Transactions for Transponder# {WVPA_GROUP_B} and Plate# {WVPA_PLATE_B}",
            "Post Date Agency Entry Time Exit Time Entry Location Entry Lane Exit Location Exit Lane Transponder # Plate # Trip Charge",
            *group_b[:12],
        ]
    )
    pages.append(
        [
            "West Virginia Parkways Authority",
            f"Transactions for Transponder# {WVPA_GROUP_B} and Plate# {WVPA_PLATE_B}",
            "Post Date Agency Agency Entry Time Exit Time Entry Location Entry Lane Exit Location Exit Lane Transponder # Plate # Trip Charge",
            *group_b[12:],
            f"Transactions for Transponder# {WVPA_GROUP_ZERO}",
            "No transactions for this transponder.",
        ]
    )
    while len(pages) < 7:
        pages.append(
            [
                "West Virginia Parkways Authority",
                "WVPA Monthly Toll Statement continued",
                f"Statement Period: {WVPA_PERIOD_START} to {WVPA_PERIOD_END}",
            ]
        )
    pages = pages[:7]
    return build_text_pdf(pages)


def build_non_wvpa_pdf() -> bytes:
    return build_text_pdf(
        [
            [
                "Random Invoice",
                "This is not a toll statement.",
            ]
        ]
    )


__all__ = [
    "PDF_PROFILE_EZPASS_WVPA_MONTHLY",
    "WVPA_ACCOUNT",
    "WVPA_AGENCIES",
    "WVPA_GROUP_A",
    "WVPA_GROUP_B",
    "WVPA_GROUP_ZERO",
    "WVPA_PLATE_B",
    "WVPA_SOURCE_TRIP_CHARGE",
    "WVPA_SOURCE_TRIP_COUNT",
    "build_non_wvpa_pdf",
    "build_wvpa_monthly_statement_pdf",
    "wvpa_transaction_lines",
]
