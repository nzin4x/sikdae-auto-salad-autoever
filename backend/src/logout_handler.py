"""로그아웃 — 디바이스 등록 해제."""

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


def logout_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    try:
        body = _parse_body(event)
        email = body.get("email")
        device_fingerprint = body.get("deviceFingerprint")
        if not email or not device_fingerprint:
            return _response(400, {"message": "email and deviceFingerprint are required"})

        config_store = ConfigStore()
        removed = config_store.remove_device(email, device_fingerprint)
        return _response(200, {"message": "Logout successful", "deviceRemoved": removed})
    except Exception as error:
        LOGGER.exception("Error during logout")
        return _response(500, {"message": str(error)})
