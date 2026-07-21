"""즉시 예약 실행 (UI의 '지금 예약하기' 버튼)."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict

from core import ConfigStore, HolidayService, PushNotifier, ReservationService, SesNotifier
from lambda_http import json_response as _response
from lambda_http import parse_body as _parse_body

LOGGER = logging.getLogger()
if not LOGGER.handlers:
    logging.basicConfig(level=logging.INFO)
LOGGER.setLevel(logging.INFO)


def immediate_reservation_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    try:
        body = _parse_body(event)
        email = body.get("email")
        if not email:
            return _response(400, {"message": "email is required"})

        service = _build_service()
        result = service.run(email=email, service_date=None)

        return _response(
            200,
            {
                "success": result.success,
                "message": result.message,
                "targetDate": result.target_date.isoformat(),
                "attemptedMenus": result.attempted_menus,
                "details": result.details,
            },
        )
    except KeyError:
        return _response(404, {"message": "User not found"})
    except Exception as error:
        LOGGER.exception("Error making immediate reservation")
        return _response(500, {"message": str(error)})


def _build_service() -> ReservationService:
    config_store = ConfigStore()
    holiday_endpoint = os.environ.get(
        "HOLIDAY_API_ENDPOINT", "http://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo"
    )
    holiday_service = HolidayService(endpoint=holiday_endpoint, config_store=config_store)
    notifier = SesNotifier() if os.environ.get("SES_SENDER_EMAIL") else None
    push_notifier = PushNotifier() if os.environ.get("VAPID_PRIVATE_KEY") else None
    timezone = os.environ.get("DEFAULT_TIMEZONE", "Asia/Seoul")
    return ReservationService(
        config_store=config_store,
        holiday_service=holiday_service,
        notifier=notifier,
        push_notifier=push_notifier,
        timezone=timezone,
    )
