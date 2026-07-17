"""다가오는 근무일들의 예약 상태 확인.

Mealc의 결제내역(pointbook) API는 '결제 처리 시각'(useDate)만 제공하고 실제 식사 예정일은
주지 않으므로, 각 후보 날짜의 매장 메뉴(get_store_menu)를 조회해 isBooked 플래그로
실제 예약 여부를 판별한다 (매 날짜마다 1회 API 호출).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict

import pytz

from core import ConfigStore, HolidayService, MealcClient, regular_menu_contents
from lambda_http import json_response as _response
from lambda_http import parse_body as _parse_body

LOGGER = logging.getLogger()
if not LOGGER.handlers:
    logging.basicConfig(level=logging.INFO)
LOGGER.setLevel(logging.INFO)

DEFAULT_DAYS_AHEAD = 5


def check_reservation_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    try:
        body = _parse_body(event)
        email = body.get("email")
        if not email:
            return _response(400, {"message": "email is required"})
        days_ahead = int(body.get("daysAhead", DEFAULT_DAYS_AHEAD))

        config_store = ConfigStore()
        preferences = config_store.get_user_preferences(email)

        client = MealcClient()
        login_result = client.login(preferences.mealc_user_id, preferences.mealc_password)
        if not login_result.success:
            return _response(401, {"message": "Login failed", "error": login_result.message})

        store_id = preferences.store_id or client.find_booking_store_id()
        if not store_id:
            return _response(404, {"message": "배달식사 매장을 찾지 못함"})

        kst = pytz.timezone(os.environ.get("DEFAULT_TIMEZONE", "Asia/Seoul"))
        today = datetime.now(kst).date()
        holiday_api_key = os.environ.get("HOLIDAY_API_KEY")
        holiday_service = HolidayService(config_store=config_store)
        next_workday = holiday_service.next_workday(today, holiday_api_key)

        candidates = []
        if today.weekday() < 5 and not holiday_service.is_holiday(today, holiday_api_key):
            candidates.append(today)
        cursor = today
        while len(candidates) < days_ahead:
            cursor = holiday_service.next_workday(cursor, holiday_api_key)
            candidates.append(cursor)

        reservations = []
        for candidate in candidates:
            menu_response = client.get_store_menu(store_id, candidate.strftime("%Y-%m-%d"))
            contents = regular_menu_contents(menu_response)
            booked_menus = [item["name"] for item in contents if item.get("booking", {}).get("isBooked")]
            if booked_menus:
                if candidate == today:
                    label = "오늘"
                elif candidate == next_workday:
                    label = "다음 근무일"
                else:
                    label = "예약 예정"
                reservations.append({"date": candidate.isoformat(), "label": label, "menus": booked_menus})

        return _response(
            200,
            {
                "email": email,
                "nextWorkday": next_workday.isoformat(),
                "hasNextWorkdayReservation": any(r["date"] == next_workday.isoformat() for r in reservations),
                "reservations": reservations,
            },
        )
    except KeyError:
        return _response(404, {"message": "User not found"})
    except Exception as error:
        LOGGER.exception("Error checking reservation")
        return _response(500, {"message": str(error)})
