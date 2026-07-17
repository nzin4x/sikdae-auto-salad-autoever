"""결제 내역(pointbook) 조회 — Mealc의 useDate는 실제 식사일이 아니라 결제 처리 시각이다.

'다음 근무일에 무엇이 예약되어 있는지'는 이 API로는 알 수 없으므로 check_reservation.py를 쓴다.
이 핸들러는 순수 결제내역(영수증) 열람용이다.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict

from core import ConfigStore, MealcClient
from lambda_http import json_response as _response
from lambda_http import parse_body as _parse_body

LOGGER = logging.getLogger()
if not LOGGER.handlers:
    logging.basicConfig(level=logging.INFO)
LOGGER.setLevel(logging.INFO)


def list_reservations_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    try:
        body = _parse_body(event)
        email = body.get("email")
        if not email:
            return _response(400, {"message": "email is required"})

        end_date = body.get("endDate") or datetime.now().strftime("%Y-%m-%d")
        start_date = body.get("startDate") or (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")

        config_store = ConfigStore()
        preferences = config_store.get_user_preferences(email)

        client = MealcClient()
        login_result = client.login(preferences.mealc_user_id, preferences.mealc_password)
        if not login_result.success:
            return _response(401, {"message": "Login failed", "error": login_result.message})

        histories = client.get_pointbook_list(start_date, end_date).get("histories", [])
        return _response(200, {"email": email, "startDate": start_date, "endDate": end_date, "histories": histories})
    except KeyError:
        return _response(404, {"message": "User not found"})
    except Exception as error:
        LOGGER.exception("Error listing reservations")
        return _response(500, {"message": str(error)})
