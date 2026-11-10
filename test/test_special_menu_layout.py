"""Regression tests for event-menu layouts that used to hide the lunch menu."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend" / "src"))

from core.models import ApiCallResult, LoginResult, UserPreferences  # noqa: E402
from core.reservation_service import ReservationService, preferred_menu_contents  # noqa: E402


def _event_menu(*, lunch_booked: bool = False) -> dict:
    return {
        "menus": [
            {
                "category": {"name": "금요일 특식"},
                "contents": [
                    {
                        "id": "cake",
                        "name": "조각 케이크",
                        "booking": {"artifactIdx": 100, "isBooked": True},
                    }
                ],
            },
            {
                # The production bug occurs when the regular section is not reliably
                # named or positioned as "점심".
                "category": {"name": "오늘의 메뉴"},
                "contents": [
                    {
                        "id": "sandwich",
                        "name": "[샌드위치]크로와상 BLT 샌드위치",
                        "booking": {"artifactIdx": 200, "isBooked": lunch_booked},
                    },
                    {
                        "id": "salad",
                        "name": "[샐러드]닭가슴살 포케",
                        "booking": {"artifactIdx": 200, "isBooked": False},
                    },
                ],
            },
        ]
    }


def _special_only_menu() -> dict:
    return {
        "menus": [
            {
                "category": {"name": "간편식"},
                "contents": [
                    {
                        "id": "tart",
                        "name": "★가을의 조각, 타르트 4종SET 사전예약★",
                        "booking": {"artifactIdx": 100, "isBooked": False},
                    }
                ],
            }
        ]
    }


def test_preferred_menu_artifact_ignores_booked_cake() -> None:
    contents = preferred_menu_contents(_event_menu(), ["샌드위치"])

    assert [item["id"] for item in contents] == ["sandwich", "salad"]
    assert {item["booking"]["artifactIdx"] for item in contents} == {200}


def test_preferred_menu_artifact_respects_keyword_priority() -> None:
    menu = _event_menu()
    menu["menus"][0]["contents"][0]["name"] = "[샐러드 특식]케이크"

    contents = preferred_menu_contents(menu, ["샌드위치", "샐러드"])

    assert {item["booking"]["artifactIdx"] for item in contents} == {200}


class _ConfigStore:
    def __init__(self) -> None:
        self.updated_date = None

    def get_user_preferences(self, email: str) -> UserPreferences:
        return UserPreferences(
            email=email,
            mealc_user_id="user",
            mealc_password="password",
            menu_preference=["샌드위치"],
            delivery_spot_keyword="4층",
            store_id="store",
        )

    def update_last_reserved_date(self, _email: str, date_str: str) -> None:
        self.updated_date = date_str


class _MealcClient:
    lunch_booked = False
    booked_menu_id = None
    booked_store_id = None

    def login(self, _user_id: str, _password: str) -> LoginResult:
        return LoginResult(True, "ok")

    def get_store_menu(self, _store_id: str, _date_str: str) -> dict:
        return _event_menu(lunch_booked=self.lunch_booked)

    def get_shipping_spots(self, _artifact_idx: int) -> dict:
        return {
            "spots": [{"spotKey": "spot", "spotName": "본사 4층"}],
            "previousShipping": {"tel": ""},
        }

    def get_account_policy(self) -> dict:
        return {"policy": {"day": [{"id": 1}]}, "user": {"name": "테스트"}}

    def check_booking(self, artifact_idx: int) -> dict:
        assert artifact_idx == 200
        return {"content": {"status": "NORMAL"}}

    def book(self, **kwargs) -> ApiCallResult:
        type(self).booked_menu_id = kwargs["menu_id"]
        type(self).booked_store_id = kwargs["store_id"]
        return ApiCallResult(True, 201, "ok", {})


class _SpecialOnlyMealcClient(_MealcClient):
    def get_store_menu(self, _store_id: str, _date_str: str) -> dict:
        return _special_only_menu()


class _MultiStoreConfig(_ConfigStore):
    def get_user_preferences(self, email: str) -> UserPreferences:
        preferences = super().get_user_preferences(email)
        preferences.store_id = None
        return preferences


class _MultiStoreMealcClient(_MealcClient):
    def get_pointbook_list(self, *_args, **_kwargs) -> dict:
        return {"histories": []}

    def find_booking_store_ids(self) -> list[str]:
        return ["meal-set-store", "sandwich-store"]

    def get_store_menu(self, store_id: str, _date_str: str) -> dict:
        if store_id == "meal-set-store":
            return _special_only_menu()
        return _event_menu(lunch_booked=self.lunch_booked)


def test_service_books_sandwich_when_booked_cake_is_first(monkeypatch) -> None:
    from core import reservation_service

    _MealcClient.lunch_booked = False
    _MealcClient.booked_menu_id = None
    monkeypatch.setattr(reservation_service, "MealcClient", _MealcClient)
    store = _ConfigStore()

    result = ReservationService(store).run("person@example.com", service_date=date(2026, 10, 23))

    assert result.success is True
    assert result.message == "[샌드위치]크로와상 BLT 샌드위치 예약 성공"
    assert _MealcClient.booked_menu_id == "sandwich"
    assert store.updated_date == "2026-10-23"


def test_service_detects_booking_only_in_preferred_artifact(monkeypatch) -> None:
    from core import reservation_service

    _MealcClient.lunch_booked = True
    _MealcClient.booked_menu_id = None
    monkeypatch.setattr(reservation_service, "MealcClient", _MealcClient)

    result = ReservationService(_ConfigStore()).run(
        "person@example.com", service_date=date(2026, 10, 23)
    )

    assert result.success is True
    assert result.message == "이미 예약되어 있음"
    assert result.details == {"alreadyBooked": True}
    assert _MealcClient.booked_menu_id is None


def test_service_retries_when_only_special_menu_is_published(monkeypatch) -> None:
    from core import reservation_service

    monkeypatch.setattr(reservation_service, "MealcClient", _SpecialOnlyMealcClient)

    result = ReservationService(_ConfigStore()).run(
        "person@example.com",
        service_date=date(2026, 10, 29),
        notify_on_retryable_failure=False,
    )

    assert result.success is False
    assert result.message == "선호 메뉴 중 예약 가능한 항목이 없음"
    assert result.retryable is True


def test_service_skips_new_meal_set_store_and_books_sandwich_store(monkeypatch) -> None:
    from core import reservation_service

    _MultiStoreMealcClient.lunch_booked = False
    _MultiStoreMealcClient.booked_menu_id = None
    _MultiStoreMealcClient.booked_store_id = None
    monkeypatch.setattr(reservation_service, "MealcClient", _MultiStoreMealcClient)

    result = ReservationService(_MultiStoreConfig()).run(
        "person@example.com", service_date=date(2026, 11, 11)
    )

    assert result.success is True
    assert _MultiStoreMealcClient.booked_menu_id == "sandwich"
    assert _MultiStoreMealcClient.booked_store_id == "sandwich-store"
