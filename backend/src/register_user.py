"""회원가입 핸들러 — Mealc 계정 유효성을 실제 로그인으로 검증 후 저장.

마스터 패스워드는 사용자가 직접 정하며, 서버에는 PBKDF2 해시만 저장한다(평문/복호화형 저장 안 함).
분실 시 복구 수단이 없으므로 재가입해야 한다. 식권대장 비밀번호와 동일하면 거부한다.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict

from core import ConfigStore, MealcClient, UserPreferences
from core.crypto import hash_master_password
from lambda_http import json_response as _response
from lambda_http import parse_body as _parse_body

LOGGER = logging.getLogger()
if not LOGGER.handlers:
    logging.basicConfig(level=logging.INFO)
LOGGER.setLevel(logging.INFO)

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
MIN_MASTER_PASSWORD_LENGTH = 8


def register_user_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    try:
        body = _parse_body(event)
        LOGGER.info(
            "Register payload: %s",
            {k: ("***" if k in ("mealcPassword", "masterPassword") else v) for k, v in body.items()},
        )

        required = ["email", "mealcUserId", "mealcPassword", "masterPassword", "menuPreference", "deliverySpotKeyword"]
        missing = [f for f in required if not body.get(f)]
        if missing:
            return _response(400, {"message": f"Missing fields: {', '.join(missing)}"})

        email = body["email"]
        if not EMAIL_RE.match(email):
            return _response(400, {"message": "Invalid email format"})

        mealc_password = body["mealcPassword"]
        master_password = body["masterPassword"]

        if len(master_password) < MIN_MASTER_PASSWORD_LENGTH:
            return _response(400, {"message": f"마스터 패스워드는 {MIN_MASTER_PASSWORD_LENGTH}자 이상이어야 합니다"})
        if master_password == mealc_password:
            return _response(400, {"message": "마스터 패스워드는 식권대장 비밀번호와 달라야 합니다"})

        config_store = ConfigStore()
        if config_store.profile_exists(email):
            return _response(409, {"message": "Already registered"})

        mealc_user_id = body["mealcUserId"]

        LOGGER.info("Validating Mealc credentials via real login")
        client = MealcClient()
        login_result = client.login(mealc_user_id, mealc_password)
        if not login_result.success:
            return _response(400, {"message": f"식권대장 로그인 실패: {login_result.message}"})

        master_password_hash, master_password_salt = hash_master_password(master_password)

        preferences = UserPreferences(
            email=email,
            mealc_user_id=mealc_user_id,
            mealc_password=mealc_password,
            master_password_hash=master_password_hash,
            master_password_salt=master_password_salt,
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
            "sikdae-auto 가입 완료",
            (
                "가입이 완료되었습니다.\n\n"
                "마스터 패스워드는 서버에 해시(단방향 암호화)로만 저장되며, 평문으로는 어디에도 저장되지 않습니다.\n"
                "잊어버리면 복구할 수 없으니 새로 가입해야 합니다.\n"
                "믿기지 않으시면 GitHub 소스코드(core/crypto.py의 hash_master_password)를 직접 확인해보세요."
            ),
            [email],
        )

        return _response(
            200,
            {
                "message": "User registered successfully",
                "email": email,
                "notice": "마스터 패스워드는 서버에 저장되지 않습니다(해시만 저장). 잊어버리면 재가입해야 합니다.",
            },
        )
    except Exception as error:
        LOGGER.exception("Error registering user")
        return _response(500, {"message": str(error)})
