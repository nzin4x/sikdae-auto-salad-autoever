"""실제 계정으로 MealcClient.login()을 검증하는 테스트.

자격증명은 .env(gitignore)에서 읽는다. 하드코딩 금지.
안전함(로그인/조회만, 상태 변경 없음) — pytest로 자동 수집/실행되어도 무방하다.

사용법:
    python test/test_login.py
    pytest test/test_login.py
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _env import mealc_credentials  # noqa: E402
from core.mealc_client import MealcClient  # noqa: E402


def test_login_and_session() -> None:
    user_id, password = mealc_credentials()

    client = MealcClient()

    print(f"[*] {user_id} 로그인 시도...")
    result = client.login(user_id, password)

    assert result.success, f"로그인 실패: {result.message}"
    print("[+] 로그인 성공")
    print(f"    access_token: {result.access_token[:12]}...")
    print(f"    expire_time: {result.expire_time}초")

    print("[*] 세션 유효성 확인 (GET /app/v2/me)...")
    me = client.get_me()
    assert me.success, f"세션 확인 실패: status={me.status_code}, message={me.message}"
    print("[+] 세션 유효성 확인 성공 — 로그인이 실제로 동작합니다.")


if __name__ == "__main__":
    test_login_and_session()
