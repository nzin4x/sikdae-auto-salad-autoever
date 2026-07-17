"""예약 관련 '조회성' API만 실계정으로 검증하는 테스트 (실제 예약/결제는 하지 않음).

안전함(조회만, 상태 변경 없음) — pytest로 자동 수집/실행되어도 무방하다.

사용법:
    python test/test_reservation_readonly.py
    pytest test/test_reservation_readonly.py
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

STORE_ID = "46DE71D7-8F6D-F08D-D4D1-43F86C0A5C84"  # [본사 - 점심 딜리버리 서비스]
TARGET_DATE = "2026-07-20"


def test_reservation_readonly_flow() -> None:
    user_id, password = mealc_credentials()
    client = MealcClient()

    result = client.login(user_id, password)
    assert result.success, f"로그인 실패: {result.message}"
    print("[+] 로그인 성공")

    policy = client.get_account_policy()
    print(f"[*] 계정: {policy.get('user', {}).get('name')}")
    day_policy = policy.get("policy", {}).get("day", [])
    policy_id = day_policy[0]["id"] if day_policy else None
    print(f"[*] 점심 정책 id: {policy_id}")

    menu = client.get_store_menu(STORE_ID, TARGET_DATE)
    contents = menu.get("menus", [{}])[0].get("contents", [])
    print(f"[*] {TARGET_DATE} 메뉴 {len(contents)}건:")
    artifact_idx = None
    first_menu_id = None
    for item in contents[:5]:
        print(f"    - {item['name']} (id={item['id']}, artifactIdx={item['booking']['artifactIdx']}, isBooked={item['booking']['isBooked']})")
        if artifact_idx is None:
            artifact_idx = item["booking"]["artifactIdx"]
            first_menu_id = item["id"]

    assert artifact_idx is not None, "메뉴가 없어 이후 조회를 진행할 수 없습니다."

    spots = client.get_shipping_spots(artifact_idx)
    print(f"[*] 배송지 {len(spots.get('spots', []))}건, 이전 배송지: {spots.get('previousShipping', {}).get('spotName')}")
    target_spot = next((s for s in spots.get("spots", []) if "4층" in s["spotName"]), None)
    if target_spot:
        print(f"    -> 본사 4층 spotKey: {target_spot['spotKey']}")

    check = client.check_booking(artifact_idx)
    print(f"[*] 예약 가능 여부 확인: {check}")

    print("\n[+] 조회성 API 전부 정상 동작 확인 (실제 예약은 생성하지 않았습니다).")
    print(f"    -> book() 호출 시 필요한 값: store_id={STORE_ID}, artifact_idx={artifact_idx}, menu_id={first_menu_id}, policy_id={policy_id}")


if __name__ == "__main__":
    test_reservation_readonly_flow()
