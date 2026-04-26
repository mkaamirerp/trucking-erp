"""Map `CriticalExtractionV11Root` → `LoadParseExtractedFields` (workspace/Load Lab shape)."""

from __future__ import annotations

from app.schemas.critical_extraction_v11 import CriticalExtractionV11Root
from app.schemas.load_document_parse import LoadParseExtractedFields, LoadParseStopItem


def _map_stop_type(raw: str | None) -> str:
    s = (raw or "").strip().casefold()
    if s in ("pickup", "delivery", "drop", "other"):
        return s
    return "other"


def map_critical_v11_to_extracted_fields(
    c: CriticalExtractionV11Root,
) -> LoadParseExtractedFields:
    eq_parts = [c.equipment.equipment_type, c.equipment.trailer_size]
    equipment_type = " ".join(x for x in eq_parts if (x or "").strip()).strip() or None

    temp: str | None = None
    t = c.temperature_requirement
    if t.temperature_required is True or t.temperature_min is not None or t.temperature_max is not None:
        bits: list[str] = []
        if t.temperature_min is not None or t.temperature_max is not None:
            u = t.temperature_unit or "F"
            lo = t.temperature_min
            hi = t.temperature_max
            if lo is not None and hi is not None:
                bits.append(f"{lo}-{hi} {u}".strip())
            elif lo is not None:
                bits.append(f"min {lo} {u}".strip())
            elif hi is not None:
                bits.append(f"max {hi} {u}".strip())
        if t.run_type:
            bits.append(str(t.run_type))
        if bits:
            temp = " | ".join(bits)

    est: int | None = None
    if c.weight.weight_lbs is not None:
        try:
            est = int(round(float(c.weight.weight_lbs)))
        except (TypeError, ValueError):
            est = None

    stops_out: list[LoadParseStopItem] = []
    for i, s in enumerate(c.stops or []):
        seq = s.stop_sequence if s.stop_sequence is not None else i
        if seq < 0:
            seq = i
        stops_out.append(
            LoadParseStopItem(
                stop_type=_map_stop_type(s.stop_type),
                sequence=int(seq),
                facility_name=(s.facility_name or None),
                street=(s.street or None),
                city=(s.city or None),
                state_or_province=(s.state_province or None),
                postal_code=(s.postal_zip or None),
                country=(s.country or None),
                appointment_date=(s.date or None),
                appointment_time_text=(s.time_window or None),
            )
        )

    return LoadParseExtractedFields(
        broker_name_snapshot=(c.broker_name.value or None),
        broker_load_reference=(c.broker_load_reference.value or None),
        equipment_type=equipment_type,
        trailer_type=None,
        trailer_size=None,
        commodity=(c.commodity.value or None),
        estimated_weight=est,
        temperature_requirement=temp,
        rate=(c.carrier_rate_total.amount or None) if c.carrier_rate_total.amount is not None else None,
        references=[],
        stops=stops_out,
    )
