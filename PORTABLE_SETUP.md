# AI Video Pipeline v3 portable setup

This bundle moves the v3 orchestration code, all nine project-local Codex stage skills, deterministic validators, the Pipeline Observer dashboard, low-level compatibility adapters, contracts, focused tests, and operating documentation to another computer.

It deliberately excludes production runs, generated media, caches, virtual environments, secrets, credentials, provider accounts, video models, and local generation servers.

## Recommended: clone the GitHub repository

A Git checkout is the recommended installation when the computer should receive future updates:

```bash
git clone https://github.com/jjhmonolith/ai-video-pipeline.git
cd ai-video-pipeline
uv sync --frozen
```

Check for an update without changing the checkout, then apply a clean fast-forward update and synchronize dependencies:

```bash
.venv/bin/python scripts/update_from_github.py --check
.venv/bin/python scripts/update_from_github.py --sync
```

The updater refuses dirty source trees, detached revisions, divergent history, and non-fast-forward changes. Ignored production runs and media are not overwritten. A portable ZIP from GitHub Releases is an immutable snapshot and should be replaced with a newer release rather than updated in place.

## 1. Extract and enter the project

Keep the extracted directory intact. In particular, do not move `.agents/skills/` away from the project root.

```bash
cd ai-video-pipeline-v3
```

## 2. Install Python dependencies

Python 3.9 or newer is required. `uv` is the preferred reproducible path:

```bash
uv sync --frozen
```

Without `uv`, create a virtual environment and install the project with pip:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install .
```

On Windows, replace `.venv/bin/python` with `.venv\Scripts\python.exe`.

The bundle does not vendor third-party wheels. The target computer therefore needs package-index access or a separately prepared trusted wheelhouse.

## 3. Verify the copied bundle

Before installing anything, verify that files match the packaging manifest:

```bash
python3 scripts/verify_v3_portable.py --manifest
```

After dependency installation, run the full local preflight:

```bash
.venv/bin/python scripts/verify_v3_portable.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m unittest \
  tests.test_portable_package \
  tests.test_run_layout \
  tests.test_v3_dashboard \
  tests.test_v3_integrity \
  tests.test_v3_orchestrator \
  tests.test_v3_end_to_end -v
```

The preflight checks Python, required packages, FFmpeg/FFprobe, the nine-stage order, and every project skill entrypoint. It cannot prove access to a GUI image generator or a separately configured video-generation service.

## 4. Open the folder as a Codex project

Open the extracted project root in Codex. The root `AGENTS.md` routes production work through `.agents/skills/video-pipeline-orchestrator/SKILL.md`; do not copy the stage instructions into a global prompt.

Initialize a production attempt with the v3 CLI or ask Codex to start the v3 pipeline. CLI example:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python \
  -m ai_video_pipeline.v3.cli init \
  runs/<production>/attempts/<attempt> \
  --direction "<user direction verbatim>" \
  --mode normal --by user --reason "new production"
```

Use `fast_track` only after an explicit user request for that attempt.

The initialization command opens the new attempt's local Pipeline Observer automatically. Add `--no-dashboard` only on a deliberately headless or test machine.

Open the read-only dashboard for an attempt with:

```bash
.venv/bin/ai-video-dashboard runs/<production>/attempts/<attempt>
```

Codex app or Codex CLI can start this same repository command. The packaged production UI is already included, so Node.js is not required to view an attempt. Node.js and `npm ci && npm run build` inside `dashboard/` are required only when changing the dashboard frontend.

## 5. Reconnect computer-specific media capabilities

These are intentionally not portable inside the ZIP:

- Codex or another image-generation capability used by Stages 02 and 05
- the configured image-to-video runtime used by Stage 06
- model weights, custom nodes, GPU drivers, local servers, provider accounts, and credentials
- fonts, codecs, or licensed media not already stored as production inputs

Install or connect them separately on the target computer and keep credentials outside this project. Stage 06 discovers the current configured video runtime; the bundle does not hardcode the source computer's host, port, model path, or token.

## 6. What not to copy from the source computer

Do not manually add `.secrets/`, `.venv/`, caches, provider tokens, keychain exports, or old `runs/` to the portable ZIP. Transfer a specific production attempt separately only when its media rights and credentials permit it.

## Rebuild the bundle

From a verified source checkout:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/package_v3_portable.py
```

The packager uses an allowlist, scans included content for common secret formats, writes SHA-256 manifests, and refuses symlinks.
