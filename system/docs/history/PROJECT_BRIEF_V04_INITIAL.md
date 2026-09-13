# Not Yet Sayable: Latent Homes
## V04 Development Brief

This is a new version of the project.

The `legacy/` folder contains the previous implementation, prompts, session data, and archive structure.
Do not modify or overwrite legacy files.
Use them only as reference for compatibility and data migration.

## Core System

The installation has two independent participants, A and B.

Each participant uses their own phone to access a WebApp through a session-specific QR code.

The WebApp is used only for:
- consent
- tutorial
- step progression
- confirm actions
- viewing returned analysis
- final map pinning

Each participant progresses independently.

Participant A and B may be on different steps at the same time.

## Main Local System

TouchDesigner is the main local application.

TouchDesigner should:
- receive participant actions
- trigger local camera capture
- call Python scripts
- run OCR
- later call AI APIs
- update participant state/results
- drive the real-time visualisation

Communication between TouchDesigner and external Python processes may use OSC.

## Server / State

Use Supabase for:
- participant/session state
- realtime updates
- WebApp ↔ local system communication
- storing processed text and analysis results

The WebApp should:
1. fetch the latest participant state when loaded or refreshed
2. subscribe to realtime state updates
3. render the correct screen based on server state

Browser refresh and back navigation must be supported.

## Interaction Flow

For each response step:

Participant presses Confirm
→ 3 / 2 / 1 countdown
→ capture request is sent
→ local system captures the image
→ OCR / processing runs
→ result is written back
→ WebApp receives realtime update
→ result screen appears
→ participant continues

No skip option.

If processing fails:
- show Try Again

If internet connection fails:
- show Internet Error

Prevent duplicate submissions and double clicks.

If a participant revisits and resubmits a previous step:
- overwrite the previous result

## Operator Page

Create an operator/master interface for exhibition control.

It must allow:
- viewing A and B current states
- resetting A independently
- resetting B independently
- recovering from stuck/error states
- generating a new session / QR entry

## Legacy Compatibility

Preserve compatibility with the existing archive structure where practical.

Important legacy concepts include:
- raw_response
- translated_response
- keywords
- trace
- classification
- past / present / future articulation
- map coordinates
- session_id

The new system adds a fourth place-related prompt before or together with map pinning.

Do not design the new AI prompts yet.

Create placeholders for:
- OCR post-processing
- Q1 analysis
- Q2 analysis
- Q3 analysis
- Q4 analysis
- priority / interpretation logic

The actual AI prompts will be provided later.

## Development Approach

Design the codebase and folder structure yourself.

Prioritize:
- reliability in a 3-day exhibition
- simple recovery
- clear state management
- minimal dependencies
- readable code
- separation between WebApp, server state, and TouchDesigner/local processing