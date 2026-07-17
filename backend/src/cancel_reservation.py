"""가장 가까운 예약을 취소한다 — 식대포인트가 즉시 환불되는 실사용 액션."""

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

CANCEL_MESSAGE = "단순 변심! 나중에 다시 구매 할게요"


def cancel_reservation_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    try:
        body = _parse_body(event)
        email = body.get("email")
        if not email:
            return _response(400, {"message": "email is required"})

        config_store = ConfigStore()
        preferences = config_store.get_user_preferences(email)

        client = MealcClient()
        login_result = client.login(preferences.mealc_user_id, preferences.mealc_password)
        if not login_result.success:
            return _response(401, {"message": "Login failed", "error": login_result.message})

        store_id = preferences.store_id or client.find_booking_store_id()

        start_date = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
        histories = client.get_pointbook_list(start_date, end_date).get("histories", [])

        candidates = [
            h
            for h in histories
            if h.get("state") == "CONFIRM" and (not store_id or h.get("storeInfo", {}).get("storeId") == store_id)
        ]
        if not candidates:
            return _response(404, {"message": "취소할 예약이 없습니다"})

        candidates.sort(key=lambda h: h.get("useDate", 0))
        target = candidates[0]

        detail = client.get_pointbook_detail(target["couponId"])
        history_info = detail.get("historyInfo", {})
        if not history_info.get("isCancelable", True):
            return _response(400, {"message": "이 예약은 취소할 수 없는 상태입니다"})

        result = client.cancel_booking(history_info["historyIdx"], target["couponId"], CANCEL_MESSAGE)
        if not result.success:
            return _response(400, {"message": result.message or "취소 실패"})

        menu_name = (target.get("storeInfo", {}).get("orderedMenus") or [{}])[0].get("menuName", "")
        return _response(
            200, {"message": "예약이 취소되었습니다", "canceledMenu": menu_name, "couponId": target["couponId"]}
        )
    except KeyError:
        return _response(404, {"message": "User not found"})
    except Exception as error:
        LOGGER.exception("Error canceling reservation")
        return _response(500, {"message": str(error)})
