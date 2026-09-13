# TD 통합 인수인계

> 후속 TD 구현 완료: `system/local/touchdesigner/README.md`에 설치·실행 순서가 있다. Python 브리지, TD 설치/어댑터, 추가 SQL 002, dev:td 모드를 구현했다. 실제 .toe 설치/카메라 설정과 클라우드 SQL 적용은 아직이다. 아래는 앞선 정리 작업의 기록이다.

최신 요구와 다음 작업 순서는 루트 `PROJECT_CONTEXT.md`, `NEXT_STEPS.md`를 읽는다.

2026-09-13 정리 작업 결과:

- 실행 코드/의존성/산출물은 모두 system/으로 이동했다. legacy/와 .toe는 수정하지 않았다.
- UI 언어를 영어로 변경했다. 모바일 질문·분석 결과 표시를 제거했다.
- Git origin과 Supabase 공개 연결 설정을 저장했다. 커밋/푸시/배포/클라우드 스키마 변경은 하지 않았다.
- Auth 설정 조회 HTTP 200, 익명 로그인 false. participants 조회 HTTP 404/PGRST205.
- TypeScript + Vite 빌드 통과. 전체 자동 테스트와 브라우저 QA는 사용자 요청에 따라 생략했다.

system/docs/history/의 초기 문서에는 이전 루트 경로와 모바일 결과 표시 요구가 남아 있다. 그대로 구현하지 않는다. system/tools/mock-worker.mjs는 개발용이며 실제 TD 브리지가 아니다.
