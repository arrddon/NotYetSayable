# Not Yet Sayable V04 — 다음 task

**PROJECT_CONTEXT.md → 이 문서 → system/local/touchdesigner/README.md** 순서로 읽는다. 초기 요구보다 최신 문서가 우선한다.

## 이번에 완료한 코드

GitHub main에 구현 커밋 `261989e`를 푸시했다. 인수인계 문서 보완도 같은 브랜치에 포함한다.

- Python 브리지: `system/local/bridge.py` (표준 라이브러리만 사용).
- TD 설치/어댑터: `system/local/touchdesigner/install.py`, `td_adapter.py`.
- Supabase 추가 마이그레이션: `202609130002_td_bridge.sql`의 local-state 읽기, 세션별 멱등 claim.
- 동의/단계/결과 → A/B 로컬 state 파일 → TD 상태 파라미터/overlay.
- TD job별 이미지 저장 → 완료 마커 → 외부 처리기 → 결과 파일/DB 업로드.
- 불확실한 재촬영/AI 재호출 방지, reset 후 오래된 결과 차단.
- `npm run dev:td` 모드와 운영자 화면 전체 Session ID 표시.
- 핵심 SQL 테스트 1개, 파일 복구 테스트 3개 통과. 실제 장비 검증은 하지 않음.

## 다음 목표: 실제 TD에 설치하고 한 번 촬영

TD 제어 도구가 없어서 **루트 .toe는 변경하지 않았다**. 설치 스크립트를 준비한 상태다. 다음 task에서 이미 설치됐는지 먼저 사용자/실제 TD 상태로 확인하고 중복 생성하지 않는다.

TD Textport에서 한 번 실행:

```python
exec(open(project.folder + '/system/local/touchdesigner/install.py', encoding='utf-8').read())
```

생성되는 `/project1/nys_bridge/settings`에 실제 `camera_A`, `camera_B` TOP 경로와 외부 Python 실행 경로를 설정한다. 생성된 `A/out`, `B/out`은 미러 카메라 + 영어 텍스트 합성 출력이다. 질문 본문은 `copy` DAT의 Q1–Q4에 나중에 넣는다.

설치하면 `A/B` COMP에 Consented/Step/Status/Question/Generation 파라미터가 생긴다. 동의는 tutorial 상태와 TD 안내 표시를 시작한다. 기존 TD 애니메이션을 pulse하려면 `hooks.on_consent`에 **실제 노드명**을 연결해야 한다. 현재 기본 hook은 로그만 출력하고 모르는 노드를 추측하지 않는다.

## 로컬로 먼저 연결

기존 일반 데모를 중지한 후 `system/`에서 `npm.cmd run dev:td`를 실행한다. 운영자 페이지에서 세션을 만들고 전체 Session ID를 복사한다. TD Textport에서:

```python
op('/project1/nys_bridge/controller').module.start('SESSION-UUID', demo=True, mock=True)
```

모바일용 참가자 링크를 이 PC에서 열어 동의 → Continue → Confirm한다. 3초 후 지정 카메라 TOP이 저장되고 TD에 `[TEST]` 결과가 표시되는지 확인한다. 새 세션으로 바꾸려면 controller.stop() 후 새 ID로 시작한다. 자동으로 최신 세션으로 전환하지 않는다. 실제 Vision 호출은 하지 않는다.

## 실제 Supabase 연결

URL/publishable key는 `system/.env.local`에 이미 있다. 다시 요청하지 않는다. 마지막 조회에서는 익명 로그인 false, participants 테이블 없음이었다. 다음 task에서 현재 상태를 다시 확인한다.

1. 관리자 연결 또는 SQL Editor로 마이그레이션 001 → 002를 적용한다.
2. 익명 로그인 활성화, 운영자 Auth 사용자 UUID를 `nys_private.operators`에 등록한다.
3. 로컬 service-role 키를 `.env.local`의 SUPABASE_SERVICE_ROLE_KEY에 설정한다. 브라우저/VITE_ 변수/Git에 넣지 않는다.
4. `npm run dev:supabase`와 TD controller.start(..., demo=False, mock=True)로 첫 실제 통신을 확인한다.
5. 휴대폰 접속용 HTTPS 배포를 진행한다. localhost QR은 다른 기기에서 접속할 수 없다.

실제 Supabase 스키마 적용은 아직 하지 않았다. 인증된 관리 접근 없이 publishable key만으로 SQL을 적용할 수 있다고 가정하지 않는다.

## 실제 Vision은 그다음

사용자가 프롬프트를 제공하면 외부 Python 처리기를 만든다. stdin은 `{job, image_path}`, stdout은 `{raw_response, translated_response, keywords, trace, classification}` JSON이다. 진단은 stderr. TD controller.start(..., mock=False, processor=...)로 연결한다. 원문은 보존하고 TD 표시용 번역/trace는 영어다. 현재 처리 인터페이스만 있으며 실제 AI 프롬프트/API 호출은 없다.

결과 DB 저장 즉시 모바일 Continue가 활성화된다. 엄격한 TD 표시 완료 확인이 필요하면 render acknowledgement를 추가한다. 지금은 TD가 다음 폴링에서 결과를 표시한다.

## 운영·Git 주의

- 루트 TD 파일, 이 두 인수인계 문서, legacy/, system/ 구조를 유지한다.
- 참가자 데이터 `legacy/data/`, runtime/, 비밀키는 로컬 보존하고 Git 제외한다. 소스/문서와 TD 파일을 푸시한다.
- 복잡한 장비/복구 수정은 Astra medium 부스트를 알린다. 중요 검증 외에는 테스트를 반복하지 않는다.
- 실제 설치/저장/촬영 여부는 코드 구현과 구분해 보고한다.

## 다음 task 요청 예시

> PROJECT_CONTEXT.md와 NEXT_STEPS.md, system/local/touchdesigner/README.md를 읽고 시작해. TD 브리지 코드는 있으니 실제 .toe 설치 여부와 A/B 카메라 TOP 경로부터 확인해서 Consent → TD 시작 → Confirm → 이미지 저장을 연결해줘. 그다음 Supabase 실제 설정과 HTTPS 접속을 진행해. 질문/결과는 TD에서 영어로만 표시하고 AI 프롬프트는 아직 만들지 마. 중요한 검증만 해줘.
