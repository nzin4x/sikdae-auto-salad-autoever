"""가장 가까운 예약을 취소한다 — 식대포인트가 즉시 환불되는 실사용 액션."""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional

import pytz

from core import (
    ConfigStore,
    MealcClient,
    active_booking_menu_histories,
    all_menu_contents,
    booking_store_id_from_history,
)
from lambda_http import json_response as _response
from lambda_http import parse_body as _parse_body

LOGGER = logging.getLogger()
if not LOGGER.handlers:
    logging.basicConfig(level=logging.INFO)
LOGGER.setLevel(logging.INFO)

CANCEL_MESSAGE = "단순 변심! 나중에 다시 구매 할게요"
HISTORY_LOOKBACK_DAYS = 30
CANCEL_SEARCH_DAYS = 14


def find_nearest_cancelable_reservation(
    client: MealcClient,
    store_id: str,
    active_histories: Dict[str, Dict[str, Any]],
    today: date,
    search_days: int = CANCEL_SEARCH_DAYS,
) -> Optional[Dict[str, Any]]:
    """Match active payments to meal dates and return the nearest cancelable one."""
    detail_cache: Dict[str, Dict[str, Any]] = {}
    for offset in range(search_days + 1):
        meal_date = today + timedelta(days=offset)
        menu_response = client.get_store_menu(store_id, meal_date.isoformat())
        for menu in all_menu_contents(menu_response):
            history = active_histories.get(str(menu.get("id") or ""))
            if not history:
                continue

            coupon_id = history.get("couponId")
            if not coupon_id:
                continue
            if coupon_id not in detail_cache:
                detail_cache[coupon_id] = client.get_pointbook_detail(coupon_id)
            history_info = detail_cache[coupon_id].get("historyInfo") or {}
            if not history_info.get("isCancelable", True) or not history_info.get("historyIdx"):
                continue

            return {
                "date": meal_date.isoformat(),
                "history": history,
                "historyInfo": history_info,
                "menuName": menu.get("name") or "",
            }
    return None


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

        timezone = pytz.timezone(os.environ.get("DEFAULT_TIMEZONE", "Asia/Seoul"))
        today = datetime.now(timezone).date()
        start_date = (today - timedelta(days=HISTORY_LOOKBACK_DAYS)).isoformat()
        histories = client.get_pointbook_list(
            start_date, today.isoformat(), page=1, page_row=100
        ).get("histories", [])

        store_id = (
            preferences.store_id
            or booking_store_id_from_history(histories)
            or client.find_booking_store_id()
        )
        if not store_id:
            return _response(404, {"message": "배달식사 매장을 찾지 못함"})

        active_histories = active_booking_menu_histories(histories, store_id)
        LOGGER.info(
            "Cancel search state loaded: store=%s activeMenus=%d",
            store_id,
            len(active_histories),
        )
        target = find_nearest_cancelable_reservation(
            client, store_id, active_histories, today
        )
        if not target:
            return _response(404, {"message": "취소할 예약이 없습니다"})

        history = target["history"]
        history_info = target["historyInfo"]
        result = client.cancel_booking(
            history_info["historyIdx"], history["couponId"], CANCEL_MESSAGE
        )
        if not result.success:
            return _response(400, {"message": result.message or "취소 실패"})

        return _response(
            200,
            {
                "message": "예약이 취소되었습니다",
                "canceledDate": target["date"],
                "canceledMenu": target["menuName"],
                "couponId": history["couponId"],
            },
        )
    except KeyError:
        return _response(404, {"message": "User not found"})
    except Exception as error:
        LOGGER.exception("Error canceling reservation")
        return _response(500, {"message": str(error)})
