"""Read-only selection tests for the nearest cancelable reservation."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend" / "src"))

from cancel_reservation import find_nearest_cancelable_reservation  # noqa: E402
from core import active_booking_menu_histories  # noqa: E402


STORE_ID = "actual-store"


def _history(state: str, menu_id: str, coupon_id: str) -> dict:
    return {
        "couponId": coupon_id,
        "state": state,
        "storeInfo": {
            "storeId": STORE_ID,
            "supplyType": 6,
            "supplyTypes": [{"code": "BOOKING"}],
            "orderedMenus": [{"menuId": menu_id, "menuName": menu_id}],
        },
    }


def _menu(menu_id: str, name: str) -> dict:
    return {
        "menus": [
            {"category": {"name": "점심"}, "contents": [{"id": menu_id, "name": name}]}
        ]
    }


class FakeClient:
    def __init__(self) -> None:
        self.menus = {
            "2026-11-10": _menu("today", "오늘 메뉴"),
            "2026-11-11": _menu("tomorrow", "내일 메뉴"),
        }
        self.details = {
            "today-coupon": {"historyInfo": {"historyIdx": 1, "isCancelable": False}},
            "tomorrow-coupon": {"historyInfo": {"historyIdx": 2, "isCancelable": True}},
        }

    def get_store_menu(self, _store_id: str, meal_date: str) -> dict:
        return self.menus.get(meal_date, {"menus": []})

    def get_pointbook_detail(self, coupon_id: str) -> dict:
        return self.details[coupon_id]


def test_latest_cancellation_removes_older_confirmed_payment() -> None:
    active = active_booking_menu_histories(
        [_history("CANCELED", "meal", "canceled"), _history("CONFIRM", "meal", "old")],
        STORE_ID,
    )

    assert active == {}


def test_rebooking_after_cancel_is_active() -> None:
    active = active_booking_menu_histories(
        [_history("CONFIRM", "meal", "new"), _history("CANCELED", "meal", "old")],
        STORE_ID,
    )

    assert active["meal"]["couponId"] == "new"


def test_nearest_cancelable_skips_non_cancelable_today() -> None:
    histories = [
        _history("CONFIRM", "today", "today-coupon"),
        _history("CONFIRM", "tomorrow", "tomorrow-coupon"),
    ]
    active = active_booking_menu_histories(histories, STORE_ID)

    target = find_nearest_cancelable_reservation(
        FakeClient(), STORE_ID, active, date(2026, 11, 10), search_days=2
    )

    assert target is not None
    assert target["date"] == "2026-11-11"
    assert target["menuName"] == "내일 메뉴"
    assert target["history"]["couponId"] == "tomorrow-coupon"
