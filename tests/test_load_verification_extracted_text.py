"""GET /loads/{id} enrichment — verification_extracted_text from commercial evidence."""

from app.services.loads import verification_extracted_text_from_accepted_parse


def test_verification_extracted_text_from_accepted_parse_raw_text() -> None:
    assert (
        verification_extracted_text_from_accepted_parse({"raw_text": "LINE ONE\nLINE TWO"})
        == "LINE ONE\nLINE TWO"
    )
    assert verification_extracted_text_from_accepted_parse({}) is None
    assert verification_extracted_text_from_accepted_parse(None) is None
