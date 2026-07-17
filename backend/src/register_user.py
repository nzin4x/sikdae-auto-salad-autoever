"""회원가입 핸들러 — Mealc 계정 유효성을 실제 로그인으로 검증 후 저장.

식권대장 비밀번호는 DynamoDB에 CRYPTO_KEY(Lambda 환경변수)로 암호화되어 저장된다.
이 키에 접근 가능한 관리자는 언제든 복호화할 수 있으므로(사람 개입 없는 13시 자동예약을
위해 불가피한 구조), 노출되어도 크게 지장이 없는 비밀번호로 식권대장 앱에서 변경한 뒤
가입할 것을 안내한다.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict

from core import PAGE_URL, ConfigStore, MealcClient, UserPreferences
from lambda_http import json_response as _response
from lambda_http import parse_body as _parse_body

LOGGER = logging.getLogger()
if not LOGGER.handlers:
    logging.basicConfig(level=logging.INFO)
LOGGER.setLevel(logging.INFO)

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

SECURITY_NOTICE = (
    "식권대장 비밀번호는 암호화되어 저장되지만, 서버 관리자는 암호화 키로 언제든 복호화할 수 있습니다. "
    "노출되어도 크게 지장이 없는 비밀번호로 식권대장 앱에서 먼저 변경한 뒤 가입해주세요."
)


def register_user_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    try:
        body = _parse_body(event)
        LOGGER.info(
            "Register payload: %s",
            {k: ("***" if k == "mealcPassword" else v) for k, v in body.items()},
        )

        required = ["email", "mealcUserId", "mealcPassword", "menuPreference", "deliverySpotKeyword"]
        missing = [f for f in required if not body.get(f)]
        if missing:
            return _response(400, {"message": f"Missing fields: {', '.join(missing)}"})

        email = body["email"]
        if not EMAIL_RE.match(email):
            return _response(400, {"message": "Invalid email format"})

        mealc_password = body["mealcPassword"]

        config_store = ConfigStore()
        if config_store.profile_exists(email):
            return _response(409, {"message": "Already registered"})

        max_users = int(os.environ.get("MAX_USERS", "10"))
        if config_store.count_users() >= max_users:
            return _response(403, {"message": f"회원 정원({max_users}명)이 가득 찼습니다"})

        mealc_user_id = body["mealcUserId"]

        LOGGER.info("Validating Mealc credentials via real login")
        client = MealcClient()
        login_result = client.login(mealc_user_id, mealc_password)
        if not login_result.success:
            return _response(400, {"message": f"식권대장 로그인 실패: {login_result.message}"})

        preferences = UserPreferences(
            email=email,
            mealc_user_id=mealc_user_id,
            mealc_password=mealc_password,
            menu_preference=body["menuPreference"],
            delivery_spot_keyword=body["deliverySpotKeyword"],
            store_id=body.get("storeId"),
            exclusion_dates=body.get("exclusionDates", []),
            is_active=True,
            notification_emails=[email],
        )
        config_store.save_user_preferences(preferences)

        device_fingerprint = body.get("deviceFingerprint")
        if device_fingerprint:
            config_store.register_device(email, device_fingerprint)

        from core import SesNotifier

        SesNotifier().send(
            "[식대오토샐러드] 가입 완료",
            f"가입이 완료되었습니다.\n\n⚠️ {SECURITY_NOTICE}\n\n👉 {PAGE_URL}",
            [email],
        )

        return _response(
            200,
            {"message": "User registered successfully", "email": email, "notice": SECURITY_NOTICE},
        )
    except Exception as error:
        LOGGER.exception("Error registering user")
        return _response(500, {"message": str(error)})
