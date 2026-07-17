# Mealc(식권대장) API 분석 노트

> mitmproxy + Frida(TrustManager 후킹)로 캡처한 실제 트래픽 기반. 실제 토큰/개인정보는 예시로 치환함.

## 기본 정보
- 앱 이름(마켓): 식권대장 (Vendys)
- 앱 패키지: `com.vlocally.mealc.android`
- API base hosts:
  - `api.sikdae.com` — 메인 API
  - `oauth.sikdae.com` — 인증/OAuth
  - `ws.sikdae.com` — WebSocket (`/wsconnect`, 실시간 알림용으로 추정, 로그인 자동화엔 불필요)

## HTTPS 인터셉트 방법 (참고)
- Android 15(APEX/Conscrypt Mainline)에서는 `/system/etc/security/cacerts`에 CA를 심어도(bind-mount, KernelSU 모듈 등) 반영되지 않음.
- **Frida로 `com.android.org.conscrypt.TrustManagerImpl`의 `checkTrustedRecursive`/`verifyChain`을 후킹**해 항상 신뢰하도록 만드는 방식으로 우회 성공.
- KernelSU 루트 + frida-server(x86_64, device abi 기준) + 범용 SSL bypass 스크립트 조합.

## 공통 요청 헤더 (모든 API 호출)
```
Content-Type: application/json
X-Sikdae-Guid: <guid, 로그인 전엔 빈 문자열>
X-User-Agent: Vendys/1.0{"client":"SikdaeUser","clientVersion":"3.129.1","os":"Android","osVersion":"15(35)","deviceModel":"SM-A156E","net":"wifi","vendys-ad-id":"<광고ID>"}
User-Agent: (X-User-Agent와 동일 값)
Authorization: Bearer <access_token>   # 로그인 후 호출에만
Accept-Language: ko
App-Session: <epoch millis>
App-Installation: <설치 UUID>
Ua-Com-Id: <회사 UUID, 로그인 후>
```
- `client`/`clientVersion`/`os`/`osVersion`/`deviceModel`/`net`/`vendys-ad-id` 값은 임의로 채워도 서버가 크게 신경 쓰지 않는 것으로 보이나, 최초 구현은 캡처값과 동일하게 맞추는 걸 권장.

## 로그인 시퀀스 (로그아웃 상태에서 재로그인 캡처)

1. **(선택) 앱 초기화)** `GET /app/v1/init?client_id={CLIENT_ID}&push_token={FCM_TOKEN}` (oauth.sikdae.com)
   - 응답에 `client_id`가 그대로 포함됨 → 이 client_id는 **앱에 고정된 값**(모든 유저 공통).

2. **SSO 확인** `GET /sso/v2?signId={username}` (oauth.sikdae.com)
   - 응답: `{"sso":false,"url":""}` → 일반 아이디/비번 로그인 대상이면 `sso:false`.

3. **공개키 조회** `GET /open/v2/kms/public/{KMS_KEY_ID}` (oauth.sikdae.com)
   - `KMS_KEY_ID`는 캡처에서 고정 UUID(`019A9FE4-3BA4-7AAE-BDFD-B54DA102D536`)로 보임 — 세션/사용자에 따라 바뀌는지는 미확인, 우선 고정값으로 시도.
   - 응답: `{"publicKey": "<base64 DER, X.509 SubjectPublicKeyInfo, RSA 2048bit>"}`

4. **토큰 발급 (실제 로그인)** `POST /vendys/v2/token` (oauth.sikdae.com)
   - Request body:
     ```json
     {
       "client_id": "66BF21D3-C4D0-4EB2-BA95-8ECBC5392681",
       "client_secret": "<앱에 고정된 값, 캡처로 확인 — 코드에는 config로 분리>",
       "grant_type": "password",
       "username": "{signId}",
       "password": "<RSA로 암호화 후 base64, 패딩 방식 미확정 — PKCS1v15로 우선 시도>"
     }
     ```
   - **password 필드**: 3번에서 받은 공개키로 평문 비밀번호를 RSA 암호화 → base64 인코딩. 패딩 스킴은 캡처만으로 확정 불가(암호문 길이 256바이트=2048bit 키와 일치). 구현 시 PKCS1v15부터 시도하고 실패하면 OAEP(SHA-1/256) 순으로 폴백.
   - Response (201):
     ```json
     {
       "ver": 1,
       "account": {"guid": "<user guid>", "password": "NONE", "duplicated": false, "login_time": "...", "user_restore": false, "user_lack": false},
       "access_token": "<token>",
       "refresh_token": "<token>",
       "token_type": "Bearer",
       "expire_time": 2592000
     }
     ```
   - 이후 모든 인증 필요 API는 `Authorization: Bearer {access_token}` 사용.

5. **로그인 검증 겸 첫 프로필 조회** `GET /app/v2/me` (api.sikdae.com) — 200이면 로그인 성공/세션 유효 확인용으로 적합.

## 로그아웃
- `DELETE /oauth2/tokens/{access_token}` (oauth.sikdae.com) → `{"result":"ok"}`

## 참고용 조회 API
- `GET /sikdae/v2` (api.sikdae.com) — 메인 홈 데이터(정책, 포인트, 공지, 예약 상태 등). `bookingOrders.isBookingMenuExistence`로 당일/익일 예약 여부 확인 가능.
- `GET /account/v4/policy` (api.sikdae.com) — 유저 이름 + 식대 정책 id(`policy.day[0].id`, 예: 점심=10988) 조회. 예약 payload의 `policy` 값으로 사용.
- `GET /app/v1/allshow-menu` (api.sikdae.com) — 서비스 메뉴 목록(userInfo.signId로 로그인 계정 확인 가능)
- `GET /app/v2/payment-history/types`, `GET /account/v3/pointbook?...`, `GET /account/v2/pointbook/{couponId}` — 결제(예약) 내역 목록/상세 조회.

## 예약(주문) 생성 플로우

1. **매장 목록** `GET /store/v5` (api.sikdae.com) — `stores[].id`에서 배달식사 매장(예: "[본사 - 점심 딜리버리 서비스]", `supplyTypes.code=BOOKING`) 확인.
2. **매장 상세** `GET /store/v6/{storeId}` — `booked[]`로 날짜별 예약 가능 여부(`isAvailable`) 확인.
3. **날짜별 메뉴 목록** `GET /store/v5/{storeId}/menu?date=YYYY-MM-DD` — 각 메뉴 항목에 `booking.artifactIdx`(그 매장·날짜 공통 값), `id`(메뉴 id), `booking.isBooked` 포함.
4. **배송지 목록** `GET /company/v1/shipping/spots?artifactIdx={artifactIdx}` — `spots[].spotKey`/`spotName` 및 `previousShipping`(직전 배송지 정보: recipient/tel 등 — **가끔 초기화되어 기본값으로 바뀌는 경우 있음**, 매번 원하는 spotKey로 명시 지정 권장).
5. **결제수단/정책 확인** `GET /payment/v2/policy/assign?amount=1&sid={storeId}&isGroup=false&payAssignType=` — 참고용, 예약 자체엔 필수 아닌 것으로 보임.
6. **중복 예약 확인** `GET /booking/v1/book/check/{artifactIdx}` → `{"content":{"status":"NORMAL","message":"정말 결제할까요?"}}` — 이미 예약된 경우 다른 status/message로 응답할 것으로 추정(미확인). **부작용 없는 안전한 조회.**
7. **예약 생성** `POST /booking/v6/book` (api.sikdae.com)
   - Request body: `{"secureData": "<JWT>"}` — **평문 JSON이 아니라 HS256 JWT로 감싸서 전송**.
   - JWT 페이로드 스키마 (필드 다수가 0/빈문자열로 채워짐 — 앱이 의도적으로 비우는 것으로 보이며 서버가 id 기준으로 재계산하는 듯):
     ```json
     {
       "bookingArtifactIdx": <int>, "date": 0, "roomIdx": 0,
       "shipping": {"...": "...", "recipient": "<수령인>", "spotKey": "<배송지 키>", "spotName": "<배송지명>", "tel": "<연락처>", "shippingType": "BOOKING", "shippingLocation": "NONE"},
       "sid": "<storeId>",
       "store": {"id": "<storeId>", "menu": [{"count": 1, "id": "<menuId>", "name": "", "price": 0, "quantity": 0, "salesPrice": 0, ...}], ...},
       "totalPrice": 0, "type": "MENU", "uid": "<본인 계정 guid>",
       "user": {"id": "<본인 계정 guid>", "name": "<이름>", "point": [{"amount": 1, "policy": <정책id>}], ...}
     }
     ```
   - **서명 키 (APK 디컴파일로 확인, jadx `JWTUtil.java` + 호출부 `mvvm/viewmodel/payment/z0.java`)**:
     `JWTUtil.signature(key, payload)` = `Jwts.builder().setPayload(payload).signWith(Keys.hmacShaKeyFor(key.getBytes()))`.
     호출부에서 `key = uid`(현재 로그인한 유저의 `getUid()`, 즉 **로그인 응답의 `account.guid` = `X-Sikdae-Guid` 헤더 값과 동일**)로 확인됨.
     → **비밀키가 서버에만 있는 게 아니라, 로그인 시 이미 클라이언트가 알고 있는 본인 계정 guid를 그대로 HMAC 키로 사용**. 실제 캡처된 JWT로 `HMAC-SHA256(key=account_guid, msg=header_b64+"."+payload_b64)` 재계산 → 서명 완전히 일치 확인함(검증 스크립트로 100% 재현).
   - Response (201): 주문 상세(`content.status.code="ORDER"`, `content.status.name="주문 완료"`, `content.shipping.shippingStatus="SUCCEED"` 등).

## 구현 위치
- `backend/src/core/crypto.py`: `sign_secure_data(payload, key)` — 위 JWT 서명 로직 구현.
- `backend/src/core/mealc_client.py`: `get_account_policy`, `get_store_menu`, `get_shipping_spots`, `check_booking`, `book` 구현 완료.
- 실계정으로 `book()` 라이브 테스트는 **실제 식대포인트가 차감되는 상태변경 액션**이라 신중하게 진행 필요 (이미 수동으로 7/20 예약을 완료한 상태이므로 같은 날짜로 재테스트 시 중복 여부 확인 필요).

## 예약 취소 플로우

1. **결제 내역에서 대상 건 찾기** `GET /account/v3/pointbook?...` → `histories[].couponId`
2. **상세 조회** `GET /account/v2/pointbook/{couponId}` → `historyInfo.historyIdx`(취소 API의 URL 파라미터로 필요, couponId와 다른 정수 값)
3. **취소 확인 정보(선택)** `GET /payment/v1/cancel/{couponId}/confirm` — 환불 예정 금액/기본 취소 사유 문구 목록(`cancelDefaultMessages`) 조회. 부작용 없음.
4. **취소 실행** `PUT /booking/v3/book/{historyIdx}`
   - Request body (서명 불필요, 평문 JSON): `{"roomIdx": 0, "couponId": "<couponId>", "cancelMessage": "<사유>"}`
   - 사유는 자유 문자열이나, 앱 기본값은 "메뉴를 잘못 선택했어요" / "단순 변심! 나중에 다시 구매 할게요" 등.
   - 응답(200): `content.shipping.shippingStatus == "CANCELED"`로 성공 판별.

## 검증 완료 (실계정, end-to-end)
`local_script/prove_cancel_and_rebook.py`로 **로그인 → 결제내역에서 예약 조회 → 취소 → 같은 메뉴로 재예약**까지 실제 API를 상대로 전부 성공 확인함 (2026-07-20, 본사 4층, 베이컨햄감자샌드위치). 로그인/취소/예약 3개 핵심 기능이 모두 실동작함이 증명된 상태.

## 다음 라운드 TODO
- 공휴일 연동은 기존 hgreenfood 프로젝트의 data.go.kr 캐싱 로직 재사용
- kms public key ID가 정말 고정인지, 세션마다 바뀌는지 재검증 (여러 번 로그인해서 비교)
- "로그인 중복 방지": 다른 클라이언트에서 로그인하면 기존 세션이 끊기는 것으로 확인됨 → 자동화 스케줄러는 매 실행마다 새로 로그인해야 함 (세션/토큰 재사용 전제 X).
