# Not Yet Sayable — implementation

이 저장소는 Not Yet Sayable의 **WebApp 전용**입니다. `web/`에 영어 참가자/운영자 화면, `supabase/`에 서버 스키마, `tools/`에 개발용 도구가 있습니다. 레거시, TD 프로젝트, Python 장비 코드는 이 저장소에서 관리하지 않습니다.

프로젝트 루트에서:

```powershell
cd system
npm.cmd run dev
```

로컬 데모: <http://127.0.0.1:5173/operator>. **New session / QR codes**로 A/B를 만듭니다. 데모는 PC 전용이며 휴대폰 접속용이 아닙니다.

실제 프런트엔드: `npm.cmd run dev:supabase`. Supabase URL/publishable key는 `.env.local`에 설정돼 있습니다. SQL 적용·익명 로그인 활성화·운영자 등록·로컬 worker 자격 설정은 아직 필요합니다.

모든 UI는 영어입니다. 모바일은 Consent, Confirm, Countdown, Please wait, Continue, Try Again, 지도 확정만 표시합니다. 질문과 결과는 별도 TD 설치 화면에서 표시합니다. `npm.cmd run dev:td`는 별도로 설치한 TD 브리지가 접속하는 개발용 서버 모드입니다.

`npm.cmd run build`는 최소 컴파일 확인입니다. `npm.cmd test`는 상태·권한 로직 변경 등 중요한 경우에만 실행하세요. 다음 웹앱 작업은 `docs/NEXT_WEBAPP_TASK.md`를 참고하세요.
