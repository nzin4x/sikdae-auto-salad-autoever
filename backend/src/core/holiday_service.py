"""data.go.kr 공휴일 API 래퍼 (DynamoDB 캐싱)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date, timedelta
from typing import Any, Dict, Optional, Set

import requests


class HolidayService:
    def __init__(
        self,
        endpoint: str = "http://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo",
        session: Optional[requests.Session] = None,
        timeout: int = 10,
        config_store: Optional[Any] = None,
    ) -> None:
        self.endpoint = endpoint
        self.session = session or requests.Session()
        self.timeout = timeout
        self.config_store = config_store
        self._cache: Dict[str, Set[str]] = {}

    def is_holiday(self, target: date, api_key: Optional[str]) -> bool:
        if not api_key:
            return False

        key = target.strftime("%Y%m")
        if key in self._cache:
            return target.strftime("%Y%m%d") in self._cache[key]

        if self.config_store:
            stored = self.config_store.get_holidays(target.year, target.month)
            if stored is not None:
                self._cache[key] = stored
                return target.strftime("%Y%m%d") in stored

        month_dates = self._fetch_month(target.year, target.month, api_key)
        self._cache[key] = month_dates

        if self.config_store:
            try:
                self.config_store.save_holidays(target.year, target.month, month_dates)
            except Exception:
                pass

        return target.strftime("%Y%m%d") in month_dates

    def next_workday(self, after: date, api_key: Optional[str], inclusive: bool = False) -> date:
        """주말과 (api_key가 있으면) 공휴일을 건너뛴 다음 근무일을 반환한다.

        inclusive=True면 after 당일도 후보에 포함(당일이 근무일이면 당일 반환),
        기본(False)은 hgreenfood 원본과 동일하게 after의 '다음 날'부터 탐색한다.
        """
        candidate = after if inclusive else after + timedelta(days=1)
        while True:
            if candidate.weekday() < 5 and not self.is_holiday(candidate, api_key):
                return candidate
            candidate += timedelta(days=1)

    def fetch_and_save_holidays(self, year: int, month: int, api_key: str) -> Set[str]:
        dates = self._fetch_month(year, month, api_key)
        if self.config_store:
            self.config_store.save_holidays(year, month, dates)
        return dates

    def _fetch_month(self, year: int, month: int, api_key: str) -> Set[str]:
        params = {"serviceKey": api_key, "solYear": str(year), "solMonth": f"{month:02d}"}
        response = self.session.get(self.endpoint, params=params, timeout=self.timeout)
        response.raise_for_status()
        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as exc:
            raise RuntimeError("Failed to parse holiday API response") from exc

        result_code = root.findtext(".//resultCode")
        if result_code and result_code != "00":
            result_msg = root.findtext(".//resultMsg") or "Unknown error"
            raise RuntimeError(f"Holiday API error {result_code}: {result_msg}")

        # data.go.kr는 실제 쉬는 공휴일뿐 아니라 제헌절처럼 쉬지 않는 "기념일"도 같이 내려준다.
        # isHoliday == 'Y'인 것만 실제 공휴일로 취급해야 한다(아니면 평일인데 건너뛰는 버그가 생김).
        holidays = set()
        for item in root.findall(".//item"):
            locdate = item.findtext("locdate")
            is_holiday = item.findtext("isHoliday")
            if locdate and is_holiday == "Y":
                holidays.add(locdate)
        return holidays
