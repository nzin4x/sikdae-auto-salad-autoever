"""예약 제외일(휴가 등) 업데이트."""

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


def update_exclusion_dates_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    try:
        body = _parse_body(event)
        email = body.get("email")
        exclusion_dates = body.get("exclusionDates", [])
        if not email:
            return _response(400, {"message": "email is required"})

        config_store = ConfigStore()
        config_store.update_exclusion_dates(email, exclusion_dates)
        return _response(200, {"message": "Exclusion dates updated", "exclusionDates": exclusion_dates})
    except Exception as error:
        LOGGER.exception("Error updating exclusion dates")
        return _response(500, {"message": str(error)})
