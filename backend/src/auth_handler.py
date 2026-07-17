"""이메일 인증코드 발송/검증 + 디바이스 자동로그인."""

from __future__ import annotations

import logging
import secrets
from typing import Any, Dict

from core import PAGE_URL, ConfigStore
from lambda_http import json_response as _response
from lambda_http import parse_body as _parse_body

LOGGER = logging.getLogger()
if not LOGGER.handlers:
    logging.basicConfig(level=logging.INFO)
LOGGER.setLevel(logging.INFO)


def send_verification_code_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    """이메일 인증 코드 발송"""
    try:
        body = _parse_body(event)
        email = body.get("email")
        if not email:
            return _response(400, {"message": "Email is required"})

        code = f"{secrets.randbelow(1000000):06d}"
        config_store = ConfigStore()
        config_store.save_verification_code(email, code)

        from core import SesNotifier

        notifier = SesNotifier()
        notifier.send(
            "[식대오토샐러드] 로그인 인증 코드",
            f"인증 코드: {code}\n\n이 코드는 10분간 유효합니다.\n\n👉 {PAGE_URL}",
            [email],
        )
        LOGGER.info("Verification code sent to %s", email)
        return _response(200, {"message": "Verification code sent", "email": email})
    except Exception as error:
        LOGGER.exception("Error sending verification code")
        return _response(500, {"message": str(error)})


def verify_code_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    """인증 코드 검증 + 회원가입 여부 확인 + 디바이스 등록"""
    try:
        body = _parse_body(event)
        email = body.get("email")
        code = body.get("code")
        device_fingerprint = body.get("deviceFingerprint")

        if not email or not code:
            return _response(400, {"message": "Email and code are required"})

        config_store = ConfigStore()
        stored = config_store.get_verification_code(email)
        if not stored:
            return _response(401, {"message": "Invalid or expired verification code"})
        if stored.get("code") != code:
            return _response(401, {"message": "Invalid verification code"})

        config_store.delete_verification_code(email)

        has_account = config_store.profile_exists(email)
        if has_account and device_fingerprint:
            config_store.register_device(email, device_fingerprint)

        return _response(200, {"message": "Verification successful", "email": email, "hasAccount": has_account})
    except Exception as error:
        LOGGER.exception("Error verifying code")
        return _response(500, {"message": str(error)})


def check_device_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    """디바이스 지문으로 자동 로그인 확인"""
    try:
        body = _parse_body(event)
        device_fingerprint = body.get("deviceFingerprint")
        if not device_fingerprint:
            return _response(400, {"message": "Device fingerprint is required"})

        config_store = ConfigStore()
        email = config_store.find_user_by_device(device_fingerprint)
        if not email:
            return _response(200, {"authenticated": False})

        config_store.update_device_access(email, device_fingerprint)
        return _response(200, {"authenticated": True, "email": email})
    except Exception as error:
        LOGGER.exception("Error checking device")
        return _response(500, {"message": str(error)})
