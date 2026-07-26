# CLAUDE.md

## 안드로이드 디버깅 모드 (식권대장 패킷 캡처)

사용자가 "안드로이드 디버깅 모드로 작동해줘" (또는 유사한 표현: 패킷 캡처 다시 뜨자, 식권대장 트래픽
분석하자 등)라고 요청하면, **[`docs/android_debug_setup.md`](docs/android_debug_setup.md)의 "셋업
절차"를 1번부터 순서대로 그대로 실행**한다.

이 문서는 MuMu Player + mitmproxy(WireGuard mode) + Frida(TrustManagerImpl 후킹)로 식권대장 앱의
HTTPS 트래픽을 복호화 캡처하는 전체 환경을 재현하는 방법과, 그 과정에서 실패했던 접근법들(Android
시스템 프록시, transparent mode 등)이 왜 안 됐는지까지 기록되어 있다. 매번 처음부터 원인을 다시
찾지 말고 이 문서를 먼저 참고할 것.

요약:
- `adb connect <게스트IP>:5555`로 직접 연결 (MuMuManager의 자체 adb connect는 실패함)
- mitmweb은 반드시 **사용자가 직접 여는 별도 터미널**에서 실행 (에이전트 백그라운드 프로세스는 자동 종료됨)
- Android 시스템 프록시 설정은 이 MuMu 빌드에서 작동하지 않음 — WireGuard mode로 우회
- Frida는 raw Python script가 아니라 **CLI(`frida -H 127.0.0.1:27042 -f ... -l ...`)**로 붙일 것
