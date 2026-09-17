# CSV master flow — 2026-09-17

## Public TD QR display

Migration `supabase/migrations/202609170004_public_qr.sql` was applied remotely on
2026-09-17; anonymous read is allowed and anonymous publication is denied. On the
operator page, create A's TD display link and copy its `/display/<id>`
link into a TouchDesigner Web Render TOP. This display does not require operator login.
The display ID remains stable across `Reset A`; the operator page publishes the new
entry token automatically. The QR disappears after a participant claims A. Only show
A when running one participant at a time. The public display reveals the current
entry token by design, but never an operator credential or service-role key.

The participant entry opens Not Yet Sayable / Latent Home / Start before consent.
The interface and favicon use #1981f0 with glass controls and short status text.
Completed participants see a closing message; the operator resets the slot for the
next visitor. Final archive creation still requires all three answers and the pin.

## Current scope

The installation CSV is the source of all question, consent and tutorial copy.
Mobile shows English action buttons, a six-segment progress indicator and a final pin map.
Theme variables `--accent` and `--accent-bright` are at the top of `web/style.css`.

| CSV phase | State | Mobile action |
| --- | --- | --- |
| 0 | Idle | Scan QR |
| 1 | Consent text on TD | I agree · Begin |
| 2 | Instructions on TD | Continue |
| 3 / 6 / 9 | Q1 / Q2 / Q3 on TD | Confirm |
| 4 / 7 / 10 | Countdown / OCR / analysis | Wait |
| 5 / 8 / 11 | Result on TD | Continue |
| 12 | Q4: map only | Confirm pin |
| 13 | Complete | — |

The server requires exactly the three current answers before accepting a pin.
Q3 analysis keeps the CSV's `question_id: Q3-1`; the app and image links use question 3.
There is no fourth image or invented Q4 prompt. Retry/revisit preserves ownership,
generation, revision and job-lease checks. Revisiting clears the previous pin.

## Deployment

Existing databases: apply `supabase/migrations/202609170003_master_flow.sql`,
then the current `supabase/archive_webapp_hook.sql` in one transaction if possible.
Do not rerun initial SQL 001/002. Existing records are not deleted or reimported.
The private archive trigger now stores three linked jobs and a separate pin, with
`flow_version: csv-3q-map-v1`. Existing older archive JSON remains unchanged.
The service-role-only local-state RPC supplies the accepted job ID for each answer.

Remote application on 2026-09-17 returned `three_questions=true`,
`three_archive=true`, `browser_worker_access=false`. It created no participant records.

## Local processing and storage

Installation Python stays local and out of this GitHub repository. The local handoff
documents the additive TD upgrade; it preserves the existing bridge and camera settings.
The processor uses `gpt-5.6-sol`: one image OCR call, then the master system text plus
the phase request with recognized text substituted. API response storage is disabled;
there are no automatic billed retries. Unreadable text returns a retry error.
Only local Python reads `OPENAI_API_KEY`; never add it to Vercel or a VITE variable.

Original captures and per-job responses remain in their existing locations.
The local export additionally writes:

```text
runtime/V04/images/<participant_id>_g<generation>/Q1_<job_id>.png
runtime/V04/participants/<participant_id>_g<generation>.json
runtime/V04/response-list.json
```

JSON contains paths and job IDs, not base64 image data. The participant snapshot updates
as responses arrive and on completion; images are copied, never moved. This is local
storage, not an off-device backup or a cloud image upload. The separate Supabase archive
is created on pin completion. The old manual archive_put CLI still accepts its older
four-answer import contract; use the completion flow for new three-answer records.

## Navigation boundary / next task

This task provides an updating TD response table and a stable auto-focus target for
the latest response or completed pin. Focus is identified by participant/generation/
question and accepted job ID, not a changing row number. The feed is local and private.

Next task: connect that focus to the installation map camera and add the full navigation
experience. Reference legacy map assets without modifying them: renew_table.py,
nav_controller_html.html, controller_html.html and webserver1_callbacks.py. The old
auto_nav_random.py is a stub. Whole-archive sync, map camera movement, clusters/LOD and
manual navigation controls are deliberately deferred.

## Verification boundaries

- State/security tests cover three answers, pin, retry, reset and job linkage.
- Python tests cover CSV mapping, output validation, file recovery and separated exports.
- A real synthetic handwriting-font image passed OCR and analysis with gpt-5.6-sol.
  The successful two-call test used an estimated USD 0.007096. One earlier printed-text
  OCR test was rejected; no participant or legacy image was sent. No further paid tests ran.
- Real handwriting accuracy, physical A/B completion and the TD node upgrade still need
  the installation operator to verify after reloading the adapter.

API references: [model](https://developers.openai.com/api/docs/models/gpt-5.6-sol),
[image input](https://developers.openai.com/api/docs/guides/images-vision).
