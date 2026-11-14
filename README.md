# 식대오토샐러드 (sikdae-auto)

식권대장(Mealc, `com.vlocally.mealc.android`) 앱의 점심 배달 예약을 대신 눌러주는 자동화 서비스.
회원가입한 사용자는 평일 13:00(KST)에 EventBridge Scheduler가 트리거하는 Lambda가 선호 메뉴 순서대로 예약을 시도한다.

- 서비스: https://sikdae-auto-salad-autoever.pages.dev/
- 소스: https://github.com/nzin4x/sikdae-auto-salad-autoever

식권대장은 공식 웹/오픈 API가 없는 네이티브 앱이라, mitmproxy + Frida(TrustManager 후킹)로 HTTPS 트래픽을 캡처해 API를 역공학해서 사용한다. 캡처/분석 내용은 [`docs/api_notes.md`](docs/api_notes.md) 참고.

## 패킷 캡처(mitmproxy + Frida) 재현 방법

API가 바뀌었거나 새 플로우를 분석해야 할 때 캡처를 다시 뜨는 절차. **Android 시스템 프록시 설정은 이
MuMu 빌드에서 작동하지 않아서(가상 WiFi가 무시함) 쓰지 않는다** — 대신 mitmproxy WireGuard mode로
기기 전체 트래픽을 강제 터널링하고, Frida로 TrustManagerImpl을 후킹해 인증서 신뢰 문제를 우회한다.

> **루팅 MuMu 운영 버전:** `3.137.0` (`versionCode=1062`)이 루팅 상태에서 실행 가능한 마지막
> 식권대장 버전이다. `3.139.0`부터는 `루팅(OS 변조)된 단말` 보안 정책으로 기동이 차단된다.
> 평상시 앱을 사용할 때는 WireGuard 캡처 터널을 끄고 직접 네트워크를 사용한다.

2026-11-02 현재 디버그 캡처는 Play 스토어의 `3.143.0` **x86_64 split APK**와 Frida
`17.25.1`을 사용한다. [`docs/frida_mealc_debug.js`](docs/frida_mealc_debug.js)가 루팅 판정과 TLS 신뢰를
함께 우회한다. `3.137.0` APKPure 패키지는 arm64 split만 있어 x86_64 MuMu에서 Frida Java 부착 시
Houdini 번역기가 충돌하므로 캡처용으로는 쓰지 않는다.

### 현재 검증된 디버그 구성

| 계층 | 구성 | 역할/주의사항 |
|---|---|---|
| Windows 호스트 | mitmproxy/mitmweb, Frida CLI `17.25.1` | Frida CLI가 Java bridge를 번들링하여 기기에 전송 |
| Android 게스트 | MuMu Player, Android 15, x86_64, `adb root` | ADB 연결은 현재 `127.0.0.1:16384` |
| 대상 앱 | 식권대장 `3.143.0` (`versionCode=1073`) x86_64 split | Play 스토어 배포본. 로그인 데이터를 유지한 채 캡처 가능 |
| 기기 계측 | `frida-server 17.25.1` + `frida_mealc_debug.js` | `RootDetection.isRooted()`와 Conscrypt `TrustManagerImpl`을 결합 우회 |
| 트래픽 경로 | Android WireGuard `mitmproxy` 터널 → 호스트 UDP `51820` | Android 전역 프록시는 `:0`로 두고 사용하지 않음 |
| 캡처/확인 | mitmweb HTTP `8080`, Web UI `8081`, `capture/*.mitm` | 식권대장 API 요청/응답 본문 저장. 캡처 파일은 Git 제외 |
| 버전 고정 | Play 스토어 `com.android.vending` 비활성화 | 캡처 전용 MuMu에서 식권대장 자동 업데이트 차단 |

```text
MuMu/Android 15 x86_64
  └─ 식권대장 3.143.0
       ├─ RootDetection.isRooted() ───┐
       └─ TrustManagerImpl TLS 신뢰 ─┤  Frida CLI 17.25.1
                                        └─ adb forward tcp:27042
       │
       └─ 모든 IP 트래픽 → WireGuard tun0 (10.0.0.1/32)
                                  → Windows mitmweb UDP 51820
                                  → 복호화된 HTTP(S)
                                  → capture/*.mitm + Web UI :8081
```

Frida `17.24.3`은 `-H` 원격 연결에서 Java bridge 번들 전송 중 WebSocket이 끊기는
회귀가 있으므로 사용하지 않는다. 호스트 `frida` 패키지와 Android `frida-server`의 버전은
반드시 같아야 한다.

캡처 전용 MuMu에서는 `3.143.0` 설치 후 Play 스토어를 비활성화해 버전을 고정한다.
이 조치는 모든 Play 스토어 자동 업데이트를 막으므로 전용 에뮬레이터에서만 사용한다.

```powershell
adb -s 127.0.0.1:16384 shell pm disable-user --user 0 com.android.vending

# 다시 Play 스토어가 필요할 때
adb -s 127.0.0.1:16384 shell pm enable com.android.vending
```

### 캡처 실행

레포 루트에서 PowerShell 터미널 두 개를 열어 각각 실행하고, 캡처가 끝날 때까지 둘 다 열어 둔다.

```powershell
# 터미널 1: mitmweb + WireGuard 서버 + 캡처 파일
.\tools\start-mitm-capture.ps1

# 터미널 2: 버전 일치 검증 + frida-server + ADB forward + 앱 spawn
.\tools\start-frida-debug.ps1
```

`start-frida-debug.ps1`는 Windows 앱 제어가 `frida.exe` 콘솔 램퍼를 차단하는 환경을 피하기 위해
`frida_tools.repl.main` Python 진입점을 실행한다. 이는 raw Frida Python API가 아니라 Java bridge
번들링을 수행하는 동일한 Frida CLI 구현이다.

mitmweb을 먼저 기동한 뒤 Android WireGuard 앱의 `mitmproxy` 터널을 ON으로 바꾸고 Frida 헬퍼를
실행한다. `ip -brief addr show tun0`에 `10.0.0.1/32`가 보이고 Frida 출력에 아래 로그가
나오면 준비된 상태다.

```text
[bypass] RootDetection and TrustManagerImpl hooked
[bypass] RootDetection.isRooted() ... -> false
[bypass] TrustManagerImpl.checkTrustedRecursive()
```

앱에서 재현할 동작을 수행한 뒤 `http://127.0.0.1:8081/`에서 보거나 `capture/*.mitm`을 분석한다.
DNS만 보이는 것이 아니라 `api.sikdae.com`/`oauth.sikdae.com`의 `GET`/`POST`, HTTP 200 상태,
응답 JSON 본문까지 보여야 정상이다. 2026-11-02에는 `/app/v2/me`, `/app/v1/allshow-menu`,
`/sikdae/v3`, `/app/v1/init`, `/account/v4/policy`를 실제로 검증했다.

캡처를 끝낼 때는 WireGuard 터널을 OFF로 바꾸고 두 터미널을 종료한다. 터널이 켜진 상태에서는
Frida 우회가 적용되지 않은 Play 스토어/Google 서비스가 mitmproxy CA를 신뢰하지 않아 오프라인처럼
보일 수 있다. 캡처에는 인증 토큰과 개인정보가 포함될 수 있으므로 외부 공유하거나 Git에 커밋하지 않는다.

전체 셋업 절차(왜 이 방법인지, 실패했던 다른 접근법들, 트러블슈팅 포함)는
[`docs/android_debug_setup.md`](docs/android_debug_setup.md)에 정리되어 있다. Claude Code에게
"안드로이드 디버깅 모드로 작동해줘"라고 하면 그 문서를 따라 환경을 재구성해준다(`CLAUDE.md` 참고).

앱에서 재현하려는 동작(로그인/예약/취소 등)을 실행하면 `capture/*.mitm`에 그대로 쌓인다. 분석이 끝나면
`docs/api_notes.md`를 갱신한다.

## 구성

| 경로 | 내용 |
|---|---|
| `backend/` | AWS SAM 앱 (Python 3.13). API Lambda + Worker Lambda + Holiday Lambda, DynamoDB 단일 테이블 |
| `frontend/` | Vite + React 19 모바일 대시보드 |
| `docs/api_notes.md` | 역공학한 Mealc API 스펙 |
| `docs/deployment.md` | 실제 배포 계정/스택 정보, 트러블슈팅 기록 |
| `docs/android_debug_setup.md` | MuMu Player 안드로이드 디버깅(패킷 캡처) 환경 셋업 가이드 — 왜 이 방법인지 포함 |
| `docs/apk_root_compatibility_test.md` | 식권대장 버전별 루팅 실행 호환성 검사 결과와 재검사 도구 사용법 |
| `docs/frida_ssl_bypass.js` | TrustManagerImpl SSL 우회용 Frida 스크립트 |
| `docs/frida_mealc_debug.js` | 3.143.0 x86_64의 루팅 판정 + TrustManagerImpl 결합 우회 스크립트 |
| `tools/start-frida-debug.ps1` | Frida 버전 검증·서버·포트 포워드·앱 spawn 실행 헬퍼 |
| `CLAUDE.md` | Claude Code용 프로젝트 지침 ("안드로이드 디버깅 모드로 작동해줘" 트리거 등) |
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
5. **특식/이벤트 메뉴 처리**: Mealc 메뉴 응답은 카테고리 섹션 배열(`menus`)로 내려오는데, 케이크 등 특식이 붙는 날에는 섹션명과 진열 순서가 바뀔 수 있다. 전체 섹션에서 선호 메뉴가 속한 예약 묶음(`booking.artifactIdx`)을 찾아 그 묶음만 대상으로 예약한다. 따라서 별도 묶음의 특식이 먼저 진열되거나 이미 예약되어 있어도 샌드위치/샐러드 예약은 정상 진행한다.
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
