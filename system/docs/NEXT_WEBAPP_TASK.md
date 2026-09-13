# Next task: Supabase + HTTPS WebApp

## Scope

GitHub `arrddon/NotYetSayable` is **WebApp-only**. Do not add legacy/, .toe files, local Python/TD code, raw participant archives, runtime/, node_modules/, or secret keys to Git. The application root is `system/`; preserve the existing TypeScript/Vite architecture.

Mobile UI is English and minimal: consent, confirm, countdown, waiting, continue, retry, map pin. Do not restore question copy or analysis results to the phone. Those belong to the separate TD display.

## Goal

Make the real Supabase-backed WebApp available at an HTTPS URL so two phones can independently join A/B through QR codes. Complete authorised implementation and deployment work, not a plan only. Update this document and push WebApp changes when finished.

## Starting state

- Supabase URL: https://kitibydaoavlrqqyqccb.supabase.co
- Publishable key is already in system/.env.example; the existing working directory also has .env.local. Do not ask for it again.
- Last read-only check: Auth available, anonymous sign-ins disabled, participants table absent. Recheck before applying migrations.
- Apply SQL 001 then 002 only if not already installed. Never rerun the initial migration over existing tables.
- TD/Python is maintained separately on the installation PC. The WebApp exposes durable SQL state/job contracts; no actual Vision prompts have been provided.

## Work sequence

1. Read package.json, web/api.ts, web/main.ts, migrations 001/002, docs/SUPABASE_SETUP.md.
2. Check real Supabase availability and configuration. If authenticated management access is available, apply missing migrations and verify Auth/Realtime/RLS. Do not bypass access controls or treat the publishable key as a management key.
3. Prepare production build and HTTPS hosting using the existing app. Hosting root is system, build command npm run build, output dist. Configure SPA fallback for /operator, /join, /participant/*. Keep service-role credentials off the browser and hosting public environment.
4. Verify operator login/session creation, QR entry, A/B isolation and initial state fetch plus Realtime resync. Mock processing is allowed only when clearly marked and explicitly enabled; never claim TD hardware or AI was tested.
5. Focus checks on duplicate Confirm, stale/reset results, refresh and reconnection. Avoid repeated full test suites, cosmetic changes, and new features.
6. Commit/push only WebApp code/config/docs. Record the deployed URL, checks performed and remaining external actions.

## If the user is away

Make progress on independent code, build, hosting configuration, and setup documentation when credentials or Auth setup are missing. Document the exact blocked action and required setting. Never invent credentials, create accounts on the user's behalf without authorisation, or report an unverified live connection as working. Do not keep repeating unchanged checks or burn usage with purposeless loops.

## Success criteria

- Working HTTPS entry URL and SPA refresh support.
- Server state controls independent A/B mobile flows.
- No participant can read/write the other participant's data.
- No secret key in Git or browser build.
- Minimal English mobile UI; questions/results remain in TD.
- Concise handoff documenting actual deployed and verified state.
