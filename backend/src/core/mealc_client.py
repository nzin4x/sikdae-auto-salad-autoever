"""HTTP client encapsulating the Mealc(식권대장) login APIs.

Endpoints and payload shapes reverse-engineered from real app traffic
(mitmproxy + Frida TrustManager bypass on a rooted MuMu Player instance).
See docs/api_notes.md for the full sequence.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, Optional

import requests

from .crypto import encrypt_password_oaep, encrypt_password_pkcs1v15, sign_secure_data
from .models import ApiCallResult, LoginResult

OAUTH_BASE_URL = "https://oauth.sikdae.com"
API_BASE_URL = "https://api.sikdae.com"

# App-embedded constants captured from real Mealc(식권대장) Android app traffic.
# These identify the client application itself (baked into every install),
# not any individual user account.
CLIENT_ID = "66BF21D3-C4D0-4EB2-BA95-8ECBC5392681"
CLIENT_SECRET = "fneDHgNPDnKI75Pj01AFtC9MLAHGRzlPvHiT7EdBIVwxmFPqfsSXC8gvHKt84YNH"
DEFAULT_KMS_KEY_ID = "019A9FE4-3BA4-7AAE-BDFD-B54DA102D536"

_PASSWORD_ENCRYPTORS = {
    "pkcs1v15": encrypt_password_pkcs1v15,
    "oaep": encrypt_password_oaep,
}


class MealcClient:
    def __init__(
        self,
        session: Optional[requests.Session] = None,
        timeout: int = 10,
        app_installation: Optional[str] = None,
    ) -> None:
        self.session = session or requests.Session()
        # Windows 시스템 프록시(mitmproxy 캡처용으로 켜져 있을 수 있음)를 우회한다.
        self.session.trust_env = False
        self.timeout = timeout
        self.app_installation = app_installation or str(uuid.uuid4())
        self.sikdae_guid = ""
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None

    def check_sso(self, username: str) -> Dict[str, Any]:
        url = f"{OAUTH_BASE_URL}/sso/v2"
        response = self.session.get(
            url, params={"signId": username}, headers=self._headers(), timeout=self.timeout
        )
        return self._safe_json(response)

    def get_public_key(self, kms_key_id: str = DEFAULT_KMS_KEY_ID) -> str:
        url = f"{OAUTH_BASE_URL}/open/v2/kms/public/{kms_key_id}"
        response = self.session.get(url, headers=self._headers(), timeout=self.timeout)
        return self._safe_json(response)["publicKey"]

    def login(
        self,
        username: str,
        password: str,
        kms_key_id: str = DEFAULT_KMS_KEY_ID,
        password_padding: str = "pkcs1v15",
    ) -> LoginResult:
        sso = self.check_sso(username)
        if sso.get("sso"):
            return LoginResult(False, f"SSO 로그인 대상 계정입니다: {sso.get('url')}", raw=sso)

        public_key = self.get_public_key(kms_key_id)
        encryptor = _PASSWORD_ENCRYPTORS[password_padding]
        encrypted_password = encryptor(password, public_key)

        payload = {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "password",
            "username": username,
            "password": encrypted_password,
        }
        url = f"{OAUTH_BASE_URL}/vendys/v2/token"
        response = self.session.post(
            url, data=json.dumps(payload), headers=self._headers(), timeout=self.timeout
        )
        body = self._safe_json(response)

        if response.status_code == 201 and body.get("access_token"):
            self.access_token = body["access_token"]
            self.refresh_token = body.get("refresh_token")
            self.sikdae_guid = body.get("account", {}).get("guid", "")
            return LoginResult(
                True,
                "로그인 성공",
                access_token=self.access_token,
                refresh_token=self.refresh_token,
                expire_time=body.get("expire_time"),
                raw=body,
            )

        message = body.get("error_description") or body.get("message") or response.text
        return LoginResult(False, message or f"로그인 실패 (status={response.status_code})", raw=body)

    def get_me(self) -> ApiCallResult:
        """인증된 세션이 실제로 유효한지 확인하기 위한 최소 조회 호출."""
        url = f"{API_BASE_URL}/app/v2/me"
        response = self.session.get(
            url, headers=self._headers(authenticated=True), timeout=self.timeout
        )
        body = self._safe_json(response)
        return ApiCallResult(response.status_code == 200, response.status_code, body.get("message"), body)

    # ---- 예약(주문) 관련 API ----

    def get_store_list(self) -> Dict[str, Any]:
        url = f"{API_BASE_URL}/store/v5"
        response = self.session.get(url, headers=self._headers(authenticated=True), timeout=self.timeout)
        return self._safe_json(response)

    def find_booking_store_id(self) -> Optional[str]:
        """배달식사(BOOKING) 매장 id를 자동으로 찾는다. 여러 개면 첫 번째를 반환."""
        stores = self.get_store_list().get("stores", [])
        for store in stores:
            if any(t.get("code") == "BOOKING" for t in store.get("supplyTypes", [])):
                return store["id"]
        return None

    def get_account_policy(self) -> Dict[str, Any]:
        """유저 정보(이름) 및 식대 정책 id(policy.day[0].id) 조회."""
        url = f"{API_BASE_URL}/account/v4/policy"
        response = self.session.get(url, headers=self._headers(authenticated=True), timeout=self.timeout)
        return self._safe_json(response)

    def get_store_menu(self, store_id: str, date: str) -> Dict[str, Any]:
        """date는 YYYY-MM-DD. 응답의 각 메뉴 항목에 booking.artifactIdx가 들어있다."""
        url = f"{API_BASE_URL}/store/v5/{store_id}/menu"
        response = self.session.get(
            url, params={"date": date}, headers=self._headers(authenticated=True), timeout=self.timeout
        )
        return self._safe_json(response)

    def get_shipping_spots(self, artifact_idx: int) -> Dict[str, Any]:
        url = f"{API_BASE_URL}/company/v1/shipping/spots"
        response = self.session.get(
            url,
            params={"artifactIdx": artifact_idx},
            headers=self._headers(authenticated=True),
            timeout=self.timeout,
        )
        return self._safe_json(response)

    def check_booking(self, artifact_idx: int) -> Dict[str, Any]:
        """예약 가능 여부/중복 확인. 실제 주문을 만들지는 않는 안전한 조회."""
        url = f"{API_BASE_URL}/booking/v1/book/check/{artifact_idx}"
        response = self.session.get(url, headers=self._headers(authenticated=True), timeout=self.timeout)
        return self._safe_json(response)

    def get_pointbook_list(self, start_date: str, end_date: str, page: int = 1, page_row: int = 20) -> Dict[str, Any]:
        """결제(예약) 내역 목록. 날짜는 YYYY-MM-DD."""
        url = f"{API_BASE_URL}/account/v3/pointbook"
        params = {
            "page": page,
            "pageRow": page_row,
            "searchSupplyType": "",
            "searchState": "",
            "startDate": start_date,
            "endDate": end_date,
        }
        response = self.session.get(url, params=params, headers=self._headers(authenticated=True), timeout=self.timeout)
        return self._safe_json(response)

    def get_pointbook_detail(self, coupon_id: str) -> Dict[str, Any]:
        """결제 상세. historyInfo.historyIdx가 cancel_booking()에 필요하다."""
        url = f"{API_BASE_URL}/account/v2/pointbook/{coupon_id}"
        response = self.session.get(url, headers=self._headers(authenticated=True), timeout=self.timeout)
        return self._safe_json(response)

    def get_cancel_confirm(self, coupon_id: str) -> Dict[str, Any]:
        """취소 시 환불 금액/기본 취소 사유 목록 조회. 부작용 없는 조회."""
        url = f"{API_BASE_URL}/payment/v1/cancel/{coupon_id}/confirm"
        response = self.session.get(url, headers=self._headers(authenticated=True), timeout=self.timeout)
        return self._safe_json(response)

    def cancel_booking(self, history_idx: int, coupon_id: str, cancel_message: str) -> ApiCallResult:
        """실제 예약을 취소한다 — 식대포인트가 즉시 환불되는 실사용 액션이다."""
        url = f"{API_BASE_URL}/booking/v3/book/{history_idx}"
        payload = {"roomIdx": 0, "couponId": coupon_id, "cancelMessage": cancel_message}
        response = self.session.put(
            url, data=json.dumps(payload), headers=self._headers(authenticated=True), timeout=self.timeout
        )
        body = self._safe_json(response)
        is_canceled = body.get("content", {}).get("shipping", {}).get("shippingStatus") == "CANCELED"
        return ApiCallResult(response.status_code == 200 and is_canceled, response.status_code, body.get("message"), body)

    def book(
        self,
        store_id: str,
        artifact_idx: int,
        menu_id: str,
        spot_key: str,
        spot_name: str,
        recipient: str,
        tel: str,
        policy_id: int,
        quantity: int = 1,
    ) -> ApiCallResult:
        """실제 예약(주문)을 생성한다 — 식대포인트 1점이 차감되는 실사용 액션이다.

        secureData JWT는 앱과 동일하게 HS256으로 서명하며, 서명 키는
        로그인한 사용자 본인의 계정 guid(self.sikdae_guid)다.
        """
        payload = {
            "bookingArtifactIdx": artifact_idx,
            "date": 0,
            "roomIdx": 0,
            "shipping": {
                "addressDetail": "",
                "addressIdx": "",
                "defaultSpot": False,
                "deliveryRequirementMemo": "",
                "fee": 0,
                "isChangeShippingAddress": False,
                "jibunAddress": "",
                "recipient": recipient,
                "roadAddress": "",
                "shippingLocation": "NONE",
                "shippingType": "BOOKING",
                "spotKey": spot_key,
                "spotName": spot_name,
                "tel": tel,
                "zonecode": "",
            },
            "sid": store_id,
            "store": {
                "artifactIdx": 0,
                "categoryId": 0,
                "categoryRow": False,
                "categorySelected": False,
                "id": store_id,
                "invisible": False,
                "like": False,
                "likedRow": False,
                "menu": [
                    {
                        "categoryRow": False,
                        "count": quantity,
                        "id": menu_id,
                        "isHeader": False,
                        "name": "",
                        "price": 0,
                        "quantity": 0,
                        "salesPrice": 0,
                    }
                ],
                "supplyType": 0,
            },
            "totalPrice": 0,
            "type": "MENU",
            "uid": self.sikdae_guid,
            "user": {
                "amount": 0,
                "division": "",
                "doDistributeAmount": False,
                "id": self.sikdae_guid,
                "initAmount": 0,
                "isAgree": False,
                "isDistributeAmountLock": False,
                "isDistributeComplete": False,
                "isInfinite": False,
                "isLeader": False,
                "mypoint": {"amount": 0, "policy": 0},
                "name": recipient,
                "payType": 0,
                "point": [{"amount": quantity, "policy": policy_id}],
                "type": "",
                "userIndex": 0,
                "userInfo": {
                    "amount": 0,
                    "division": "",
                    "id": "",
                    "isAgree": False,
                    "isInfinite": False,
                    "isLeader": False,
                    "mypoint": {"amount": 0, "policy": 0},
                    "name": "",
                    "point": [],
                    "type": "",
                    "userIndex": 0,
                },
            },
        }
        secure_data = sign_secure_data(payload, self.sikdae_guid)

        url = f"{API_BASE_URL}/booking/v6/book"
        response = self.session.post(
            url,
            data=json.dumps({"secureData": secure_data}),
            headers=self._headers(authenticated=True),
            timeout=self.timeout,
        )
        body = self._safe_json(response)
        return ApiCallResult(response.status_code == 201, response.status_code, body.get("message"), body)

    def _headers(self, authenticated: bool = False) -> Dict[str, str]:
        ua = self._device_user_agent()
        headers = {
            "Content-Type": "application/json",
            "X-Sikdae-Guid": self.sikdae_guid,
            "X-User-Agent": ua,
            "User-Agent": ua,
            "Accept-Language": "ko",
            "App-Session": str(int(time.time() * 1000)),
            "App-Installation": self.app_installation,
        }
        if authenticated and self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    @staticmethod
    def _device_user_agent() -> str:
        device_info = {
            "client": "SikdaeUser",
            "clientVersion": "3.129.1",
            "os": "Android",
            "osVersion": "15(35)",
            "deviceModel": "SM-A156E",
            "net": "wifi",
            "vendys-ad-id": str(uuid.uuid4()),
        }
        return "Vendys/1.0" + json.dumps(device_info, separators=(",", ":"))

    @staticmethod
    def _safe_json(response: requests.Response) -> Dict[str, Any]:
        try:
            return response.json()
        except ValueError:
            return {}
