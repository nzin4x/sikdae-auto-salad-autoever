"""실계정으로 예약 취소 -> 재예약까지 end-to-end로 직접 수행해 자동화가 실제로 동작함을 증명한다.

⚠️ 실제 예약을 취소하고 재생성하는 상태변경 스크립트다. `pytest`가 자동 수집하지 않도록
의도적으로 파일명에 `test_` 접두사를 붙이지 않았다 — 반드시 직접 실행할 것.

절차:
1. 로그인
2. 결제 내역에서 대상 날짜 예약 건 찾기
3. 취소
4. 취소 확인
5. 같은 메뉴/배송지로 재예약
6. 재예약 성공 확인

사용법:
    python test/manual_prove_cancel_and_rebook.py
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
DELIVERY_SPOT_KEYWORD = "4층"


def main() -> None:
    user_id, password = mealc_credentials()
    client = MealcClient()

    print("[1] 로그인...")
    login_result = client.login(user_id, password)
    if not login_result.success:
        print(f"[-] 로그인 실패: {login_result.message}")
        sys.exit(1)
    print(f"[+] 로그인 성공 (uid={client.sikdae_guid})")

    print("\n[2] 결제 내역에서 예약 건 조회...")
    pointbook = client.get_pointbook_list("2026-07-11", "2026-07-24")
    histories = pointbook.get("histories", [])
    target = None
    for h in histories:
        if h.get("state") == "CONFIRM" and h.get("storeInfo", {}).get("storeId") == STORE_ID:
            target = h
            break
    if not target:
        print("[-] 취소 가능한 예약 건을 찾지 못했습니다. 이미 취소되었거나 예약이 없는 상태일 수 있습니다.")
        print("    -> 재예약 단계로 바로 진행합니다.")
    else:
        coupon_id = target["couponId"]
        menu_name = target["storeInfo"]["orderedMenus"][0]["menuName"]
        print(f"[+] 예약 발견: couponId={coupon_id}, 메뉴={menu_name}")

        detail = client.get_pointbook_detail(coupon_id)
        history_idx = detail["historyInfo"]["historyIdx"]
        print(f"    historyIdx={history_idx}")

        print("\n[3] 취소 확인 정보 조회...")
        confirm = client.get_cancel_confirm(coupon_id)
        print(f"    환불 예정: {confirm.get('amountInfo')}")

        print("\n[4] 예약 취소 실행 (사유: '단순 변심! 나중에 다시 구매 할게요')...")
        cancel_result = client.cancel_booking(history_idx, coupon_id, "단순 변심! 나중에 다시 구매 할게요")
        if not cancel_result.success:
            print(f"[-] 취소 실패: status={cancel_result.status_code}, {cancel_result.raw}")
            sys.exit(1)
        print(f"[+] 취소 성공: shippingStatus={cancel_result.raw['content']['shipping']['shippingStatus']}")

    print(f"\n[5] {TARGET_DATE} 메뉴 재조회 및 재예약 준비...")
    policy = client.get_account_policy()
    day_policy = policy.get("policy", {}).get("day", [])
    policy_id = day_policy[0]["id"]
    recipient = policy["user"]["name"]

    menu = client.get_store_menu(STORE_ID, TARGET_DATE)
    contents = menu["menus"][0]["contents"]
    first_item = contents[0]
    artifact_idx = first_item["booking"]["artifactIdx"]
    menu_id = first_item["id"]
    print(f"[+] 메뉴 선택: {first_item['name']} (id={menu_id})")

    spots = client.get_shipping_spots(artifact_idx)
    spot = next((s for s in spots["spots"] if DELIVERY_SPOT_KEYWORD in s["spotName"]), None)
    if not spot:
        print(f"[-] '{DELIVERY_SPOT_KEYWORD}' 배송지를 찾지 못했습니다.")
        sys.exit(1)
    tel = spots.get("previousShipping", {}).get("tel") or ""
    print(f"[+] 배송지 선택: {spot['spotName']} ({spot['spotKey']})")

    print("\n[6] 중복 예약 확인...")
    check = client.check_booking(artifact_idx)
    print(f"    {check}")

    print("\n[7] 예약(주문) 생성...")
    book_result = client.book(
        store_id=STORE_ID,
        artifact_idx=artifact_idx,
        menu_id=menu_id,
        spot_key=spot["spotKey"],
        spot_name=spot["spotName"],
        recipient=recipient,
        tel=tel,
        policy_id=policy_id,
    )
    if not book_result.success:
        print(f"[-] 예약 실패: status={book_result.status_code}, {book_result.raw}")
        sys.exit(1)

    status = book_result.raw["content"]["status"]
    shipping = book_result.raw["content"]["shipping"]
    print(f"[+] 예약 성공! status={status}, shipping={shipping['shippingTitle']}/{shipping['shippingStatus']}, 장소={shipping['spotName']}")
    print("\n=== 취소 -> 재예약 end-to-end 증명 완료 ===")


if __name__ == "__main__":
    main()
