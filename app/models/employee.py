"""Compatibility shim: the Employee model now lives in app.models.payee."""

from app.models.payee import Employee  # noqa: F401
