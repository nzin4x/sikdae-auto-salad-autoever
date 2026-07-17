"""식권대장 예약 워크플로우 오케스트레이션."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional

import pytz

from .branding import PAGE_URL
from .config_store import ConfigStore
from .holiday_service import HolidayService
from .mealc_client import MealcClient
from .models import ReservationAttempt, UserPreferences
from .ses_notifier import SesNotifier


def regular_menu_contents(menu_response: Dict[str, Any]) -> list:
    """get_store_menu 응답에서 '일반(점심)' 카테고리 섹션의 메뉴 목록만 골라낸다.

    Mealc은 하루 메뉴를 카테고리 섹션 배열(`menus`)로 내려주는데, 특식/이벤트(예: 케이크)가
    별도 섹션으로 함께 올 수 있다. 특식 예약 여부가 일반 점심 예약을 막지 않도록,
    카테고리명에 "점심"이 포함된 섹션을 일반 메뉴로 간주한다(섹션이 하나뿐이면 그걸 사용).
    reservation_service와 check_reservation 핸들러가 동일한 기준을 쓰도록 공용 함수로 둔다.
    """
    menu_sections = menu_response.get("menus", [])
    if not menu_sections:
        return []
    regular_section = next(
        (s for s in menu_sections if "점심" in s.get("category", {}).get("name", "")),
        menu_sections[0],
    )
    return regular_section.get("contents", [])


class ReservationService:
    def __init__(
        self,
        config_store: ConfigStore,
        holiday_service: Optional[HolidayService] = None,
        notifier: Optional[SesNotifier] = None,
        timezone: str = "Asia/Seoul",
    ) -> None:
        self.config_store = config_store
        self.holiday_service = holiday_service
        self.notifier = notifier
        self.timezone = timezone

    def run(self, email: str, service_date: Optional[date] = None) -> ReservationAttempt:
        preferences = self.config_store.get_user_preferences(email)
        tz = pytz.timezone(self.timezone)
        holiday_api_key = os.environ.get("HOLIDAY_API_KEY")
        target_date = service_date or self._next_service_date(tz, holiday_api_key)

        if self.holiday_service and holiday_api_key and self.holiday_service.is_holiday(target_date, holiday_api_key):
            attempt = ReservationAttempt(False, "공휴일이라 건너뜀", target_date)
            self._notify(preferences, attempt)
            return attempt

        target_date_str = target_date.isoformat()
        if target_date_str in preferences.exclusion_dates:
            attempt = ReservationAttempt(False, f"제외일 설정으로 건너뜀: {target_date_str}", target_date)
            self._notify(preferences, attempt)
            return attempt

        client = MealcClient()
        # 다른 기기에서 로그인하면 기존 세션이 끊기는 것으로 확인됨 → 매번 새로 로그인한다.
        login_result = client.login(preferences.mealc_user_id, preferences.mealc_password)
        if not login_result.success:
            attempt = ReservationAttempt(False, f"로그인 실패: {login_result.message}", target_date)
            self._notify(preferences, attempt)
            return attempt

        store_id = preferences.store_id or client.find_booking_store_id()
        if not store_id:
            attempt = ReservationAttempt(False, "배달식사 매장을 찾지 못함", target_date)
            self._notify(preferences, attempt)
            return attempt

        date_str = target_date.strftime("%Y-%m-%d")
        menu_response = client.get_store_menu(store_id, date_str)
        contents = regular_menu_contents(menu_response)

        if not contents:
            attempt = ReservationAttempt(False, f"{date_str} 메뉴 없음", target_date)
            self._notify(preferences, attempt)
            return attempt

        # 특식/이벤트 메뉴(별도 카테고리 섹션)는 여기서 제외된다 — 특식만 예약되어 있어도
        # 일반(점심) 메뉴는 별도의 추가 예약으로 취급해 정상 진행해야 한다(hgreenfood-auto-salad 원본과 동일한 정책).
        if any(item.get("booking", {}).get("isBooked") for item in contents):
            attempt = ReservationAttempt(True, "이미 예약되어 있음", target_date, details={"alreadyBooked": True})
            self._notify(preferences, attempt)
            return attempt

        attempted = []
        last_error_message = None
        keywords = preferences.menu_preference or [""]
        for keyword in keywords:
            matched = next((item for item in contents if keyword in item.get("name", "")), None)
            if not matched:
                continue
            attempted.append(keyword)

            result_message = self._try_book(client, store_id, matched, preferences)
            if result_message.success:
                self.config_store.update_last_reserved_date(email, date_str)
                attempt = ReservationAttempt(
                    True, f"{matched['name']} 예약 성공", target_date, attempted, result_message.raw
                )
                self._notify(preferences, attempt)
                return attempt
            last_error_message = result_message.message

        attempt = ReservationAttempt(
            False, last_error_message or "선호 메뉴 중 예약 가능한 항목이 없음", target_date, attempted
        )
        self._notify(preferences, attempt)
        return attempt

    def _try_book(self, client: MealcClient, store_id: str, matched: Dict[str, Any], preferences: UserPreferences):
        from .models import ApiCallResult

        artifact_idx = matched["booking"]["artifactIdx"]
        menu_id = matched["id"]

        spots_response = client.get_shipping_spots(artifact_idx)
        spot = self._pick_spot(spots_response, preferences.delivery_spot_keyword)
        if not spot:
            return ApiCallResult(False, 0, f"배송지('{preferences.delivery_spot_keyword}')를 찾지 못함", {})

        policy = client.get_account_policy()
        day_policy = policy.get("policy", {}).get("day", [])
        if not day_policy:
            return ApiCallResult(False, 0, "식대 정책 조회 실패", {})
        policy_id = day_policy[0]["id"]
        recipient = policy.get("user", {}).get("name", "")
        tel = spots_response.get("previousShipping", {}).get("tel", "")

        check = client.check_booking(artifact_idx)
        if check.get("content", {}).get("status") != "NORMAL":
            return ApiCallResult(False, 0, check.get("content", {}).get("message", "예약 불가 상태"), {})

        return client.book(
            store_id=store_id,
            artifact_idx=artifact_idx,
            menu_id=menu_id,
            spot_key=spot["spotKey"],
            spot_name=spot["spotName"],
            recipient=recipient,
            tel=tel,
            policy_id=policy_id,
        )

    @staticmethod
    def _pick_spot(spots_response: Dict[str, Any], keyword: str) -> Optional[Dict[str, Any]]:
        spots = spots_response.get("spots", [])
        if keyword:
            match = next((s for s in spots if keyword in s.get("spotName", "")), None)
            if match:
                return match
        return spots[0] if spots else None

    def _next_service_date(self, tz, holiday_api_key: Optional[str]) -> date:
        today = datetime.now(tz).date()
        if self.holiday_service:
            return self.holiday_service.next_workday(today, holiday_api_key)
        candidate = today + timedelta(days=1)
        while candidate.weekday() >= 5:
            candidate += timedelta(days=1)
        return candidate

    def _notify(self, preferences: UserPreferences, attempt: ReservationAttempt) -> None:
        if not self.notifier or not preferences.notification_emails:
            return
        weekday_kr = ["월", "화", "수", "목", "금", "토", "일"][attempt.target_date.weekday()]
        status_str = "성공" if attempt.success else "실패"
        subject = f"[식대오토샐러드] {attempt.target_date.isoformat()}({weekday_kr}) 예약 {status_str}"
        body_lines = [
            f"예약 날짜: {attempt.target_date.isoformat()} ({weekday_kr})",
            f"결과: {status_str}",
            f"메시지: {attempt.message}",
            "",
            f"+ 식권대장 계정: {preferences.mealc_user_id}",
            f"+ 선호 메뉴: {', '.join(preferences.menu_preference) or '(미설정)'}",
            f"+ 배송지 키워드: {preferences.delivery_spot_keyword or '(미설정)'}",
            "",
            f"+ 예약 확인 및 설정: {PAGE_URL}",
        ]
        self.notifier.send(subject, "\n".join(body_lines), preferences.notification_emails)
