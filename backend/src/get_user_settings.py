"""사용자 설정 조회."""

from __future__ import annotations

import logging
from typing import Any, Dict

from core import ConfigStore
from lambda_http import json_response as _response

LOGGER = logging.getLogger()
if not LOGGER.handlers:
    logging.basicConfig(level=logging.INFO)
LOGGER.setLevel(logging.INFO)


def get_user_settings_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    try:
        query = event.get("queryStringParameters") or {}
        email = query.get("email")
        if not email:
            return _response(400, {"message": "email is required"})

        config_store = ConfigStore()
        preferences = config_store.get_user_preferences(email)
        push_subscribed = bool(config_store.list_push_subscriptions(email, platform="android"))
        return _response(
            200,
            {
                "email": preferences.email,
                "mealcUserId": preferences.mealc_user_id,
                "menuPreference": preferences.menu_preference,
                "deliverySpotKeyword": preferences.delivery_spot_keyword,
                "exclusionDates": preferences.exclusion_dates,
                "isActive": preferences.is_active,
                "lastReservedDate": preferences.last_reserved_date,
                "pushSubscribed": push_subscribed,
            },
        )
    except KeyError:
        return _response(404, {"message": "User not found"})
    except Exception as error:
        LOGGER.exception("Error getting settings")
        return _response(500, {"message": str(error)})
