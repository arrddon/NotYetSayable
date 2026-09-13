# Not Yet Sayable — implementation

먼저 상위 폴더의 `PROJECT_CONTEXT.md`와 `NEXT_STEPS.md`를 읽으세요. 이 폴더는 루트 TD 프로젝트를 지원하는 WebApp, Supabase 스키마, 로컬 도구를 담습니다.

프로젝트 루트에서:

```powershell
cd system
npm.cmd run dev
```

로컬 데모: <http://127.0.0.1:5173/operator>. **New session / QR codes**로 A/B를 만듭니다. 데모는 PC 전용이며 휴대폰 접속용이 아닙니다.

실제 프런트엔드: `npm.cmd run dev:supabase`. Supabase URL/publishable key는 `.env.local`에 설정돼 있습니다. SQL 적용·익명 로그인 활성화·운영자 등록·로컬 worker 자격 설정은 아직 필요합니다.

모든 UI는 영어입니다. 모바일은 Consent, Confirm, Countdown, Please wait, Continue, Try Again, 지도 확정만 표시합니다. TD 브리지와 설치 스크립트는 `local/bridge.py`, `local/touchdesigner/`에 있습니다. 실제 .toe에 설치하고 카메라 경로를 지정하는 순서는 [TD 연결 안내](local/touchdesigner/README.md)를 참고하세요. TD 데모는 `npm.cmd run dev:td`로 실행합니다.

`npm.cmd run build`는 최소 컴파일 확인입니다. `npm.cmd test`는 상태·권한 로직 변경 등 중요한 경우에만 실행하세요. `docs/history/`는 이전 기록이며 현재 요구보다 우선하지 않습니다.
