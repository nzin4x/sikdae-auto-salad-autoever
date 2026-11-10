"""다가오는 근무일들의 예약 상태 확인.

결제내역(pointbook)의 CONFIRM/CANCELED 상태를 예약 상태의 주 근거로 사용한다.
pointbook의 useDate는 결제 시각이지 식사 예정일이 아니므로, 각 후보 날짜의 메뉴 ID와
활성 결제내역의 orderedMenus.menuId를 교차 매칭해 날짜를 확정한다.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, Set, Tuple

import pytz

from core import (
    ConfigStore,
    HolidayService,
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

DEFAULT_DAYS_AHEAD = 5


def booking_history_menu_states(
    histories: Iterable[Dict[str, Any]], store_id: str
) -> Tuple[Set[str], Set[str]]:
    """Return confirmed and canceled menu IDs for this booking store.

    A canceled payment must not reappear through a stale ``booking.isBooked`` flag.
    Pointbook entries are newest-first.  Only the newest state for a menu ID is
    used, so a cancellation hides an older payment while a later rebooking wins.
    """
    confirmed: Set[str] = set()
    canceled: Set[str] = set()

    for history in histories:
        store_info = history.get("storeInfo") or {}
        if store_info.get("storeId") != store_id:
            continue

        supply_types = store_info.get("supplyTypes") or []
        is_booking = store_info.get("supplyType") == 6 or any(
            supply.get("code") == "BOOKING" for supply in supply_types
        )
        if not is_booking:
            continue

        menu_ids = {
            str(menu["menuId"])
            for menu in store_info.get("orderedMenus") or []
            if menu.get("menuId")
        }
        unresolved_menu_ids = menu_ids.difference(confirmed).difference(canceled)
        if history.get("state") == "CONFIRM":
            confirmed.update(unresolved_menu_ids)
        elif history.get("state") == "CANCELED":
            canceled.update(unresolved_menu_ids)

    return confirmed, canceled


def booked_menu_names(
    menu_response: Dict[str, Any], confirmed_menu_ids: Set[str], canceled_menu_ids: Set[str]
) -> list[str]:
    """Resolve booked menu names, preferring pointbook state over menu flags."""
    return [
        item["name"]
        for item in booked_menu_items(
            menu_response, confirmed_menu_ids, canceled_menu_ids
        )
    ]


def booked_menu_items(
    menu_response: Dict[str, Any], confirmed_menu_ids: Set[str], canceled_menu_ids: Set[str]
) -> list[Dict[str, str]]:
    """Resolve booked menu IDs and names, preferring pointbook state."""
    items: list[Dict[str, str]] = []
    seen: Set[str] = set()
    for item in all_menu_contents(menu_response):
        menu_id = str(item.get("id", ""))
        if menu_id in confirmed_menu_ids:
            is_booked = True
        elif menu_id in canceled_menu_ids:
            is_booked = False
        else:
            is_booked = bool((item.get("booking") or {}).get("isBooked"))

        name = item.get("name", "")
        if is_booked and name and name not in seen:
            items.append({"id": menu_id, "name": name})
            seen.add(name)
    return items


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

        kst = pytz.timezone(os.environ.get("DEFAULT_TIMEZONE", "Asia/Seoul"))
        today = datetime.now(kst).date()
        holiday_api_key = os.environ.get("HOLIDAY_API_KEY")
        holiday_service = HolidayService(config_store=config_store)
        next_workday = holiday_service.next_workday(today, holiday_api_key)

        # Pointbook only exposes payment time, not meal date.  Pull recent active/
        # canceled booking menu IDs once, then map them to each candidate day's menu.
        # It also disambiguates accounts that expose multiple BOOKING stores.
        history_start = (today - timedelta(days=30)).isoformat()
        histories: list[Dict[str, Any]] = []
        try:
            pointbook = client.get_pointbook_list(
                history_start, today.isoformat(), page=1, page_row=100
            )
            histories = pointbook.get("histories", [])
        except Exception:
            LOGGER.exception("Failed to load pointbook; falling back to menu booking flags")

        store_id = (
            preferences.store_id
            or booking_store_id_from_history(histories)
            or client.find_booking_store_id()
        )
        if not store_id:
            return _response(404, {"message": "배달식사 매장을 찾지 못함"})

        try:
            confirmed_menu_ids, canceled_menu_ids = booking_history_menu_states(
                histories, store_id
            )
        except Exception:
            LOGGER.exception("Failed to parse pointbook; falling back to menu booking flags")
            confirmed_menu_ids, canceled_menu_ids = set(), set()

        active_histories = active_booking_menu_histories(histories, store_id)
        cancelable_menu_ids: Set[str] = set()
        detail_cache: Dict[str, Dict[str, Any]] = {}
        for menu_id, history in active_histories.items():
            coupon_id = history.get("couponId")
            if not coupon_id:
                continue
            try:
                if coupon_id not in detail_cache:
                    detail_cache[coupon_id] = client.get_pointbook_detail(coupon_id)
                history_info = detail_cache[coupon_id].get("historyInfo") or {}
                if history_info.get("isCancelable") is True and history_info.get("historyIdx"):
                    cancelable_menu_ids.add(menu_id)
            except Exception:  # pylint: disable=broad-except
                LOGGER.exception("Failed to load cancelability for coupon %s", coupon_id)

        LOGGER.info(
            "Reservation history state loaded: confirmed=%d canceled=%d",
            len(confirmed_menu_ids),
            len(canceled_menu_ids),
        )

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
            booked_items = booked_menu_items(
                menu_response, confirmed_menu_ids, canceled_menu_ids
            )
            if booked_items:
                if candidate == today:
                    label = "오늘"
                elif candidate == next_workday:
                    label = "다음 근무일"
                else:
                    label = "예약 예정"
                is_cancelable = any(
                    item["id"] in cancelable_menu_ids for item in booked_items
                )
                reservations.append(
                    {
                        "date": candidate.isoformat(),
                        "label": label,
                        "status": "CONFIRMED",
                        "statusLabel": "예약 확정",
                        "isCancelable": is_cancelable,
                        "menus": [item["name"] for item in booked_items],
                    }
                )

        return _response(
            200,
            {
                "email": email,
                "nextWorkday": next_workday.isoformat(),
                "hasNextWorkdayReservation": any(r["date"] == next_workday.isoformat() for r in reservations),
                "hasCancelableReservation": any(r["isCancelable"] for r in reservations),
                "reservations": reservations,
            },
        )
    except KeyError:
        return _response(404, {"message": "User not found"})
    except Exception as error:
        LOGGER.exception("Error checking reservation")
        return _response(500, {"message": str(error)})
