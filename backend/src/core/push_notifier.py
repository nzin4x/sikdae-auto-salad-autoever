"""Web Push(VAPID) 기반 알림 발송."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from pywebpush import WebPushException, webpush


@dataclass
class PushSendResult:
    success: bool
    expired: bool = False


class PushNotifier:
    def __init__(self, private_key: Optional[str] = None, subject: Optional[str] = None) -> None:
        self.private_key = private_key or os.environ.get("VAPID_PRIVATE_KEY")
        self.subject = subject or os.environ.get("VAPID_SUBJECT")

    def send(self, subscription_info: Dict[str, Any], title: str, body: str, url: str) -> PushSendResult:
        if not self.private_key:
            return PushSendResult(False)
        try:
            webpush(
                subscription_info=subscription_info,
                data=json.dumps({"title": title, "body": body, "url": url}),
                vapid_private_key=self.private_key,
                vapid_claims={"sub": self.subject},
            )
            return PushSendResult(True)
        except WebPushException as error:
            status_code = getattr(error.response, "status_code", None)
            print(f"Web push send failed: {error}")
            return PushSendResult(False, expired=status_code in (404, 410))
