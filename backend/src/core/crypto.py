"""RSA password encryption matching the Mealc(식권대장) Android app.

The app fetches a public key from `oauth.sikdae.com/open/v2/kms/public/{id}`
(base64 DER, X.509 SubjectPublicKeyInfo, RSA 2048bit) and encrypts the plaintext
password with it before sending it to `/vendys/v2/token`. The padding scheme
could not be determined from captured traffic alone (no private key available);
PKCS1v15 is tried first since it's the most common choice for this class of
Korean apps, with OAEP variants as fallback.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from typing import Tuple

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes, serialization

MASTER_PASSWORD_PBKDF2_ITERATIONS = 200_000


def _load_public_key(public_key_b64: str):
    der_bytes = base64.b64decode(public_key_b64)
    return serialization.load_der_public_key(der_bytes)


def encrypt_password_pkcs1v15(password: str, public_key_b64: str) -> str:
    public_key = _load_public_key(public_key_b64)
    ciphertext = public_key.encrypt(password.encode("utf-8"), padding.PKCS1v15())
    return base64.b64encode(ciphertext).decode("ascii")


def encrypt_password_oaep(password: str, public_key_b64: str, algorithm=hashes.SHA1()) -> str:
    public_key = _load_public_key(public_key_b64)
    ciphertext = public_key.encrypt(
        password.encode("utf-8"),
        padding.OAEP(mgf=padding.MGF1(algorithm=algorithm), algorithm=algorithm, label=None),
    )
    return base64.b64encode(ciphertext).decode("ascii")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def sign_secure_data(payload: dict, key: str) -> str:
    """앱의 JWTUtil.signature()와 동일한 HS256 JWT를 생성한다.

    앱 디컴파일(JWTUtil.java) 결과, 서명 키는 별도 비밀값이 아니라
    **로그인한 사용자 본인의 계정 guid**(로그인 응답의 account.guid,
    X-Sikdae-Guid 헤더와 동일한 값)이다. 실제 캡처된 토큰으로 HMAC-SHA256
    재계산 검증까지 완료함(docs/api_notes.md 참고).
    """
    header_b64 = _b64url(json.dumps({"alg": "HS256"}, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = hmac.new(key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header_b64}.{payload_b64}.{_b64url(signature)}"


def _get_fernet() -> Fernet:
    """CRYPTO_KEY 환경변수(Fernet.generate_key() 형식, base64 32바이트)로 초기화한다.

    KMS 대신 Lambda 환경변수 키를 쓰는 방식 — 비용은 $0이지만, 키 자체의
    보관/로테이션 책임은 배포자에게 있다 (SSM SecureString에 저장 후 템플릿에서 주입 권장).
    """
    key = os.environ.get("CRYPTO_KEY")
    if not key:
        raise RuntimeError("CRYPTO_KEY 환경변수가 설정되어 있지 않습니다.")
    return Fernet(key.encode("utf-8") if isinstance(key, str) else key)


def encrypt(value: str) -> str:
    """DynamoDB에 저장할 민감정보(Mealc 비밀번호 등)를 암호화한다."""
    return _get_fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt(encrypted_value: str) -> str:
    return _get_fernet().decrypt(encrypted_value.encode("ascii")).decode("utf-8")


def hash_master_password(password: str, salt_b64: str = None) -> Tuple[str, str]:
    """마스터 패스워드는 평문/복호화 가능한 형태로 저장하지 않는다 — PBKDF2 해시만 저장한다.

    분실 시 복구 수단이 없다(재가입해야 함). Worker(자동예약)는 이 값을 전혀 쓰지 않으며,
    웹 UI에서 설정변경/탈퇴 같은 민감 액션을 할 때 재입력받아 이 해시와 비교하는 용도로만 쓰인다.
    """
    salt = base64.b64decode(salt_b64) if salt_b64 else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, MASTER_PASSWORD_PBKDF2_ITERATIONS)
    return base64.b64encode(digest).decode("ascii"), base64.b64encode(salt).decode("ascii")


def verify_master_password(password: str, hash_b64: str, salt_b64: str) -> bool:
    computed_hash, _ = hash_master_password(password, salt_b64)
    return hmac.compare_digest(computed_hash, hash_b64)
