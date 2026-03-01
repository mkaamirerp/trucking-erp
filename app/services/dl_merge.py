"""
Merge dl_extract_v1 result into PersonApplication.intake_payload.
Single place for extract field → intake key mapping.
Does not overwrite fields in user_edited_fields.
"""

from __future__ import annotations

from app.models.person_application import PersonApplication

# Locked mapping: dl_extract_v1 field name → intake_payload key
DL_EXTRACT_TO_INTAKE = {
    "first_name": "first_name",
    "last_name": "last_name",
    "dob": "date_of_birth",
    "license_number": "license_number",
    "issuing_state": "license_state",
    "expiry_date": "license_expiry",
    "issue_date": "license_issue_date",
    "address": "address_line",
    "class": "license_class",
    "endorsements": "endorsements",
    "restrictions": "restrictions",
    "sex": "sex",
    "height": "height",
    "conditions": "conditions",
}


def apply_dl_extract_to_intake(app: PersonApplication, extract: dict) -> None:
    """
    Merge dl_extract_v1 result into app.intake_payload.
    Does not overwrite fields in user_edited_fields.
    """
    if not extract or extract.get("version") != "dl_extract_v1":
        return
    payload = app.intake_payload if app.intake_payload is not None else {}
    payload = dict(payload)
    if "user_edited_fields" not in payload:
        payload["user_edited_fields"] = {}
    edited = payload["user_edited_fields"]
    if "field_sources" not in payload:
        payload["field_sources"] = {}
    sources = payload["field_sources"]
    fields = extract.get("fields") or {}
    doc_type = extract.get("doc_type", "")

    for extract_key, intake_key in DL_EXTRACT_TO_INTAKE.items():
        if extract_key not in fields:
            continue
        node = fields[extract_key]
        value = node.get("value")
        confidence = node.get("confidence", 0)
        if edited.get(intake_key) is True:
            continue
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        payload[intake_key] = value
        sources[intake_key] = {
            "source": "DL",
            "confidence": confidence,
            "doc_type": doc_type,
        }

    payload["dl_extract_status"] = "OK"
    payload["field_sources"] = sources
    app.intake_payload = payload
