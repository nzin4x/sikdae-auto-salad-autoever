"""웹 푸시 구독 등록."""

from __future__ import annotations

import logging
from typing import Any, Dict

from core import ConfigStore
from lambda_http import json_response as _response
from lambda_http import parse_body as _parse_body

LOGGER = logging.getLogger()
if not LOGGER.handlers:
    logging.basicConfig(level=logging.INFO)
LOGGER.setLevel(logging.INFO)


def push_subscribe_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    try:
        body = _parse_body(event)
        email = body.get("email")
        fingerprint = body.get("deviceFingerprint")
        subscription = body.get("subscription")
        platform = body.get("platform")

        if not email or not fingerprint or not subscription:
            return _response(400, {"message": "email, deviceFingerprint, subscription are required"})
        if "endpoint" not in subscription or "keys" not in subscription:
            return _response(400, {"message": "subscription must include endpoint and keys"})

        config_store = ConfigStore()
        config_store.save_push_subscription(email, fingerprint, subscription, platform or "unknown")
        return _response(200, {"message": "Push subscription saved", "email": email})
    except Exception as error:
        LOGGER.exception("Error saving push subscription")
        return _response(500, {"message": str(error)})
