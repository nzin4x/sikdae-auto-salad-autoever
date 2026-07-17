# 🍱 식대오토샐러드 (sikdae-auto)

식권대장(Mealc, `com.vlocally.mealc.android`) 자동예약 프로젝트.

- 🌐 서비스: https://sikdae-auto-salad-autoever.pages.dev/
- 💻 소스: https://github.com/nzin4x/sikdae-auto-salad-autoever

기존 [hgreenfood-auto-salad](https://github.com/nzin4x/hgreenfood-auto-salad)는 웹 기반 사내 식당 예약 시스템을 자동화했으나,
회사가 예약 시스템을 식권대장앱(Mealc)으로 교체하면서 동일한 아키텍처(Lambda + DynamoDB + EventBridge Scheduler + Cloudflare Pages)를 재구현했다.

식권대장앱(Mealc)은 네이티브 앱이라 브라우저 디버거로 API를 뽑을 수 없어, MuMu Player(Android 에뮬레이터, 루팅 가능) + mitmproxy로 HTTPS 트래픽을 캡처해 API를 역공학했다. Android 15의 APEX 인증서 저장소 때문에 시스템 CA 주입은 통하지 않아, Frida로 앱의 TrustManager를 직접 후킹해 우회했다.

## 구성

- **`backend/`** — AWS SAM 앱. DynamoDB(단일 테이블) + Lambda(API/Worker/HolidayUpdater) + EventBridge Scheduler(평일 13:00 KST 자동예약, 매월 25일 공휴일 캐시 갱신). SES 이메일 인증 기반 다중유저 회원가입(최대 `MAX_USERS`=10명, hgreenfood-auto-salad와 동일).
- **`frontend/`** — Vite+React 모바일 대시보드. 예약 현황, 즉시예약, 취소, 설정(선호메뉴/배송지/제외일 캘린더/자동예약 토글), 회원탈퇴.
- **`docs/api_notes.md`** — 역공학한 Mealc API 스펙(로그인 RSA 암호화, 예약 JWT 서명, 예약/취소 시퀀스 등).
- **`docs/deployment.md`** — 배포 정보, 트러블슈팅, 실계정 검증 로그.
- **`test/`** — 배포된 시스템을 거치지 않고 Mealc API를 직접 두드려보는 로컬 테스트. `test_*.py`는 조회/로그인만 하는 안전한 것들이라 `pytest`로 자동 수집해도 무방하고, `manual_prove_cancel_and_rebook.py`는 **실제 예약을 취소/재생성하는 상태변경 스크립트**라 일부러 `test_` 접두사를 빼서 pytest가 자동 실행하지 않게 했다 — 반드시 `python test/manual_prove_cancel_and_rebook.py`로 직접 실행할 것.
- **`capture/`** — mitmproxy 캡처 파일 (gitignore, 민감정보 포함 가능).

## 로컬 개발 환경 설정

```bash
cp .env.example .env   # MEALC_USER_ID / MEALC_PASSWORD / DATA_GO_KR_API_KEY 채우기
pip install -r backend/src/requirements.txt python-dotenv pytest
pytest test/            # 안전한 조회성 테스트만 실행
python test/manual_prove_cancel_and_rebook.py   # 실제 취소/재예약 — 신중히 직접 실행
```

`.env`는 `test/*.py`가 Mealc API를 직접 호출해 테스트할 때만 쓰인다. **배포된 시스템 자체는 이 파일을 쓰지 않는다** — 회원가입 시 입력한 식권대장 계정정보는 DynamoDB에 암호화되어 저장되고, Lambda가 매일 13시에 그걸로 로그인해 자동예약한다.

## 메뉴 우선순위(선호 메뉴) 동작 방식

`menuPreference`는 실제 메뉴명이 아니라 **그날 실제 메뉴 이름에 포함되는지 확인하는 부분 문자열 키워드의 우선순위 목록**이다(예: `["샌드위치", "샐러드"]`). 한글 텍스트 자체를 식권대장 서버에 보내는 게 아니라, 클라이언트(Worker)가 그날의 실제 메뉴 목록을 조회한 뒤 필터링하는 데만 쓰인다.

동작 순서 (`backend/src/core/reservation_service.py`):
1. 예약 대상일의 실제 메뉴 목록을 `GET /store/v5/{storeId}/menu?date=...`로 조회한다.
2. `menuPreference`를 순서대로 순회하며, 각 키워드가 **그날 실제 메뉴 이름 문자열에 포함되는(substring) 첫 번째 항목**을 찾는다. 예: `"샌드위치"` → `"[샌드위치]베이컨햄감자샌드위치"` 매치.
3. 매치된 항목의 **실제 메뉴 ID/가격 등(서버가 내려준 진짜 데이터)** 으로 예약 요청을 만든다 — 키워드 문자열 자체는 예약 요청에 들어가지 않는다.
4. 첫 번째 키워드로 매치되는 메뉴가 없으면 다음 키워드로 넘어간다. 하나도 매치되지 않으면 그날은 예약을 시도하지 않고 "선호 메뉴 중 예약 가능한 항목이 없음"으로 종료한다.
5. 순서가 중요하다 — 리스트의 앞쪽 키워드가 매치되면 뒤쪽 키워드는 아예 시도하지 않는다(우선순위).

### 특식/이벤트 메뉴(케이크 등) 처리

식권대장 메뉴 응답은 하루치 메뉴를 카테고리 섹션 배열(`menus`)로 내려주는데, 특식/이벤트 메뉴(예: 케이크 프로모션)가 "점심"과 별도 섹션으로 같이 올 수 있다. `core/reservation_service.py`의 `regular_menu_contents()`는 카테고리명에 "점심"이 포함된 섹션만 "일반 메뉴"로 간주하고, **특식 섹션에 이미 예약이 있어도 일반(점심) 메뉴 예약은 별도로 진행**한다(hgreenfood-auto-salad 원본의 "일반 메뉴 코드만 중복 확인" 정책과 동일한 취지). "이미 예약되어 있음"으로 자동예약을 건너뛰는 건 일반(점심) 섹션에 이미 예약이 있을 때뿐이다.

## 배포

`backend/README` 대신 [`docs/deployment.md`](docs/deployment.md) 참고. 요약하면:

```bash
cd backend
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 sam build
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 sam deploy \
  --stack-name sikdae-auto --s3-bucket <bucket> --capabilities CAPABILITY_IAM \
  --parameter-overrides SesSenderEmail=<ses-sender> CryptoKey=$(cat backend/.crypto-key.local) HolidayApiKey=<data.go.kr-key>
```

프론트엔드는 `frontend/.env`의 `VITE_API_URL`을 배포된 API Gateway URL로 맞춘 뒤 Cloudflare Pages에 연결한다(Root directory: `frontend`).

## 보안

- `.env`, `backend/.crypto-key.local`, `capture/` 하위 파일은 git에 커밋하지 않는다 (`.gitignore` 참고).
- 실제 계정/비밀번호를 코드에 하드코딩하지 않는다.
- 회원의 식권대장 비밀번호는 DynamoDB에 Fernet(`CRYPTO_KEY` Lambda 환경변수) 암호화로 저장된다. 이 키를 가진 관리자는 언제든 복호화할 수 있다(사람 개입 없는 13시 자동예약을 위해 불가피한 구조) — 그래서 마스터 패스워드 같은 추가 인증 계층은 실질적 보안 이득이 없다고 판단해 없앴다. 대신 가입 시 "노출되어도 무방한 비밀번호로 식권대장 앱에서 변경 후 가입하라"고 명확히 안내한다.
