"""공개 통계 — 회원 개인정보 노출 없이 집계 수치만 반환한다."""

from __future__ import annotations

import logging
import os
from datetime import date
from typing import Any, Dict

from core import ConfigStore
from lambda_http import json_response as _response

LOGGER = logging.getLogger()
if not LOGGER.handlers:
    logging.basicConfig(level=logging.INFO)
LOGGER.setLevel(logging.INFO)

WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]


def get_stats_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    try:
        today = date.today()
        config_store = ConfigStore()

        stats = config_store.get_stats(exclusion_dates_from=today.isoformat())
        stats["maxUsers"] = int(os.environ.get("MAX_USERS", "10"))

        holiday_dates = sorted(config_store.get_holidays(today.year, today.month) or [])
        stats["holidaysThisMonth"] = [_format_holiday(d) for d in holiday_dates]

        return _response(200, stats)
    except Exception as error:
        LOGGER.exception("Error getting stats")
        return _response(500, {"message": str(error)})


def _format_holiday(yyyymmdd: str) -> Dict[str, str]:
    d = date(int(yyyymmdd[:4]), int(yyyymmdd[4:6]), int(yyyymmdd[6:8]))
    return {"date": d.isoformat(), "weekday": WEEKDAY_KR[d.weekday()]}
