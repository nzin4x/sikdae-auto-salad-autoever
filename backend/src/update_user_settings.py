"""사용자 설정 업데이트 (마스터 패스워드 확인 필요 — 식권대장 계정정보를 다루기 때문)."""

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


def update_user_settings_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    try:
        body = _parse_body(event)
        email = body.get("email")
        master_password = body.get("masterPassword")
        if not email or not master_password:
            return _response(400, {"message": "email and masterPassword are required"})

        config_store = ConfigStore()
        if not config_store.verify_master_password(email, master_password):
            return _response(403, {"message": "마스터 패스워드가 올바르지 않습니다"})

        menu_preference = body.get("menuPreference")
        delivery_spot_keyword = body.get("deliverySpotKeyword")
        mealc_user_id = body.get("mealcUserId")
        mealc_password = body.get("mealcPassword")

        if not any([menu_preference, delivery_spot_keyword, mealc_user_id, mealc_password]):
            return _response(400, {"message": "At least one field to update is required"})

        config_store.update_user_settings(
            email,
            menu_preference=menu_preference,
            delivery_spot_keyword=delivery_spot_keyword,
            mealc_user_id=mealc_user_id,
            mealc_password=mealc_password,
        )
        return _response(200, {"message": "Settings updated successfully", "email": email})
    except Exception as error:
        LOGGER.exception("Error updating settings")
        return _response(500, {"message": str(error)})
