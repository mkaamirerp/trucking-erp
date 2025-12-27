# Decision 0005: Storage & OCR Pipeline
**Status:** Active  
**Context:** Driver documents must be stored reliably, later moved to S3, and OCR should extract structured fields.

## Decision
Storage:
- Dev: local filesystem
- Prod: single S3 bucket with per-tenant prefixes
- DB stores `storage_key` + metadata
- Code uses a storage abstraction to switch providers

OCR:
- OCR runs as background job (Celery planned)
- Store OCR output as structured JSON on document records
- Later: compare OCR-extracted fields against manual entries

