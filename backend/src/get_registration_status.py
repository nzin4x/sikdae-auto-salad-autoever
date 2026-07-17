"""가입자 수 / 정원 조회."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict

from core import ConfigStore
from lambda_http import json_response as _response

LOGGER = logging.getLogger()
if not LOGGER.handlers:
    logging.basicConfig(level=logging.INFO)
LOGGER.setLevel(logging.INFO)


def get_registration_status_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    try:
        max_users = int(os.environ.get("MAX_USERS", "10"))
        config_store = ConfigStore()
        count = config_store.count_users()
        return _response(200, {"count": count, "limit": max_users, "isFull": count >= max_users})
    except Exception as error:
        LOGGER.exception("Error getting registration status")
        return _response(500, {"message": str(error)})
