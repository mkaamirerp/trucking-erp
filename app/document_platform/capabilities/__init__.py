"""Shared document capabilities (Slice 0 bootstrap).

Capabilities are reusable primitives (PDF text extract, OpenAI transport,
barcode decode, DL image geometry, etc.). They are selected by a profile.
They must not choose a business document type and must not post/reconcile
Load, Fuel, Toll, POD, or driver records.

Production implementations are not moved into this package in Slice 0.
"""

__all__: list[str] = []
