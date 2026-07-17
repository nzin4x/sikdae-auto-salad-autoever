"""Data models shared by the Mealc(식권대장) client."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional


@dataclass
class LoginResult:
    success: bool
    message: str
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expire_time: Optional[int] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ApiCallResult:
    success: bool
    status_code: int
    message: Optional[str]
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UserPreferences:
    """DynamoDB에 저장되는 sikdae-auto 회원 1명의 설정."""

    email: str
    mealc_user_id: str
    mealc_password: str
    menu_preference: List[str] = field(default_factory=list)  # 메뉴 이름에 포함될 키워드 순서, 예: ["샌드위치", "샐러드"]
    delivery_spot_keyword: str = ""  # 예: "4층" — 배송지 목록에서 이 문자열이 포함된 spot 선택
    store_id: Optional[str] = None  # 미지정 시 BOOKING 지원 매장 자동 탐색
    exclusion_dates: List[str] = field(default_factory=list)  # ISO 포맷 (YYYY-MM-DD)
    is_active: bool = True
    notification_emails: List[str] = field(default_factory=list)
    last_reserved_date: Optional[str] = None


@dataclass
class ReservationAttempt:
    success: bool
    message: str
    target_date: date
    attempted_menus: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)
