# Supabase 연결

> 최신 지시는 루트 PROJECT_CONTEXT.md/NEXT_STEPS.md가 우선합니다. 실행 위치는 system/입니다. URL/publishable key는 .env.local에 이미 있습니다. 아래 예제 값으로 기존 설정을 덮어쓰지 마세요. 2026-09-13 확인: 익명 로그인 비활성화, participants 테이블 없음. 모바일 질문/결과 표시는 제거했고 TD가 담당합니다.

이 단계는 아직 실행하지 않았습니다. 새 Supabase 프로젝트에 적용하는 초기 마이그레이션입니다. 비어 있지 않은 다른 프로젝트에 그대로 적용하지 마세요.

## 1. 데이터베이스와 인증

1. SQL Editor에서 `supabase/migrations/202609130001_core.sql`, 이어서 `202609130002_td_bridge.sql`을 적용합니다. 이미 적용한 마이그레이션은 다시 실행하지 않습니다.
2. Supabase Auth에서 Anonymous Sign-ins를 활성화합니다. 참가자는 별도 계정 입력 없이 익명 인증 세션을 발급받고, QR 토큰으로 자신의 참가자에 연결됩니다.
3. 운영자용 이메일/비밀번호 사용자를 Supabase Auth에 만듭니다. 사용자 UUID를 아래 SQL에 넣어 운영자 권한을 부여합니다.

```sql
insert into nys_private.operators(user_id)
values ('운영자-Auth-사용자-UUID');
```

4. Realtime publication `supabase_realtime`에 `public.participants`가 포함됐는지 확인합니다. 초기 마이그레이션은 해당 publication이 있으면 자동으로 추가합니다.
5. `public`만 Data API에 노출하고 `nys_private`는 노출하지 않습니다.

RLS로 읽기를 제한하며, 참가자에게 직접 INSERT/UPDATE/DELETE 권한은 없습니다. 상태 변경은 소유자, 현재 세대, revision을 확인하는 RPC만 수행합니다. 운영자 화면과 참가자 화면은 별도의 브라우저 인증 저장 키를 사용합니다.

## 2. 환경변수

`.env.example`을 `.env.local`로 복사한 후:

```dotenv
VITE_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=YOUR_PUBLISHABLE_KEY
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_SERVICE_ROLE_KEY=YOUR_SERVICE_ROLE_KEY
NYS_MOCK_WORKER=true
```

`VITE_` 두 변수만 브라우저 번들에 포함됩니다. **service-role 키는 절대 `VITE_` 접두어를 붙이지 않습니다.** `.env.local`은 버전 관리에서 제외됩니다.

```powershell
npm.cmd run dev:supabase
```

별도 터미널에서 테스트 결과 처리기를 시작합니다.

```powershell
npm.cmd run mock-worker
```

이 처리기는 Supabase의 대기 작업을 읽고 테스트 결과를 씁니다. 실제 참가자 운영에는 사용하지 않습니다. `NYS_MOCK_WORKER=true`를 명시하지 않으면 실행을 거부합니다. 미래의 TD 브리지와 동시에 실행하지 않습니다.

## 3. 휴대폰 테스트

`npm.cmd run build` 후 `dist/`를 HTTPS 정적 호스팅에 배포합니다. `/operator`, `/join`, `/participant/*` 요청을 `index.html`로 돌려주는 SPA fallback을 설정해야 합니다. 같은 호스트의 `/operator`에서 QR을 만들어야 참가자가 실제 배포 주소로 접속합니다.

휴대폰에서 A/B QR을 각각 열고 새로고침, 잠금 후 복귀, 연결 끊김, 동시에 Confirm, 운영자 초기화를 확인합니다. QR은 한 브라우저 인증 세션에 연결됩니다. 다른 브라우저로 옮겨야 하면 **입장 링크 재발급**을 사용합니다. QR 만료는 발급 후 4일입니다.

지도는 Leaflet와 OpenStreetMap 표준 타일을 사용하고 저작자 표시를 유지합니다. 타일 오류 시 좌표 입력으로 확정할 수 있습니다. 전시용 타일 제공자와 사용 조건은 설치 환경에 맞춰 확정하세요. 현재 동의문과 질문은 기능 테스트용이므로 전시 문구로 교체해야 합니다.

## 연결 후 확인할 항목

- A 계정에서 B 데이터를 조회/수정할 수 없는지 실제 Data API로 확인
- 익명 인증이 현장 네트워크의 인증 제한에 걸리지 않는지 확인
- Realtime 연결 및 재연결 시 최신 화면 복원 확인
- 2개 휴대폰의 동시 Confirm과 실제 DB lock 경합 확인
- worker 중단 → 운영자 응답 없음 표시 → 복구 → Try Again 확인
- 온라인 복귀 후 미확인 요청을 같은 요청 ID로 재확인

참고: [익명 인증](https://supabase.com/docs/guides/auth/auth-anonymous), [DB 함수](https://supabase.com/docs/guides/database/functions), [RLS](https://supabase.com/docs/guides/database/postgres/row-level-security), [Postgres Changes](https://supabase.com/docs/guides/realtime/postgres-changes), [OSM 타일 정책](https://operations.osmfoundation.org/policies/tiles/).
