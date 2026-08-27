# Pipeline Observer dashboard

Pipeline Observer is the repository-owned, read-only view of one v3 production attempt. It does not keep a second database and does not rewrite pipeline state. Every visible relationship comes from an exact entity ID, receipt binding, or media path in the current attempt. Files that exist without one of those bindings are shown as unreferenced warnings rather than being connected by filename guesses.

The v3 `init` command starts one detached observer for the new attempt and opens it in the local browser automatically. Its session record and log stay under `<attempt>/.dashboard/`; a later launch reuses a responsive session instead of creating another server. Dashboard startup failure is reported in the `init` result but does not block production.

## Open it

From the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m ai_video_pipeline.v3.cli \
  dashboard runs/<production>/attempts/<attempt>
```

The installed console entry point is equivalent:

```bash
.venv/bin/ai-video-dashboard runs/<production>/attempts/<attempt>
```

To start or reuse the background observer without occupying the current terminal:

```bash
PYTHONPATH=src .venv/bin/python -m ai_video_pipeline.v3.cli \
  dashboard runs/<production>/attempts/<attempt> --detach
```

The server binds only to the local computer (`127.0.0.1` or `localhost`) and opens the default browser. Use `--no-open` when Codex CLI is running without a desktop browser, or `--port 4173` when a stable local port is useful for a foreground server. Detached mode always chooses an available loopback port. Stop a foreground server with `Ctrl-C`.

For an explicitly headless or test-only production, `init --no-dashboard` suppresses automatic launch. Normal production should leave the default enabled.

## Codex app and CLI connection

The dashboard command is part of this repository, so Codex does not need a separate dashboard account, remote API, or credential. In the Codex app, open this repository and ask it to open the Pipeline Observer for a named attempt; Codex can run the command and open the returned local URL. In Codex CLI, ask the same from the repository root or run the command directly and open the printed URL.

This connection is intentionally one-way. Codex and the pipeline continue to own production writes. The dashboard exposes only `GET` and `HEAD`; create, edit, regenerate, approve, and state-transition requests are rejected. A later control surface can be added as a separate authenticated command layer without changing this observer contract.

## What is visible

- all nine v3 stages, including `05.5-motion-prompt`, their state, stage attempts, integrity reports, fresh-context critiques, sealed artifacts, and receipts
- Stage 01 contracts and subjects
- Stage 02 boards, structured meta-prompts, panel plans, image attempts, and cross-board review
- Stage 03 sequences, scenes, events, and new-reference debt
- Stage 04 scene treatments, setups, shots, composition, camera, performance, and timing data
- Stage 05 reused and new references, preflight, start plates, prompts, and image attempts
- Stage 05.5 final plate-grounded C01 prompts and their shot, plate, and reference inputs
- Stage 06 motion jobs, every generated take, prompts, review evidence, and selected take
- Stage 07 timeline segments, source takes, edit decisions, and master media
- Stage 08 receipt-backed review dimensions, defects, and internal release eligibility

Click a node to inspect its structured JSON, prompt text, image/video/audio, direct inputs and outputs, files, and retry history. Failed attempts remain selectable beside the final selected attempt. Selecting a node highlights its complete connected lineage. The canvas supports pan, zoom, minimap navigation, stage focus, search, and overview/compact/detail semantic zoom.

The browser refreshes the snapshot every two seconds using an ETag. Each changed snapshot is rebuilt from current state, receipts, artifacts, validation, critique, prompts, and media paths. Unchanged polls transfer no snapshot body. Live updates preserve the user's current zoom and canvas position rather than repeatedly fitting the entire pipeline. The server reads only the selected attempt directory and streams video with HTTP byte ranges, so long local files can seek without being loaded into memory in full.

## GitHub and portable bundles

The editable React Flow + ELK source is in `dashboard/`. A production build is committed under `src/ai_video_pipeline/dashboard_static/` and included as Python package data. Normal users therefore need only the Python installation; Node.js is not required to run the dashboard.

When editing the UI, rebuild it before committing:

```bash
cd dashboard
npm ci
npm run build
```

`package-lock.json` fixes the frontend dependency graph. The portable packager includes the editable dashboard source, the production build, dashboard tests, and the Python server. It excludes `node_modules/`.

## Safety boundaries

- binding to non-loopback interfaces is rejected
- resolved file paths must stay inside the selected attempt
- path traversal and symlink escape are rejected
- text previews are capped at 2 MB
- media responses use no-store caching and same-origin browser policy
- no write endpoint, shell endpoint, Codex command endpoint, or arbitrary path browser exists
