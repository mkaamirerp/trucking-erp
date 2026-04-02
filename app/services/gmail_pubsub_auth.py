"""Verify Google-signed OIDC tokens on Pub/Sub push requests (authenticated push)."""

from __future__ import annotations

import logging

from google.auth.transport import requests as google_auth_requests
from google.oauth2 import id_token as google_id_token

logger = logging.getLogger(__name__)


def verify_pubsub_push_oidc(bearer_token: str, audience: str) -> dict:
    """
    Validate JWT from Authorization: Bearer … against Google's certs.
    `audience` must match the Pub/Sub push subscription OIDC audience (usually the push URL).
    Returns decoded claims on success; raises ValueError on failure.
    """
    if not bearer_token or not audience:
        raise ValueError("missing token or audience")
    request = google_auth_requests.Request()
    return google_id_token.verify_oauth2_token(bearer_token, request, audience=audience)
