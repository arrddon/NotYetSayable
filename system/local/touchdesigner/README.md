# TouchDesigner connection

## What is implemented

- `install.py` creates `/project1/nys_bridge` with separate A/B state, camera select, mirror, Text TOP, Composite TOP and output nodes.
- `td_adapter.py` runs on TD's main thread. It reads local state, exposes consent/step/status parameters and saves requested images asynchronously.
- `../bridge.py` runs in external Python. It reads Supabase or the local TD demo, claims jobs, publishes state files, waits for capture-complete markers and uploads processor results.
- Duplicate claims and capture events are suppressed. A reset invalidates older results. Uploads are persisted before network calls. Uncertain processing after a crash returns an error rather than repeating a potentially billed AI call.
- Question copy is blank. Add the English Q1–Q4 text later in the `copy` DAT. AI prompts are not implemented.

**The installer has not been executed in the user's TouchDesigner session. The root .toe has not been modified.** The supplied environment has no callable TD control API. Run the following once in TD, then save the project manually after checking the nodes.

## 1. Install in the root V04 project

Open `NotYetSayable_V04.toe`, open Textport, and run:

```python
exec(open(project.folder + '/system/local/touchdesigner/install.py', encoding='utf-8').read())
```

The installer refuses to overwrite an existing `nys_bridge`. Do not run it repeatedly. The controller imports the adapter from disk; restart TD after editing that external Python module. Changes to the node-generation script require deliberate manual integration, not automatic deletion of existing nodes.

Inside `/project1/nys_bridge/settings`, fill:

| Key | Value |
|---|---|
| camera_A | Absolute TD path of participant A's capture TOP, e.g. `/project1/capture_A` |
| camera_B | Absolute TD path of participant B's capture TOP, e.g. `/project1/capture_B` |
| python | Existing Python executable. A bundled Codex Python path is prefilled; replace if unavailable. Do not use TouchDesigner.exe. |

Use the correct A/B crop if sharing a camera. The capture source should be readable, unmirrored handwriting; only the display branch is mirrored. `A/out` and `B/out` are the composited display outputs.

The A/B Base COMP custom parameters expose `Consented`, `Step`, `Status`, `Question`, `Generation`. The full participant JSON is in `A/state` / `B/state`. Consent immediately sets these values and switches the overlay to tutorial text. To trigger an existing animation, add its participant-specific pulse to `hooks.on_consent(slot, participant)`. The default hook only logs the consent; it does not guess existing project node names. `on_state` runs on state revisions and can drive an existing display network.

## 2. Local TD demo (no cloud credentials needed)

Stop the ordinary local demo with Ctrl+C first. Then, from the project root:

```powershell
cd system
npm.cmd run dev:td
```

Open <http://127.0.0.1:5173/operator>. Create a session. Copy its full **Session ID**, now shown below the session selector. The TD demo does not start the automatic mock worker.

Start the Python bridge from the TD Textport:

```python
op('/project1/nys_bridge/controller').module.start('PASTE-SESSION-UUID', demo=True, mock=True)
```

Open A/B participant links on this PC. Agree on the phone/controller page: the corresponding TD state should change to tutorial. Continue, then Confirm. After 3 seconds TD saves the camera image; the Python bridge returns an English `[TEST]` result displayed over the camera. No camera or microphone access is requested from the browser. Phone access from another device requires the real HTTPS/Supabase setup.

To stop the child bridge before changing sessions:

```python
op('/project1/nys_bridge/controller').module.stop()
```

The bridge intentionally watches one explicit session. Creating a new operator session does not switch the bridge automatically. Stop/start with the new Session ID. TD's timeline must be cooking for the Execute DAT and heartbeat to run.

## 3. Real Supabase

Apply both migrations, in order, with a Supabase management connection:

1. `system/supabase/migrations/202609130001_core.sql`
2. `system/supabase/migrations/202609130002_td_bridge.sql`

Enable anonymous sign-ins and register the operator as described in `system/docs/SUPABASE_SETUP.md`. Put `SUPABASE_SERVICE_ROLE_KEY` in the ignored `system/.env.local` (no `VITE_` prefix). The provided publishable key is already configured but cannot perform these management operations.

Run the actual frontend with `npm.cmd run dev:supabase`. Start the TD bridge with `demo=False, mock=True` for the first controlled capture test. Do not run `npm run dev` or `npm run mock-worker` against the same work queue.

## 4. Later Vision processor contract

Once prompts are supplied, implement an external Python script. It receives one JSON object on stdin:

```json
{"job":{"id":"...","slot":"A","question":1,"generation":1,"attempt":1},"image_path":".../captures/A/job-id.png"}
```

It must return a single result JSON object on stdout with `raw_response`, `translated_response`, `keywords`, `trace`, `classification`. Send diagnostics to stderr. Preserve raw text; use English translated_response/trace for display. No processor path means no real AI call is possible.

Start with `mock=False, processor=r'ABSOLUTE-PROCESSOR-PATH.py'`. The processor runs outside TD, at most two jobs concurrently, with a 60-second subprocess timeout. The DB job deadline remains 90 seconds. Do not silently retry AI requests inside the processor unless the API's idempotency semantics are known.

## Recovery and files

All generated files are under the ignored `system/runtime/`:

- `state/A.json`, `state/B.json`: authoritative snapshots with freshness timestamps.
- `requests/A.json`, `requests/B.json`: current capture request.
- `captures/A/<job_id>.png` and `.json`: completed capture and completion marker.
- `jobs/<job_id>.json`: durable bridge journal; `results/<job_id>.json`: saved processor result.
- `td/attempts/`: written before capture; prevents uncertain automatic recapture after restart.
- `td/seen/`: consent notification identity. State is restored on every TD restart without repeating the same consent pulse.
- `td/heartbeat.json`, `bridge-status.json`, `bridge.log`: local connection status and logs.

No marker means no processing. An uncertain capture yields `CAPTURE_UNCERTAIN`; an interrupted processor yields `PROCESSING_UNCERTAIN`. Use the operator recovery button, then participant Try Again. A retry creates a new job and fresh countdown.

Offline state is not used to begin captures. TD requires a fresh state and request; the bridge requires a fresh TD heartbeat for the selected session before claiming. Already confirmed images/results remain on disk for recovery. Results are displayed from accepted server state, not unaccepted local output.

The DB result currently enables mobile Continue before a separate TD-render acknowledgement. The adapter updates its overlay on the next poll; a stricter display acknowledgement can be added later if needed.

API references used: [TOP save](https://docs.derivative.ca/ScriptTOP_Class), [Execute DAT](https://derivative.ca/UserGuide/Execute_DAT), [Text TOP](https://docs.derivative.ca/Text_TOP), [Composite TOP](https://derivative.ca/UserGuide/Composite_TOP).
