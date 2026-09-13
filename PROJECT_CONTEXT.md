# Not Yet Sayable V04 — 프로젝트 맥락과 시사점

다음 작업에서는 **이 문서 → NEXT_STEPS.md → 필요한 system/ 코드** 순서로 읽는다. 2026-09-13 사용자의 최신 지시이며 이전 brief보다 우선한다.

## 확정된 방향

- 메인은 루트 `NotYetSayable_V04.toe`이다. 이 파일과 `legacy/`는 이번 작업에서 수정하지 않았다.
- A/B 참가자는 서로 독립적으로 진행한다. 전역 phase 하나를 공유하지 않는다.
- **질문 문구, 튜토리얼, 분석 결과는 모두 TD 설치 화면에서 표시한다.**
- 모바일은 Consent, Confirm, 최소 상태 안내, Continue, Try Again, 최종 지도 핀 확정만 담당한다. 질문 본문·응답 원문·번역·키워드·분석을 표시하지 않는다.
- 모든 화면 문구는 **영어**다. 원본 응답의 언어는 데이터로 보존하고 TD 표시용 번역/분석을 영어로 만든다.
- TD가 지정 폴더에 이미지를 저장하고 Python이 저장 완료된 이미지를 받아 AI Vision을 호출한다. 휴대폰 촬영은 하지 않는다.
- 결과는 미러링된 오버헤드 카메라 영상 위에 텍스트 이미지로 합성한다. 영상만 먼저 미러링하고 텍스트를 나중에 올려 글자가 뒤집히지 않게 한다.
- AI 프롬프트는 아직 만들지 않는다. OCR 보정, Q1–Q4 분석, 우선순위/해석 인터페이스만 유지한다.
- 최소 디자인. 중요한 검증만 수행하고 반복 테스트·브라우저 전수 검증은 생략한다.
- 복잡한 상태/복구/TD 통합 직전에 **Astra medium 부스트 권장 구간**이라고 알린다. 모델 설정을 임의 변경하지 않는다.

## 폴더 구조

```text
NotYetSayable_V04.toe   메인 TD 프로젝트
PROJECT_CONTEXT.md     최신 맥락과 기존 구현의 시사점
NEXT_STEPS.md          다음 작업 시작점
legacy/                이전 코드·프롬프트·아카이브, 읽기 전용
system/
  web/                 최소 영어 모바일 + 운영자 화면
  supabase/migrations/ 테이블, 권한, 액션/작업 RPC
  local/processing/    Python 처리 인터페이스 (미구현)
  tools/               데모 서버, mock worker, 연결 확인
  tests/               기존 중요 상태 테스트
  docs/history/        초기 brief와 이전 설계·검증 기록
  runtime/             로컬 DB/실행 데이터 (Git 제외)
  package.json         실행은 system/ 폴더에서
```

루트 `.gitignore`/`.git`는 저장소 메타데이터다. 루트에 npm 산출물이나 개별 웹 파일을 다시 만들지 않는다.

## 기존 프로젝트에서 배운 점

`legacy/assets/lv1_ai_simple.py`는 하나의 MainPhase, capture TOP, current-cache JSON을 사용한다. 이를 A/B가 함께 쓰면 진행과 결과가 서로 덮어써질 수 있다. atomic rename은 파일 파손을 줄이지만 동시 worker의 읽기/쓰기 충돌을 막지는 못한다.

새 코드는 참가자별 상태, reset generation, revision, job ID, attempt, lease를 구분한다. 이전 결과는 현재 작업과 일치할 때만 반영한다. TD도 같은 식별자를 사용해야 한다.

아카이브의 raw_response, translated_response, keywords, trace, classification, past/present/future articulation, map 좌표, session_id는 보존할 가치가 있다. 변환 어댑터는 아직 없다. Q3→legacy Q3-1, Q4→별도 확장 필드로 연결하는 방향이며 A/B/세대별 export session_id는 충돌하지 않아야 한다.

## 현재 구현

- TypeScript/Vite WebApp, Supabase 스키마/RPC/RLS, 동일 초기 SQL을 실행하는 로컬 PGlite 데모.
- A/B 독립 진행, 중복 제출 방지, 서버 기준 3초 카운트다운, 재제출, 개별 reset/recover, QR 재발급.
- 모바일 질문/결과 출력 제거 완료. 재진행은 접힌 Repeat a step 메뉴, 직접 좌표 입력도 접힌 보조 메뉴로 유지.
- 모든 UI와 mock 결과는 영어. 실제 OCR/AI 분석은 없음.
- 최초 구현에서 자동 테스트 11개와 브라우저 전체 흐름을 확인했다. 이번 정리는 전체 테스트를 재실행하지 않고 빌드·연결 상태만 확인한다.
- TD 브리지와 설치 코드를 구현했다: `system/local/bridge.py`, `system/local/touchdesigner/install.py`, `td_adapter.py`. 동의/진행 상태 전달, 작업별 캡처 요청, 저장 완료 마커, 처리기 호출 인터페이스, 결과 업로드 재시도, A/B 미러 영상 + Text TOP 합성을 포함한다.
- TD 설치 스크립트는 **아직 실제 .toe에서 실행하지 않았다**. 이 환경에 TD 제어 API가 없으므로 사용자가 설치 명령을 실행하고 카메라 TOP 경로를 지정해야 한다. Vision 프롬프트/실제 API 호출은 아직 없다.
- `npm run dev:td`는 자동 mock worker를 끄고 Python TD 브리지용 로컬 API를 연다. 일반 `npm run dev`와 구분한다. 브리지는 운영자 페이지의 전체 Session ID 하나를 명시적으로 선택한다.
- 이번 TD 작업에서는 핵심 SQL 검증 1개와 파일 복구 검증 3개가 통과했다. 장비/브라우저 전수 테스트는 하지 않았다.

## 외부 연결 상태

- GitHub: https://github.com/arrddon/NotYetSayable.git
- 루트 Git 저장소의 origin은 위 주소다. **main 푸시 완료**, 구현 커밋은 `261989e`다. 이후 인수인계 문서 보완 커밋이 이어질 수 있다. 참가자 응답이 담긴 `legacy/data/`, 실행 데이터, 비밀키는 Git에서 제외했다.
- Supabase: https://kitibydaoavlrqqyqccb.supabase.co
- 제공된 publishable key는 `system/.env.local`과 `.env.example`에 설정했다. 브라우저용 공개 키이며 관리자/worker 비밀키가 아니다.
- 읽기 전용 확인: Auth 설정 HTTP 200, **익명 로그인 비활성화**. participants 조회 HTTP 404/PGRST205, **스키마 캐시에 테이블 없음**.
- SQL 001/002 적용, 운영자 등록, service-role 설정, TD 장비에서 설치/실행, HTTPS 배포는 아직 하지 않았다. publishable key는 다시 요청하지 않는다.

이전의 “모바일에서 질문·결과 표시” 지시는 폐기됐다. 초기 자료는 system/docs/history/에 보존하며 현재 요구로 오해하지 않는다.
