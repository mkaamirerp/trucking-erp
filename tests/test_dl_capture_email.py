import pytest

from app.utils import email as email_mod


@pytest.mark.asyncio
async def test_send_dl_capture_link_email_uses_restricted_url(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    async def fake_send_email(*, to: str, subject: str, body: str, **_kwargs: object) -> None:
        captured["to"] = to
        captured["subject"] = subject
        captured["body"] = body

    monkeypatch.setattr(email_mod, "send_email", fake_send_email)
    await email_mod.send_dl_capture_link_email(
        to="applicant@example.test",
        capture_link="https://pytest.truckerp.me/dl-capture/restricted-only",
    )
    assert captured["to"] == "applicant@example.test"
    assert "dl-capture/restricted-only" in captured["body"]
    assert "onboarding?token=" not in captured["body"]
    assert "capture" in captured["subject"].lower()
