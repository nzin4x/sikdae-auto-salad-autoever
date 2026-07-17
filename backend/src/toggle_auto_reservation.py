"""자동 예약 활성화/비활성화 토글."""

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


def toggle_auto_reservation_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    try:
        body = _parse_body(event)
        email = body.get("email")
        if not email:
            return _response(400, {"message": "email is required"})
        if "enabled" not in body or not isinstance(body["enabled"], bool):
            return _response(400, {"message": "enabled (boolean) is required"})

        config_store = ConfigStore()
        config_store.update_auto_reservation_status(email, body["enabled"])
        return _response(200, {"message": "Updated", "email": email, "isActive": body["enabled"]})
    except Exception as error:
        LOGGER.exception("Error toggling auto-reservation")
        return _response(500, {"message": str(error)})
