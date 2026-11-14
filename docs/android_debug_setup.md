# MuMu Player 안드로이드 디버깅 모드 셋업 가이드

식권대장 앱 트래픽을 다시 분석해야 할 때, "안드로이드 디버깅 모드로 작동해줘" 한마디로 이 환경 전체를
재현하기 위한 기록. 2026-07-23 ~ 2026-07-25 사이에 실제로 삽질하며 알아낸 내용이라, 왜 이 방법이어야
하는지(그리고 왜 다른 방법들은 안 됐는지)까지 포함한다.

## 현재 고정 버전과 네트워크 모드 (2026-11-02 확인)

- **루팅 MuMu에서는 식권대장 `3.137.0` (`versionCode=1062`)을 고정 사용한다.** 이 버전이 루팅
  상태에서 실행 가능한 마지막 버전이다.
- `3.139.0` (`versionCode=1066`)과 `3.143.0` (`versionCode=1073`)은 시작 직후
  `보안 정책에 따라 루팅(OS 변조)된 단말에서는 식권대장을 이용하실 수 없습니다.`라고 차단한다.
- 실제 `adb root`의 `uid=0(root)` 상태에서 `3.133.0`, `3.137.0`은 로그인 화면까지 기동됐고,
  `3.139.0`, `3.143.0`은 위 보안 문구가 확인됐다. 재검사 방법은
  [`apk_root_compatibility_test.md`](apk_root_compatibility_test.md)에 기록돼 있다.
- **일반 앱 사용(직접 네트워크):** WireGuard `mitmproxy` 터널을 끄고 Android 전역 프록시는 `:0`으로
  둔다. 이 상태에서 `api.sikdae.com:443` 직접 연결, 식권대장 홈 화면, Play 스토어 콘텐츠 로드를
  확인했다.
- **패킷 캡처:** 아래 절차에 따라 mitmweb과 WireGuard를 켠다. 캡처가 끝나거나 SSL 우회가 붙지 않은
  상태에서는 WireGuard를 다시 꺼야 앱 네트워크를 정상적으로 사용할 수 있다.
- **캡처 조합은 `3.143.0` x86_64 split APK + Frida `17.25.1` 이상을 사용한다.**
  `docs/frida_mealc_debug.js`가 `RootDetection.isRooted()` 판정과 Conscrypt TLS 신뢰를 함께 우회한다.
- `3.137.0`은 루팅 상태에서 단독 실행되는 마지막 버전이지만, APKPure XAPK는 arm64 split만
  제공해 x86_64 MuMu에서 Frida Java bridge를 붙이면 `libhoudini.so`에서 충돌한다.

### 패킷 캡처 가능 여부 재검증 (2026-11-02)

`3.143.0` x86_64 split이 로그인된 상태에서 전체 절차를 다시 실행한 결과는 다음과 같다.

- WireGuard 터널과 mitmproxy 경유는 정상이다. `tun0=10.0.0.1/32`가 생성되고 캡처에
  `api.sikdae.com`, `s.vendys.io` DNS 조회가 기록됐다.
- 앱은 터널을 통해 두 도메인의 TCP 443 연결을 시도한다.
- Frida `17.24.3`의 `-H` WebSocket 연결은 Java bridge 번들을 보내는 순간
  `Failed to load script: the connection is closed`로 종료되는 Frida 회귀 버그였다. 앱의 반-Frida 탐지가
  원인이 아니었다. 공식 이슈: [frida/frida#3806](https://github.com/frida/frida/issues/3806).
- 호스트 `frida` 패키지와 기기 `frida-server`를 모두 `17.25.1`로 맞추자 Java bridge가
  안정적으로 로드됐다.
- `frida_mealc_debug.js`로 기동하자 루팅 경고 없이 로그인된 홈 화면이 열렸고, WireGuard +
  mitmweb 캡처에 `api.sikdae.com` 실제 `GET`과 200 응답 본문이 복호화되어 저장됐다.
- 검증된 주요 경로: `/app/v2/me`, `/app/v1/allshow-menu`, `/sikdae/v3`, `/app/v1/init`,
  `/account/v4/policy`.

즉 **현재 구성은 HTTPS 요청/응답 본문 캡처까지 재현 가능하다.**

## 목표 아키텍처

```
[MuMu Player 안드로이드 게스트]                    [Windows 호스트]
  com.vlocally.mealc.android (식권대장)
       │ TLS (평문처럼 보이게 우회됨)
       │
  Frida gadget (frida-server, root)  <──TCP:27042── adb forward ──  frida CLI (Java bridge 자동 번들링)
       │ TrustManagerImpl.checkTrustedRecursive/verifyChain 후킹
       │ → 아무 인증서나 신뢰하도록 만듦
       │
  모든 IP 트래픽
       │ WireGuard 터널 (UDP 51820)
       ▼
  tun0 (10.0.0.1/32) ───────────────────────────►  mitmweb --mode wireguard@51820
                                                     (호스트 LAN IP:51820에서 리스닝)
                                                     → 복호화된 HTTP(S) 캡처 → capture/*.mitm
```

핵심 아이디어 두 가지:
1. **Android 시스템 프록시 설정에 의존하지 않는다.** 앱이 프록시를 인식하는지 여부와 무관하게, WireGuard로
   기기의 IP 트래픽 전체를 강제로 mitmproxy로 보낸다.
2. **mitmproxy CA를 신뢰하게 만드는 것도 시스템 레벨이 아니라 Frida로 개별 프로세스 안에서 조작한다.**
   Android 15는 시스템 CA 저장소 조작을 무시하기 때문.

## 왜 이 방법인가 — 시행착오 기록

### 1) Android 전역 HTTP 프록시 설정 → 실패
`adb shell settings put global http_proxy <host>:8080`으로 설정하면 값 자체는 저장되지만, 이 MuMu
빌드에서는 **`dumpsys connectivity`의 실제 LinkProperties에 전혀 반영되지 않았다.** WiFi 저장 설정
XML(`/data/misc/apexdata/com.android.wifi/MuMuWifiConfigStore.xml`)에 직접 `ProxySettings=STATIC`을
심고 WiFi를 재시작해도 마찬가지였다 — MuMu의 가상 WiFi 스택이 프록시 설정 자체를 반영하지 않는 것으로
보인다. 결과적으로 Chromium도 식권대장 앱도 이 프록시를 전혀 타지 않고 직접 연결을 시도했다
(캡처 파일에 해당 트래픽이 전혀 안 찍힘으로 확인).

→ **교훈: 이 환경에서는 시스템 프록시 설정 자체를 시도하지 말 것.**

### 2) mitmproxy `--mode transparent` (iptables DNAT 병행 시도) → 실패
Windows에서 transparent mode는 WinDivert 드라이버가 필요하고 **관리자 권한 없이 `PermissionError:
[WinError 5]`로 즉시 실패**한다. mitmproxy 자체도 "deprecated, flaky" 라고 경고한다.

→ **교훈: Windows 호스트에서는 transparent mode를 시도하지 말 것.**

### 3) WireGuard mode → 성공
mitmproxy의 `--mode wireguard`는 WinDivert 없이 순수 유저스페이스로 동작하는 VPN 서버다. Android에
WireGuard 앱만 설치하면, 시스템 프록시 인식 여부와 무관하게 **모든 IP 트래픽이 강제로 터널을 통과**한다.

### 4) Frida `Java`가 안 잡히는 문제 → 두 가지가 겹쳐 있었음
- 처음엔 `frida-server` 바이너리가 이상한 줄 알고 공식 릴리즈로 통째로 교체했다(아래 절차에 포함).
- 하지만 진짜 원인은 따로 있었다: **Frida 16+ 부터 `Java`/`ObjC` 브릿지가 core에서 분리**되어,
  Python API로 `session.create_script(raw_js)`처럼 스크립트를 날것으로 로드하면 `Java`가 전역에
  주입되지 않는다(`typeof Java === 'undefined'`). **`frida` CLI 툴**은 내부적으로 이 브릿지를 자동
  번들링해주기 때문에 CLI로 붙이자 바로 해결됐다.
- 정확히 어느 쪽이 결정적이었는지 분리 검증은 안 했지만, 재현성을 위해 **둘 다** 절차에 포함시켰다
  (공식 frida-server + frida CLI로 attach).

→ **교훈: Python `frida` 모듈로 raw script를 직접 로드하지 말고, 반드시 `frida` CLI(`-l script.js`)를
사용할 것.**

`-H 127.0.0.1:27042`로 붙을 때는 `17.24.3`을 사용하지 말 것. 이 버전은 Java bridge 번들
전송 크기에서 연결이 끊기는 회귀가 있었고, `17.25.1`에서 해결됨을 실기기로 확인했다.

Windows 앱 제어 정책이 pip의 `frida.exe` 콘솔 램퍼를 차단할 수 있다. 이 경우
`python -c "from frida_tools.repl import main; main()" ...`로 같은 CLI 진입점을 실행한다.
`tools/start-frida-debug.ps1`는 이 방식을 자동으로 사용한다.

### 5) `frida-tools`의 `-U`(USB) 디바이스 열거가 무한 행(hang) → adb forward로 우회
`frida-ps -U`, `frida-ls-devices` 둘 다 20초+ 응답 없이 멈췄다. `adb forward tcp:27042 tcp:27042`로
포트를 직접 뚫고 `-H 127.0.0.1:27042`(원격/TCP 모드)로 붙이면 즉시 연결된다.

→ **교훈: `-U` 쓰지 말고 항상 `adb forward tcp:27042 tcp:27042` + `-H 127.0.0.1:27042`.**

### 6) `MuMuManager.exe adb connect`가 `vm not ready`로 실패
MuMuManager의 자체 `adb -v <idx> -c connect` 서브커맨드는 브릿지 모드에서 계속 실패했다. 이 환경은
브릿지 네트워크 모드(`net_bridge_open: true`)라 게스트가 실제 LAN IP를 갖고 있으므로, **표준
`adb connect <게스트IP>:5555`가 훨씬 안정적**이었다.

→ **교훈: `MuMuManager adb connect` 쓰지 말고 표준 `adb connect <게스트IP>:5555` 사용.**

### 7) Claude(에이전트)가 백그라운드로 띄운 mitmweb이 계속 자동 종료됨
0.0.0.0으로 바인딩하는 리스너 프로세스(mitmweb)를 에이전트의 샌드박스 안에서 백그라운드로 띄우면
몇 초~몇 분 안에 원인 불명으로 죽었다(`status: killed`). **반대로 `frida-server`(안드로이드 게스트 안,
adb shell로 기동)나 `frida` CLI(호스트, 포트 리스닝 없이 outbound 연결만 함)는 안 죽었다** — 외부에서
접속 가능한 포트를 리스닝하는 프로세스만 표적이 되는 것으로 추정.

→ **교훈: mitmweb은 반드시 사용자가 직접 여는 별도 터미널 창에서 실행할 것. 에이전트가 대신
백그라운드로 띄우지 말 것.**

### 8) 기타 자잘한 함정
- **Git Bash(MSYS) 경로 자동 변환**: `adb push`/`adb shell`에 유닉스 스타일 절대경로(`/data/local/tmp/...`,
  `/sdcard/...`)를 넘기면 MSYS가 멋대로 Windows 경로로 바꿔버려서 조용히 실패한다.
  **`MSYS_NO_PATHCONV=1`을 항상 붙일 것.** (단, 로컬 Windows 경로 인자는 원래 Windows 스타일
  그대로 두면 된다 — 둘 다 유닉스 스타일로 쓸 필요는 없음.)
- **`C:\app`는 Google Drive(`다른 컴퓨터`) 정션**이라 가끔 첫 접근이 느려서 일시적으로
  "경로 없음"처럼 보일 수 있다. 재시도하면 대부분 바로 해결됨 — 실제 삭제/장애 아님.
- **MuMu는 앱마다 별도 가상 디스플레이(탭)를 쓴다.** `adb shell screencap`을 display id 지정 없이
  쓰면 엉뚱한(대부분 홈 화면) 디스플레이가 찍힌다. 정확한 화면을 보려면
  `dumpsys activity activities`에서 대상 앱의 `Display #N`을 찾고, `dumpsys display`에서
  `mDisplayId=N`에 해당하는 `mPrimaryDisplayDevice=...(local:XXXXXXXXXXXXXXXXXX)` 값을 찾아
  `screencap -d <그 local: 뒤 숫자>`로 캡처해야 한다. (패킷 캡처 자체엔 불필요, 화면 확인이 필요할
  때만 참고.)
- **WiFi를 끄면 adb-over-network 연결도 같이 끊긴다** (당연하지만 자주 까먹음). 이럴 때는
  `MuMuManager.exe sh -v <idx> -c "svc wifi enable"` (네트워크에 의존하지 않는 내부 셸 채널)로
  복구한 뒤 `adb connect`를 다시 하면 된다.

## 사전 준비물 (경로)

| 용도 | 경로 |
|---|---|
| adb | `C:\app\platform-tools\adb.exe` |
| mitmweb | `C:\Program Files\mitmproxy\bin\mitmweb.exe` |
| MuMuManager (인스턴스 정보/내부 셸) | `C:\Program Files\Netease\MuMuPlayer\nx_main\MuMuManager.exe` |
| frida CLI | pip로 설치된 `frida-tools`의 `Scripts\frida.exe` — 위치는 `pip show -f frida-tools`로 확인 (보통 `%LOCALAPPDATA%\Packages\PythonSoftwareFoundation.Python.*\LocalCache\local-packages\Python3xx\Scripts\frida.exe`) |
| WireGuard 클라이언트 설정 저장소 | `~/.mitmproxy/wireguard.conf` (JSON, `server_key`/`client_key`만 들어있음 — mitmweb이 없으면 자동 생성) |
| SSL bypass 스크립트 | `docs/frida_ssl_bypass.js` |
| 3.143 루팅 + SSL 결합 우회 | `docs/frida_mealc_debug.js` |
| 식권대장 패키지/런처 액티비티 | `com.vlocally.mealc.android/.mvvm.view.intro.IntroActivity` |
| 캡처 저장 위치 | `capture/*.mitm` (gitignore됨) |

WireGuard(공식 앱)와 frida-server가 이미 기기에 설치/배치되어 있어야 한다(최초 1회만).
frida-server가 없거나 버전이 안 맞으면 "6. Frida 준비" 절 참고.

## 셋업 절차 (순서대로)

### 1. MuMu 인스턴스 확인
```bash
MM="/c/Program Files/Netease/MuMuPlayer/nx_main/MuMuManager.exe"
"$MM" info -v 0   # is_android_started, is_process_started가 true인지 확인
```

### 2. 게스트 IP 확인 + adb 연결
```bash
"$MM" sh -v 0 -c "ip addr show wlan0"   # inet 192.168.x.x/24 확인 (브릿지 모드라 실제 LAN IP)
ADB="/c/app/platform-tools/adb.exe"
"$ADB" connect <게스트IP>:5555          # MuMuManager 자체 adb connect(-c connect)는 쓰지 말 것
"$ADB" devices -l                        # device 상태로 나오는지 확인
```

### 3. mitmweb 기동 — **반드시 사용자가 직접 여는 별도 터미널에서**
Claude가 대신 백그라운드로 띄우면 안 됨(위 7번 항목 참고). 사용자에게 아래 명령을 새 PowerShell 창에서
실행하도록 안내:
```powershell
& "C:\Program Files\mitmproxy\bin\mitmweb.exe" --mode regular@8080 --mode wireguard@51820 --web-port 8081 -w "C:\lsrc\sikdae-auto-salad-autoever\capture\<날짜시각>.mitm"
```
켜진 뒤 `netstat -ano | grep ":8080 \|:8081 \|:51820"`으로 리스닝 확인 가능 (읽기 전용이라 Claude가
직접 체크해도 안전).

### 4. WireGuard 클라이언트 설정 만들어서 기기에 넣기
QR 스캔은 호스트 화면 → 게스트 카메라로 찍을 방법이 없으므로 **파일로 push**한다.
```bash
python -c "
import json, mitmproxy_rs.wireguard as wg
c = json.load(open(r'C:\Users\<user>\.mitmproxy\wireguard.conf'))
server_pub = wg.pubkey(c['server_key'])
conf = f'''[Interface]
PrivateKey = {c[\"client_key\"]}
Address = 10.0.0.1/32
DNS = 10.0.0.53

[Peer]
PublicKey = {server_pub}
AllowedIPs = 0.0.0.0/0
Endpoint = <호스트 LAN IP>:51820
'''
open('mitmproxy.conf', 'w').write(conf)
"
MSYS_NO_PATHCONV=1 "$ADB" -s <게스트IP>:5555 push mitmproxy.conf /sdcard/Download/mitmproxy.conf
```
호스트 LAN IP는 `ipconfig`로 확인(무선/이더넷 어댑터의 IPv4 주소).

기기에서: WireGuard 앱 → `+` → **"파일 또는 아카이브에서 가져오기"** → Download 폴더 →
`mitmproxy.conf` → 터널 토글 ON.

확인:
```bash
MSYS_NO_PATHCONV=1 "$ADB" -s <게스트IP>:5555 shell "ip addr" | grep -A3 tun0   # 10.0.0.1/32 있어야 함
```

### 5. (참고) Android 시스템 프록시는 설정하지 않는다
과거에 `settings put global http_proxy`로 설정해둔 값이 남아있다면 지워서 혼동을 피한다(1번 시행착오
참고 — 어차피 안 먹히지만, 죽은 프록시로 연결 시도하다 실패하는 것처럼 보이는 앱이 있을 수 있음):
```bash
MSYS_NO_PATHCONV=1 "$ADB" -s <게스트IP>:5555 shell settings put global http_proxy :0
```

캡처 전용 에뮬레이터에서 `3.143.0`의 자동 업데이트를 막으려면 Play 스토어를 비활성화한다.
식권대장만이 아니라 모든 Play 자동 업데이트가 막히므로 전용 MuMu에서만 사용한다.

```bash
"$ADB" -s <게스트IP>:5555 shell pm disable-user --user 0 com.android.vending
# 복구: "$ADB" -s <게스트IP>:5555 shell pm enable com.android.vending
```

### 5-1. 캡처를 끝내고 직접 네트워크로 복귀

식권대장 자체를 정상 사용하려면 WireGuard 앱에서 `mitmproxy` 터널을 OFF로 바꾸고 `tun0`이 사라졌는지
확인한다. mitmweb도 종료한다.

```bash
MSYS_NO_PATHCONV=1 "$ADB" -s <게스트IP>:5555 shell "ip addr show tun0 2>/dev/null || echo tun0-off"
MSYS_NO_PATHCONV=1 "$ADB" -s <게스트IP>:5555 shell "toybox nc -z -w 5 api.sikdae.com 443 && echo tcp-443-ok"
```

`tun0-off`, `tcp-443-ok`가 나오면 직접 네트워크 상태다.

터널을 끈 직후 Play 스토어 등이 계속 오프라인으로 보이면 이전 VPN 연결을 프로세스가 캐시한 것이다.
데이터를 지우지 말고 Play 스토어와 Play Services만 재시작한다.

```bash
MSYS_NO_PATHCONV=1 "$ADB" -s <게스트IP>:5555 shell am force-stop com.android.vending
MSYS_NO_PATHCONV=1 "$ADB" -s <게스트IP>:5555 shell am force-stop com.google.android.gms
```

그 뒤 Play 스토어를 다시 열면 된다. 2026-10-30에는 이 조치 후 추천·검색·설치 화면이 정상 로드됐다.

### 6. Frida 준비
```bash
# 6-1. 기기에 frida-server 있는지, 버전이 python frida 패키지와 맞는지 확인
python -c "import frida; print(frida.__version__)"
MSYS_NO_PATHCONV=1 "$ADB" shell "su -c '/data/local/tmp/frida-server --version'"

# 버전이 다르거나 frida-server가 없으면 공식 릴리즈를 받아서 교체 (버전은 위에서 확인한 값으로)
curl -sL -o /tmp/frida-server.xz "https://github.com/frida/frida/releases/download/<VERSION>/frida-server-<VERSION>-android-x86_64.xz"
cd /tmp && xz -d -k frida-server.xz
MSYS_NO_PATHCONV=1 "$ADB" push "$(cygpath -w /tmp/frida-server)" /data/local/tmp/frida-server-new
MSYS_NO_PATHCONV=1 "$ADB" shell "su -c 'pkill -9 frida-server; sleep 1; mv -f /data/local/tmp/frida-server-new /data/local/tmp/frida-server; chmod 755 /data/local/tmp/frida-server; nohup /data/local/tmp/frida-server > /data/local/tmp/frida-server.log 2>&1 &'"
MSYS_NO_PATHCONV=1 "$ADB" shell "su -c 'ps -A | grep frida'"   # 떠있는지 확인
```

호스트와 기기 버전은 반드시 같아야 하며 `17.25.1` 이상을 사용한다. `17.24.3`은 사용하지 않는다.

### 7. 포트 포워드 + Frida로 SSL bypass 붙이기

레포 루트의 PowerShell에서는 다음 헬퍼로 버전 일치 확인, 서버 기동, 포트 포워드,
앱 spawn을 한 번에 실행할 수 있다.

```powershell
.\tools\start-frida-debug.ps1
```

수동 명령은 다음과 같다.

```bash
"$ADB" forward tcp:27042 tcp:27042   # -U(USB 열거) 쓰면 행 걸림 — 반드시 forward+TCP로

FRIDA="<pip Scripts 경로>/frida.exe"
"$ADB" shell "am force-stop com.vlocally.mealc.android"
"$FRIDA" -H 127.0.0.1:27042 -f com.vlocally.mealc.android -l "C:\lsrc\sikdae-auto-salad-autoever\docs\frida_mealc_debug.js"
```
`[bypass] RootDetection and TrustManagerImpl hooked` 로그가 뜨고, `RootDetection.isRooted() ... -> false`와
`TrustManagerImpl.checkTrustedRecursive()`가 출력되면 정상.

**중요 — 이것도 결국 죽는다, 그것도 생각보다 빨리.** 처음엔 포트를 리스닝하지 않고 outbound
연결만 하니까 mitmweb과 달리 에이전트 백그라운드 셸에서 안 죽을 거라 생각했는데, 실제로는 재시도
때마다 **몇 분 안에(한 번은 거의 즉시) `killed` 상태로 종료됐다.** "포트 리스닝 여부가 기준"이라는
가설도 틀린 것으로 보인다 — 에이전트(Claude) 백그라운드 셸에서 띄운 프로세스는 종류를 막론하고
장시간 생존을 보장할 수 없다고 보는 게 맞다.

→ **결론: mitmweb과 frida 둘 다 반드시 사용자가 직접 여는 별도 터미널(2개 창)에서 실행할 것.**
에이전트가 대신 백그라운드로 띄우는 건 "붙는지 빠르게 확인"하는 용도로만 쓰고, 실제 캡처/테스트
세션 동안 계속 살아있어야 하는 프로세스는 처음부터 사용자 터미널에 맡긴다.

재연결이 필요해지면(앱에서 인증서 에러가 다시 뜨기 시작하면) `am force-stop` 후 다시
`frida -H 127.0.0.1:27042 -f com.vlocally.mealc.android -l docs\frida_mealc_debug.js` 를
실행하면 된다.

### 8. 검증
```bash
"/c/Program Files/mitmproxy/bin/mitmdump" -n -r capture/<파일>.mitm 2>&1 | grep -i "sikdae\|vendys"
```
DNS 조회뿐 아니라 실제 `GET`/`POST` 라인과 `200 OK` 같은 응답이 보이면 성공. (`api.sikdae.com`
관련 실제 API 호출은 앱에서 로그인 등을 실제로 진행해야 찍힌다 — DNS만 보이는 건 아직 사용자가
해당 화면까지 안 간 것뿐, 실패 아님.)

## 트리거 문구
사용자가 "안드로이드 디버깅 모드로 작동해줘" 라고 말하면, 이 문서의 "셋업 절차"를 1번부터 순서대로
그대로 실행한다. `CLAUDE.md`에 이 문서를 가리키는 안내가 있다.
