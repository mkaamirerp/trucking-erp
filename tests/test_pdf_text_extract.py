def test_pdf_capability_namespace_reexports_same_callables() -> None:
    import app.document_platform.capabilities.pdf.text_extract as new
    import app.services.pdf_text_extract as old

    assert new.extract_text_and_pages_from_pdf_bytes is old.extract_text_and_pages_from_pdf_bytes
    assert new.extract_text_from_pdf_bytes is old.extract_text_from_pdf_bytes
