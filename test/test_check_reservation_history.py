"""Reservation dashboard reconciliation between pointbook and future menus."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend" / "src"))

from check_reservation import (  # noqa: E402
    booking_history_menu_states,
    booking_store_id_from_history,
    booked_menu_names,
    next_workday_booked_item,
)


STORE_ID = "booking-store"


def _history(state: str, menu_id: str, *, store_id: str = STORE_ID) -> dict:
    return {
        "state": state,
        "storeInfo": {
            "storeId": store_id,
            "supplyType": 6,
            "supplyTypes": [{"code": "BOOKING", "name": "배달식사"}],
            "orderedMenus": [{"menuId": menu_id, "menuName": menu_id}],
        },
    }


def _menu(*items: tuple[str, str, bool]) -> dict:
    return {
        "menus": [
            {
                "category": {"name": "점심"},
                "contents": [
                    {"id": menu_id, "name": name, "booking": {"isBooked": flag}}
                    for menu_id, name, flag in items
                ],
            }
        ]
    }


def test_confirmed_pointbook_entry_marks_future_menu_booked() -> None:
    confirmed, canceled = booking_history_menu_states(
        [_history("CONFIRM", "sandwich")], STORE_ID
    )

    names = booked_menu_names(
        _menu(("sandwich", "[샌드위치]양념치킨텐더샌드위치", False)),
        confirmed,
        canceled,
    )

    assert names == ["[샌드위치]양념치킨텐더샌드위치"]


def test_canceled_pointbook_entry_overrides_stale_menu_flag() -> None:
    confirmed, canceled = booking_history_menu_states(
        [_history("CANCELED", "sandwich")], STORE_ID
    )

    names = booked_menu_names(
        _menu(("sandwich", "[샌드위치]취소된 메뉴", True)), confirmed, canceled
    )

    assert names == []


def test_rebook_after_cancel_keeps_confirmed_menu() -> None:
    confirmed, canceled = booking_history_menu_states(
        [_history("CONFIRM", "sandwich"), _history("CANCELED", "sandwich")],
        STORE_ID,
    )

    assert confirmed == {"sandwich"}
    assert canceled == set()
    assert booked_menu_names(
        _menu(("sandwich", "[샌드위치]재예약", False)), confirmed, canceled
    ) == ["[샌드위치]재예약"]


def test_latest_cancellation_hides_older_confirmation() -> None:
    confirmed, canceled = booking_history_menu_states(
        [_history("CANCELED", "sandwich"), _history("CONFIRM", "sandwich")],
        STORE_ID,
    )

    assert confirmed == set()
    assert canceled == {"sandwich"}


def test_store_is_selected_from_latest_confirmed_booking() -> None:
    histories = [
        _history("CANCELED", "old", store_id="canceled-store"),
        _history("CONFIRM", "current", store_id="actual-store"),
    ]

    assert booking_store_id_from_history(histories) == "actual-store"


def test_non_booking_store_history_is_ignored() -> None:
    confirmed, canceled = booking_history_menu_states(
        [_history("CONFIRM", "other", store_id="another-store")], STORE_ID
    )

    assert confirmed == set()
    assert canceled == set()


def test_menu_flag_remains_as_legacy_fallback() -> None:
    assert booked_menu_names(
        _menu(("legacy", "기존 예약", True)), set(), set()
    ) == ["기존 예약"]


def test_next_workday_uses_only_explicitly_booked_menu() -> None:
    menu = _menu(
        ("sandwich", "예약한 샌드위치", True),
        ("salad", "예약 가능한 샐러드", False),
        ("meal-set", "예약 가능한 세트", False),
    )
    active = {
        "sandwich": _history("CONFIRM", "sandwich"),
        "salad": _history("CONFIRM", "salad"),
        "meal-set": _history("CONFIRM", "meal-set"),
    }

    item = next_workday_booked_item(menu, active)

    assert item is not None
    assert item["id"] == "sandwich"


def test_next_workday_fallback_uses_only_newest_active_payment() -> None:
    menu = _menu(
        ("newest", "최신 예약", False),
        ("older", "과거 결제 메뉴", False),
    )
    active = {
        "newest": _history("CONFIRM", "newest"),
        "older": _history("CONFIRM", "older"),
    }

    item = next_workday_booked_item(menu, active)

    assert item is not None
    assert item["id"] == "newest"
