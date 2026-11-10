"""다음 근무일의 예약 상태 확인.

결제내역(pointbook)의 CONFIRM/CANCELED 상태를 예약 상태의 주 근거로 사용한다.
pointbook의 useDate는 결제 시각이지 식사 예정일이 아니므로 과거 결제를 여러 미래 날짜로
확장하지 않는다. 다음 근무일 메뉴의 booking.isBooked를 우선하고 최신 활성 결제를 보조로 쓴다.
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


def next_workday_booked_item(
    menu_response: Dict[str, Any],
    active_histories: Dict[str, Dict[str, Any]],
) -> Dict[str, Any] | None:
    """Return at most one confirmed menu for the next workday.

    The menu API's ``booking.isBooked`` is authoritative.  The newest active
    pointbook entry is only a fallback because older payment menu IDs can recur
    in later menus and must never mark several future dates as confirmed.
    """
    contents = all_menu_contents(menu_response)
    explicitly_booked = next(
        (
            item
            for item in contents
            if bool((item.get("booking") or {}).get("isBooked"))
        ),
        None,
    )
    if explicitly_booked:
        return explicitly_booked

    contents_by_id = {
        str(item.get("id")): item for item in contents if item.get("id")
    }
    for menu_id in active_histories:
        if menu_id in contents_by_id:
            return contents_by_id[menu_id]
    return None


def check_reservation_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
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

        active_histories = active_booking_menu_histories(histories, store_id)
        LOGGER.info(
            "Reservation history state loaded: active=%d",
            len(active_histories),
        )

        reservations = []
        menu_response = client.get_store_menu(store_id, next_workday.isoformat())
        booked_item = next_workday_booked_item(menu_response, active_histories)
        if booked_item:
            menu_id = str(booked_item.get("id") or "")
            is_cancelable = False
            history = active_histories.get(menu_id)
            coupon_id = history.get("couponId") if history else None
            if coupon_id:
                try:
                    history_info = (
                        client.get_pointbook_detail(coupon_id).get("historyInfo") or {}
                    )
                    is_cancelable = bool(
                        history_info.get("isCancelable") is True
                        and history_info.get("historyIdx")
                    )
                except Exception:  # pylint: disable=broad-except
                    LOGGER.exception(
                        "Failed to load cancelability for coupon %s", coupon_id
                    )

            reservations.append(
                {
                    "date": next_workday.isoformat(),
                    "label": "다음 근무일",
                    "status": "CONFIRMED",
                    "statusLabel": "예약 확정",
                    "isCancelable": is_cancelable,
                    "menus": [booked_item.get("name", "")],
                }
            )

        return _response(
            200,
            {
                "email": email,
                "nextWorkday": next_workday.isoformat(),
                "hasNextWorkdayReservation": bool(reservations),
                "hasCancelableReservation": any(r["isCancelable"] for r in reservations),
                "reservations": reservations,
            },
        )
    except KeyError:
        return _response(404, {"message": "User not found"})
    except Exception as error:
        LOGGER.exception("Error checking reservation")
        return _response(500, {"message": str(error)})
