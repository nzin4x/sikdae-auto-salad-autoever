"""Lambda entrypoints: API Gateway/Function URL 라우팅 + Worker + Holiday 스케줄러."""

from __future__ import annotations

import logging
import os
from datetime import date
from typing import Any, Dict

from core import HolidayService, ReservationService
from immediate_reservation import _build_service
from lambda_http import json_response as _response

LOGGER = logging.getLogger()
if not LOGGER.handlers:
    logging.basicConfig(level=logging.INFO)
LOGGER.setLevel(logging.INFO)


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
    """EventBridge Scheduler(평일 13:00 KST)가 호출 — 활성 회원 전원에 대해 예약 시도."""
    LOGGER.info("=== WORKER HANDLER STARTED ===")
    service = _build_service()
    emails = service.config_store.list_active_users()
    LOGGER.info("Processing %d active users", len(emails))

    results = []
    for idx, email in enumerate(emails, 1):
        LOGGER.info("[%d/%d] Processing %s", idx, len(emails), email)
        try:
            outcome = service.run(email=email)
            results.append(
                {"email": email, "success": outcome.success, "message": outcome.message, "targetDate": outcome.target_date.isoformat()}
            )
        except Exception as error:  # pylint: disable=broad-except
            LOGGER.exception("Reservation attempt failed for %s", email)
            results.append({"email": email, "success": False, "message": str(error)})

    LOGGER.info("Worker completed: %s", results)
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
