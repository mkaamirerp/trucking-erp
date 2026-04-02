"""Shared email ingestion: normalize → persist → route (provider-agnostic)."""

from app.services.email_engine.email_ingestion_engine import IngestionContext, ingest_normalized_thread
from app.services.email_engine.normalized import NormalizedAttachment, NormalizedEmailMessage, NormalizedThreadRollup

__all__ = [
    "IngestionContext",
    "ingest_normalized_thread",
    "NormalizedAttachment",
    "NormalizedEmailMessage",
    "NormalizedThreadRollup",
]
