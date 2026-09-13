# Not Yet Sayable V04 — 최소 동작 버전

흰 배경, 기본 버튼 중심의 참가자/운영자 WebApp입니다. 현재는 **가짜 처리 결과**를 이용해 진행·복구를 검증합니다. 실제 촬영, OCR, AI 호출은 아직 연결하지 않았습니다. `legacy/`와 기존 `.toe` 파일은 수정하지 않았습니다.

## 바로 실행

Node.js 22.18 이상에서 프로젝트 폴더를 열고:

```powershell
npm.cmd ci
npm.cmd run dev
```

브라우저에서 <http://127.0.0.1:5173/operator>를 엽니다.

1. **운영자 데모 시작 → 새 세션 / QR 만들기**를 누릅니다.
2. A/B의 **참가자 화면 열기** 링크를 각각 엽니다.
3. 동의 → 안내 → Q1–Q4 → 지도 확정 순서로 진행합니다.
4. Confirm을 누르면 서버 기준 3초 뒤 작업을 가져오고 약 1.5초 뒤 테스트 결과를 씁니다.
5. 운영자 화면에서 A/B의 독립 진행, 개별 초기화, 중단 후 재시도를 확인합니다.

로컬 데모는 이 컴퓨터에서만 열립니다. **데모 QR의 localhost 주소는 휴대폰에서 접속할 수 없습니다.** 휴대폰 테스트에는 아래 Supabase 설정과 HTTPS 배포가 필요합니다. 데모 서버의 브라우저 식별은 테스트용이므로 외부에 노출하지 마세요.

데모 데이터는 `runtime/demo-db/`에 저장되어 서버를 재시작해도 남습니다. 브라우저 localStorage는 인증 식별, sessionStorage는 미확인 요청과 운영자 QR 보관에만 사용합니다. 참가자 진행 상태는 서버 DB에 있습니다.

## 구현 범위

| 기능 | 현재 상태 |
|---|---|
| A/B 독립 진행, 동의, 안내, Q1–Q4, 지도 확정 | 구현 |
| 서버 시각 기준 카운트다운, 이중 제출 방지 | 구현 |
| 새로고침, 완료한 질문 보기, 뒤로가기, 재답변 | 구현 |
| Try Again, Internet Error, 미확인 요청 재확인 | 구현 |
| 운영자 세션 생성, QR, 개별 초기화·복구·재입장 | 구현 |
| Supabase 테이블·RLS·RPC·Realtime 클라이언트 | 구현, 실제 클라우드 연결 검증은 대기 |
| 동일 SQL을 실행하는 로컬 DB·테스트 처리기 | 구현 |
| 실제 TouchDesigner·카메라·OCR | 다음 단계 |
| OCR 보정, Q1–Q4 분석, 우선순위/해석 | Python 인터페이스만 있음 |
| 전시용 동의문·질문 문구 | 확정 필요 |
| 기존 아카이브 변환·내보내기 | 다음 단계 |

## 구성

```text
web/                    기본 참가자/운영자 화면, 지도, Supabase 클라이언트
supabase/migrations/    상태 테이블, 권한, 원자적 액션과 작업 처리 RPC
tools/                  로컬 데모 서버, PGlite Auth 대체 코드, 테스트 처리기
local/processing/       아직 구성되지 않은 실제 처리 단계 인터페이스
tests/                  SQL 상태·권한·재시작 테스트
docs/                   연결 및 복구 안내
runtime/                실행 중 생성되는 DB/로그 (버전 관리 제외)
legacy/                 읽기 전용 참고 자료
```

실제 구성은 정적 WebApp ↔ Supabase ↔ 로컬 시스템입니다. 데모 서버/PGlite는 개발 도구이며 배포 빌드에는 들어가지 않습니다.

## 검증

```powershell
npm.cmd test
npm.cmd run build
```

자동 테스트는 실제 마이그레이션을 PGlite에서 실행해 상태 전이, 멱등 처리, A/B 격리, 권한 거부, 초기화·QR 교체, 이전 결과 차단, 시간 초과, 재답변, 디스크 재시작을 확인합니다. PGlite는 요청을 직렬화하므로 실제 Supabase 동시 연결 및 Realtime 전송까지 증명하지는 않습니다. 연결 후 전시 네트워크에서 추가 확인해야 합니다.

실제 연결 방법은 [docs/SUPABASE_SETUP.md](docs/SUPABASE_SETUP.md), 상태·복구 규칙은 [docs/STATE_AND_RECOVERY.md](docs/STATE_AND_RECOVERY.md)를 참고하세요.
