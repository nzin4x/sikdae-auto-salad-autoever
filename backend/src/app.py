"""Lambda entrypoints: API Gateway/Function URL 라우팅 + Worker + Holiday 스케줄러."""

from __future__ import annotations

import logging
import os
import time
from datetime import date
from typing import Any, Dict

from core import HolidayService, ReservationService
from immediate_reservation import _build_service
from lambda_http import json_response as _response

LOGGER = logging.getLogger()
if not LOGGER.handlers:
    logging.basicConfig(level=logging.INFO)
LOGGER.setLevel(logging.INFO)

# Lambda의 실행시간 하드캡은 900초(15분) — 아무리 Timeout을 늘려도 이 이상은 못 돈다.
# 마지막 라운드의 실제 처리시간 + 알림 발송 여유를 남기기 위해 재시도 예산은 그보다 짧게 잡는다.
WORKER_MAX_ELAPSED_SECONDS = 840  # 14분
WORKER_INITIAL_DELAY_SECONDS = 1


def api_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    route = event.get("resource") or event.get("rawPath") or ""
    LOGGER.info("API request: %s", route)

    routes = {
        "/register": ("register_user", "register_user_handler"),
        "/register/status": ("get_registration_status", "get_registration_status_handler"),
        "/check-reservation": ("check_reservation", "check_reservation_handler"),
        "/reservations": ("list_reservations", "list_reservations_handler"),
        "/auth/send-code": ("auth_handler", "send_verification_code_handler"),
        "/auth/verify-code": ("auth_handler", "verify_code_handler"),
        "/auth/check-device": ("auth_handler", "check_device_handler"),
        "/auth/logout": ("logout_handler", "logout_handler"),
        "/user/toggle-auto-reservation": ("toggle_auto_reservation", "toggle_auto_reservation_handler"),
        "/user/delete-account": ("delete_account", "delete_account_handler"),
        "/user/get-settings": ("get_user_settings", "get_user_settings_handler"),
        "/user/update-settings": ("update_user_settings", "update_user_settings_handler"),
        "/user/update-exclusion-dates": ("update_exclusion_dates", "update_exclusion_dates_handler"),
        "/reservation/make-immediate": ("immediate_reservation", "immediate_reservation_handler"),
        "/reservation/cancel": ("cancel_reservation", "cancel_reservation_handler"),
        "/stats": ("get_stats", "get_stats_handler"),
    }

    if route == "/admin/update-holidays":
        return update_holidays_handler(event, _context)

    target = routes.get(route)
    if not target:
        return _response(404, {"message": f"Unknown route: {route}"})

    module_name, func_name = target
    module = __import__(module_name, fromlist=[func_name])
    handler = getattr(module, func_name)
    return handler(event, _context)


def worker_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    """EventBridge Scheduler(평일 13:00 KST)가 호출 — 활성 회원 전원에 대해 예약 시도.

    정각 직후엔 Mealc 서버(당일 메뉴 게시 등)가 아직 준비되지 않아 실패하는 경우가 있어,
    전체 회원을 한 라운드로 묶어 1s, 2s, 4s, 8s, ... 로 대기시간을 지수 증가시키며
    재시도 가능한(retryable) 실패만 다음 라운드에 다시 시도한다. 대기시간은 회원별이
    아니라 전체가 공유하므로, 회원 수가 늘어도 총 소요시간이 곱해지지 않는다.
    Lambda 실행시간 하드캡(15분)을 넘지 않도록 WORKER_MAX_ELAPSED_SECONDS로 예산을 제한한다.
    """
    LOGGER.info("=== WORKER HANDLER STARTED ===")
    service = _build_service()
    emails = service.config_store.list_active_users()
    LOGGER.info("Processing %d active users", len(emails))

    outcomes: Dict[str, Any] = {}
    pending = list(emails)
    delay = WORKER_INITIAL_DELAY_SECONDS
    start = time.monotonic()
    round_num = 0

    while pending:
        round_num += 1
        LOGGER.info("Round %d: %d user(s) pending", round_num, len(pending))
        still_pending = []
        for email in pending:
            try:
                outcome = service.run(email=email, notify_on_retryable_failure=False)
                outcomes[email] = outcome
                if outcome.retryable:
                    still_pending.append(email)
            except Exception:  # pylint: disable=broad-except
                LOGGER.exception("Reservation attempt failed for %s", email)
                still_pending.append(email)
        pending = still_pending

        if not pending:
            break

        remaining_budget = WORKER_MAX_ELAPSED_SECONDS - (time.monotonic() - start)
        if remaining_budget <= 0:
            LOGGER.warning("Retry budget exhausted with %d user(s) still pending", len(pending))
            break

        sleep_for = min(delay, remaining_budget)
        LOGGER.info("Retrying %d user(s) after %.0fs", len(pending), sleep_for)
        time.sleep(sleep_for)
        delay *= 2

    # 예산을 다 쓰고도 재시도 대상으로 남은 회원에게는 최종 실패를 통지한다.
    for email in pending:
        outcome = outcomes.get(email)
        if outcome is not None:
            try:
                service.notify_final_outcome(email, outcome)
            except Exception:  # pylint: disable=broad-except
                LOGGER.exception("Failed to send final-failure notification for %s", email)

    results = [
        {
            "email": email,
            "success": outcome.success if outcome else False,
            "message": outcome.message if outcome else "처리되지 않음",
            "targetDate": outcome.target_date.isoformat() if outcome else None,
        }
        for email, outcome in ((e, outcomes.get(e)) for e in emails)
    ]

    LOGGER.info("Worker completed after %d round(s): %s", round_num, results)
    return {"results": results}


def update_holidays_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    from lambda_http import parse_body

    try:
        payload = parse_body(event)
        today = date.today()
        year = int(payload.get("year", today.year))
        month = int(payload.get("month", today.month))

        api_key = os.environ.get("HOLIDAY_API_KEY")
        if not api_key:
            return _response(500, {"message": "Holiday API key not configured"})

        service = _build_service()
        holidays = service.holiday_service.fetch_and_save_holidays(year, month, api_key)
        return _response(200, {"message": "Holidays updated", "year": year, "month": month, "holidays": list(holidays)})
    except Exception as error:
        LOGGER.exception("Failed to update holidays")
        return _response(500, {"message": str(error)})


def holiday_scheduler_handler(event: Dict[str, Any], _context: Any) -> None:
    """매월 1회 다음 달 공휴일을 미리 캐싱한다."""
    LOGGER.info("Holiday scheduler triggered")
    today = date.today()
    next_year, next_month = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)

    api_key = os.environ.get("HOLIDAY_API_KEY")
    if not api_key:
        LOGGER.error("Holiday API key not configured")
        return

    service = _build_service()
    try:
        holidays = service.holiday_service.fetch_and_save_holidays(next_year, next_month, api_key)
        LOGGER.info("Updated holidays for %s-%s: %s", next_year, next_month, holidays)
    except Exception:
        LOGGER.exception("Failed to update holidays for %s-%s", next_year, next_month)
