# 식대오토샐러드 (sikdae-auto)

식권대장(Mealc, `com.vlocally.mealc.android`) 앱의 점심 배달 예약을 대신 눌러주는 자동화 서비스.
회원가입한 사용자는 평일 13:00(KST)에 EventBridge Scheduler가 트리거하는 Lambda가 선호 메뉴 순서대로 예약을 시도한다.

- 서비스: https://sikdae-auto-salad-autoever.pages.dev/
- 소스: https://github.com/nzin4x/sikdae-auto-salad-autoever

식권대장은 공식 웹/오픈 API가 없는 네이티브 앱이라, mitmproxy + Frida(TrustManager 후킹)로 HTTPS 트래픽을 캡처해 API를 역공학해서 사용한다. 캡처/분석 내용은 [`docs/api_notes.md`](docs/api_notes.md) 참고.

## 구성

| 경로 | 내용 |
|---|---|
| `backend/` | AWS SAM 앱 (Python 3.13). API Lambda + Worker Lambda + Holiday Lambda, DynamoDB 단일 테이블 |
| `frontend/` | Vite + React 19 모바일 대시보드 |
| `docs/api_notes.md` | 역공학한 Mealc API 스펙 |
| `docs/deployment.md` | 실제 배포 계정/스택 정보, 트러블슈팅 기록 |
| `test/` | 배포 시스템을 거치지 않고 Mealc API를 직접 호출하는 로컬 검증 스크립트 |
| `capture/` | mitmproxy 캡처 파일 저장 위치 (gitignore) |

## 아키텍처

```
EventBridge Scheduler (평일 13:00 KST) ─▶ WorkerFunction ─┐
EventBridge Scheduler (매월 25일 10:00 KST) ─▶ HolidayUpdaterFunction │
                                                            ├─▶ DynamoDB (SikdaeAutoReserve)
Cloudflare Pages (React) ─▶ API Gateway ─▶ ApiFunction ────┘         │
                                                                      ▼
                                                        Mealc API (api/oauth.sikdae.com)
```

- **DynamoDB**: 단일 테이블(`PK`/`SK`)에 회원 설정(`USER#{email}` / `CONFIG`), 디바이스 자동로그인(`USER#{email}` / `DEVICE#{fingerprint}`), 이메일 인증코드(`VERIFY#{email}` / `CODE`, TTL), 공휴일 캐시(`COMMON` / `HOLIDAY#{yyyymm}`)를 함께 저장한다.
- **회원 정원**: `MAX_USERS`(기본 10명) 초과 시 회원가입 거부.
- **이메일 발송**: SES로 인증코드/가입완료/예약결과 알림 전송.

## 백엔드 API

`backend/src/app.py`가 API Gateway 이벤트의 `resource` 경로를 보고 핸들러 모듈로 라우팅한다.

| Method | Path | 핸들러 | 설명 |
|---|---|---|---|
| POST | `/auth/send-code` | auth_handler | 이메일로 6자리 인증코드 발송 |
| POST | `/auth/verify-code` | auth_handler | 인증코드 검증, 가입 여부 확인, 디바이스 등록 |
| POST | `/auth/check-device` | auth_handler | 디바이스 지문으로 자동 로그인 |
| POST | `/auth/logout` | logout_handler | 디바이스 등록 해제 |
| POST | `/register` | register_user | 회원가입 — 입력한 식권대장 계정으로 실제 로그인해 유효성 검증 후 저장 |
| GET | `/register/status` | get_registration_status | 가입 현황(정원 등) 조회 |
| POST | `/check-reservation` | check_reservation | 향후 N영업일(기본 5일)의 예약 현황 조회 |
| POST | `/reservations` | list_reservations | 결제 내역(영수증) 조회 |
| POST | `/reservation/make-immediate` | immediate_reservation | 다음 근무일 즉시 예약 실행 |
| POST | `/reservation/cancel` | cancel_reservation | 가장 가까운 예약 취소 |
| GET | `/user/get-settings` | get_user_settings | 회원 설정 조회 |
| POST | `/user/update-settings` | update_user_settings | 선호 메뉴/배송지/계정정보 수정 |
| POST | `/user/update-exclusion-dates` | update_exclusion_dates | 제외일(자동예약 건너뛸 날짜) 수정 |
| POST | `/user/toggle-auto-reservation` | toggle_auto_reservation | 자동예약 활성화/비활성화 |
| POST | `/user/delete-account` | delete_account | 회원 탈퇴, 관련 데이터 삭제 |
| GET | `/stats` | get_stats | 익명화된 서비스 통계 |
| POST | `/admin/update-holidays` | app.update_holidays_handler | 공휴일 캐시 수동 갱신 |

Worker Lambda(`app.worker_handler`)와 Holiday Lambda(`app.holiday_scheduler_handler`)는 HTTP 라우팅 대상이 아니라 EventBridge Scheduler가 직접 호출한다.

## 예약 로직

핵심 로직은 `backend/src/core/reservation_service.py`의 `ReservationService.run()`에 있다.

1. 대상일 결정: 공휴일 서비스로 다음 근무일(주말/공휴일 제외)을 계산한다. 공휴일 정보는 data.go.kr API를 조회해 DynamoDB에 월 단위로 캐시한다(`core/holiday_service.py`).
2. 대상일이 공휴일이거나 회원이 설정한 제외일이면 예약을 시도하지 않는다.
3. Mealc에 로그인 후 그날 매장 메뉴를 조회한다. 다른 기기에서 로그인하면 기존 세션이 끊기는 것으로 확인되어, 매 실행마다 새로 로그인한다.
4. **선호 메뉴 매칭**: `menuPreference`는 실제 메뉴명이 아니라, 그날 메뉴 이름에 포함되는지 확인하는 부분 문자열 키워드의 우선순위 목록이다(예: `["샌드위치", "샐러드"]`). 목록을 순서대로 순회하며 먼저 매치되는 메뉴로 예약을 시도하고, 매치되는 메뉴가 하나도 없으면 그날은 예약하지 않는다.
5. **특식/이벤트 메뉴 처리**: Mealc 메뉴 응답은 카테고리 섹션 배열(`menus`)로 내려오는데, 케이크 등 특식이 "점심"과 별도 섹션으로 같이 올 수 있다. `regular_menu_contents()`는 카테고리명에 "점심"이 포함된 섹션만 일반 메뉴로 간주하며, 특식 섹션에 이미 예약이 있어도 일반(점심) 메뉴 예약은 별도로 진행한다. "이미 예약됨"으로 건너뛰는 건 일반 섹션에 예약이 있을 때뿐이다.
6. 예약 성공 시 `lastReservedDate`를 갱신하고, 설정된 알림 이메일로 결과를 발송한다.

Worker(`app.worker_handler`)는 전체 회원을 한 라운드로 묶어 처리하며, 정각 직후 당일 메뉴가 아직 게시되지 않아 실패하는 경우를 위해 1s, 2s, 4s, ... 로 지수 백오프하며 재시도 가능한(retryable) 실패만 재시도한다. 대기시간은 전체가 공유하므로 회원 수가 늘어도 총 소요시간이 곱해지지 않는다. Lambda 실행시간 하드캡(15분)에 맞춰 재시도 예산은 840초로 제한된다.

## 인증

마스터 패스워드 없이 이메일 인증코드 + 디바이스 자동로그인 방식을 쓴다(`backend/src/auth_handler.py`).

1. 이메일 입력 → 6자리 인증코드 SES 발송(10분 TTL, DynamoDB에 저장).
2. 인증코드 확인 → 성공 시 브라우저에 저장된 디바이스 지문(`crypto.randomUUID()`, localStorage)을 해당 계정에 등록.
3. 이후 방문 시 디바이스 지문만으로 자동 로그인(`/auth/check-device`).
4. 신규 이메일이면 회원가입(`Register.jsx`) 화면으로 이동.

## 프론트엔드

`frontend/src/App.jsx`가 `loading → email → code → register → dashboard` 스테이지를 전환한다.

- **Dashboard**: 자동예약 on/off 토글, 향후 예약 현황, 즉시예약(13시 이후 & 다음 근무일 미예약 시에만 노출), 가장 가까운 예약 취소, 회원 탈퇴.
- **Settings**: 선호 메뉴 순서(위/아래 버튼으로 재정렬, 드래그앤드롭 없음), 배송지 키워드, 식권대장 계정정보 변경, 제외일 캘린더(`Calendar.jsx`).
- **Stats**: 가입자/활성 인원/예약 성공 이력 수, 최다 선호 메뉴·배송지, 이번 달 공휴일, 익명화된 회원 제외일 집계.

## 로컬 개발

```bash
cp .env.example .env   # MEALC_USER_ID / MEALC_PASSWORD / DATA_GO_KR_API_KEY 채우기
pip install -r backend/src/requirements.txt python-dotenv pytest
pytest test/            # 조회성 테스트만 실행 (test_ 접두사 파일)
python test/manual_prove_cancel_and_rebook.py   # 실제 취소/재예약 — pytest 자동수집 대상 아님, 직접 실행 필요
```

`.env`는 `test/*.py`가 Mealc API를 직접 호출해 검증할 때만 쓰인다. 배포된 시스템은 이 파일을 쓰지 않는다 — 회원가입 시 입력한 계정정보는 DynamoDB에 암호화 저장되고, Worker Lambda가 그걸로 로그인한다.

```bash
cd frontend
npm install
npm run dev
```

## 배포

```bash
cd backend
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 sam build
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 sam deploy \
  --stack-name sikdae-auto --s3-bucket <bucket> --capabilities CAPABILITY_IAM \
  --parameter-overrides SesSenderEmail=<ses-sender> CryptoKey=<fernet-key> HolidayApiKey=<data.go.kr-key>
```

프론트엔드는 `frontend/.env`의 `VITE_API_URL`을 API Gateway URL로 맞춘 뒤 Cloudflare Pages에 연결한다(Root directory: `frontend`).

실제 배포 계정/리전, 엔드포인트, 트러블슈팅 기록은 [`docs/deployment.md`](docs/deployment.md) 참고.

## 보안

- `.env`, `backend/.crypto-key.local`, `capture/` 하위 파일은 git에 커밋하지 않는다(`.gitignore` 참고).
- 회원의 식권대장 비밀번호는 DynamoDB에 Fernet(`CRYPTO_KEY` Lambda 환경변수) 암호화로 저장된다. 이 키를 가진 사람은 복호화할 수 있으므로, 가입 시 노출되어도 무방한 비밀번호로 변경 후 가입하도록 안내한다(`register_user.py`의 `SECURITY_NOTICE`).
- 인증은 마스터 패스워드 대신 이메일 인증코드 + 디바이스 자동로그인만 사용한다.
