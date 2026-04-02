"""Public workspace intake API: validation (no tenant DB)."""

from __future__ import annotations


def test_workspace_intake_rejects_unknown_package_code(client):
    r = client.post(
        "/api/v1/public/workspace-intake",
        json={
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@example.com",
            "confirm_email": "ada@example.com",
            "phone_number": "+1 555 0100",
            "selected_package_code": "GOLD_PLAN",
        },
    )
    assert r.status_code == 422


def test_workspace_intake_rejects_email_mismatch(client):
    r = client.post(
        "/api/v1/public/workspace-intake",
        json={
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@example.com",
            "confirm_email": "other@example.com",
            "phone_number": "+1 555 0100",
            "selected_package_code": "FREE_TRIAL",
        },
    )
    assert r.status_code == 422


def test_workspace_intake_consume_unknown_token(client):
    r = client.post(
        "/api/v1/public/workspace-intake/consume",
        json={"intake_token": "not-a-real-token-but-long-enough-12345"},
    )
    assert r.status_code == 400
