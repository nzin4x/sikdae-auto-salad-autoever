"""회원 탈퇴 — 단순 삭제. 노출될 민감정보가 없으므로(비밀번호 등은 지워지기만 함) 별도 인증 확인은 요구하지 않는다."""

from __future__ import annotations

import logging
from typing import Any, Dict

from core import ConfigStore
from lambda_http import json_response as _response
from lambda_http import parse_body as _parse_body

LOGGER = logging.getLogger()
if not LOGGER.handlers:
    logging.basicConfig(level=logging.INFO)
LOGGER.setLevel(logging.INFO)


def delete_account_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    try:
        body = _parse_body(event)
        email = body.get("email")
        if not email:
            return _response(400, {"message": "email is required"})

        config_store = ConfigStore()
        config_store.delete_profile(email)
        return _response(200, {"message": "Account deleted successfully", "email": email})
    except Exception as error:
        LOGGER.exception("Error deleting account")
        return _response(500, {"message": str(error)})
