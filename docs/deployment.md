# 배포 정보 (ap-northeast-2, 계정 074789808615)

## 스택
- CloudFormation 스택명: `sikdae-auto`
- DynamoDB 테이블: `SikdaeAutoReserve` (PAY_PER_REQUEST)
- SES 발신자: `no-reply@nz.pe.kr` (운영 검증 완료)

## 엔드포인트
- API Gateway: `https://nx8n9zd3i4.execute-api.ap-northeast-2.amazonaws.com/Prod`
- Lambda Function URL(ApiFunction): `https://dgndrueejgahio5e4lxao46n3a0wxakp.lambda-url.ap-northeast-2.on.aws/`
- 프론트엔드는 API Gateway URL 사용 권장(Function URL은 `rawPath` 기반이라 `app.py` 라우팅과 경로 매칭이 다름).

## EventBridge Scheduler
- `sikdae-auto-worker-weekday`: 평일 13:00 KST, WorkerFunction 호출
- `sikdae-auto-holiday-monthly`: 매월 25일 10:00 KST, HolidayUpdaterFunction 호출

## 배포 방법
```bash
cd backend
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 sam build
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 sam deploy \
  --stack-name sikdae-auto \
  --s3-bucket sikdae-auto-sam-artifacts-074789808615 \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides SesSenderEmail=no-reply@nz.pe.kr CryptoKey=<Fernet key> \
  --no-confirm-changeset \
  --region ap-northeast-2
```

- `PYTHONUTF8=1`/`PYTHONIOENCODING=utf-8`가 없으면 프로젝트 경로에 한글이 포함되어 있어 `sam build`가 `UnicodeDecodeError`로 실패한다.
- `CryptoKey`는 CloudFormation이 Lambda 환경변수에 SSM SecureString 동적참조를 지원하지 않기 때문에(`AWS::Lambda::Function/Properties/Environment/Variables`에서 미지원, 배포 시 실제로 확인됨) **`--parameter-overrides`로 직접 주입**한다.
  - **`backend/.crypto-key.local`**(gitignore됨)에 고정값을 보관하고, 배포 시 `CryptoKey=$(cat backend/.crypto-key.local)`로 항상 동일하게 넘겨야 한다. 이 값이 바뀌면 기존에 암호화 저장된 모든 회원의 식권대장 비밀번호를 복호화할 수 없게 된다(실제로 두 번 실수로 값이 바뀌어 테스트 계정을 재가입해야 했음).
- 최초 배포 시 SAM 관리형 S3 버킷(`aws-sam-cli-managed-default`)이 이 계정에서 예전에 생성됐다가 버킷 자체는 삭제된 상태라 `--resolve-s3`가 실패했음 → 별도 버킷(`sikdae-auto-sam-artifacts-074789808615`)을 만들어 `--s3-bucket`으로 명시.
- `HolidayApiKey`는 data.go.kr 서비스키를 `--parameter-overrides HolidayApiKey=...`로 주입 완료.

## ⚠️ curl 테스트 시 주의 (Windows/Git-Bash 인코딩 문제)
Windows Git-Bash(cp949 콘솔) 환경에서 curl `-d '{...한글...}'` 처럼 **한글을 커맨드라인 인자에 직접 넣으면 실제로 바이트가 깨져서 DynamoDB에 손상된 데이터(유니코드 replacement character, U+FFFD)가 저장되는 사고가 실제로 발생했다** (터미널에 안 예쁘게 보이는 정도가 아니라 진짜 데이터 손상). 한글이 포함된 요청은 반드시 JSON 파일로 작성해서 `curl --data-binary "@file.json"`으로 보낼 것.

## 실계정 검증 완료 (2라운드 기준)
- 회원가입(마스터 패스워드 방식, 실제 Mealc 로그인 검증 포함), 잘못된 마스터패스워드 거부, 설정변경(메뉴순서/배송지), 제외일 등록, `check-reservation`(주말을 건너뛴 정확한 다음 근무일 계산 확인 — 7/17(금) 기준 다음 근무일이 7/18(토)이 아니라 7/20(월)로 정확히 표시됨), `reservation/cancel`(신규, 실제 취소 성공), `reservation/make-immediate`(취소 후 재예약 성공) 전부 API Gateway 경유 실제 호출로 검증 완료.

## 남은 것
- SSM에 예전에 생성해둔 `/sikdae-auto/crypto-key` 파라미터는 최종적으로 사용하지 않음(참고용으로 남겨둠, 삭제해도 무방) — 실제 키 관리는 `backend/.crypto-key.local` 파일로 함.
- 프론트엔드 메뉴 선호순서 편집/제외일 캘린더는 드래그앤드롭 없이 단순 위아래 버튼/리스트 방식으로 구현(라이브러리 의존성 최소화).
