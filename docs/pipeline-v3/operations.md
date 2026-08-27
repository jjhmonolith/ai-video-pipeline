# Pipeline v3 operations

Use the project virtual environment because it contains the declared imaging dependencies.

## Initialize

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m ai_video_pipeline.v3.cli \
  init runs/<production>/attempts/<attempt> \
  --direction "<user direction verbatim>" \
  --mode normal --by user --reason "new production"
```

Use `--mode fast_track` only when the user explicitly selected it.

Initialization automatically starts and opens the attempt's read-only Pipeline Observer. Its launch status and URL are included in the command result. Use `--no-dashboard` only for an explicitly headless or test run; dashboard failure never changes pipeline state or blocks Stage 01.

## Drive one loop

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m ai_video_pipeline.v3.cli work <attempt>
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m ai_video_pipeline.v3.cli submit <attempt>
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m ai_video_pipeline.v3.cli review <attempt>
```

`work` returns the current stage skill, exact artifact/critique paths, upstream receipt bindings, retry number and strategy, last failed evidence, and critic rubric. For Stage 02 it additionally returns `stage_inputs`: exact Stage 01 definitions and clauses, canonical kind-spec hashes, the fixed `1672x941` landscape sheet canvas, and nine required panel IDs. The LLM skill writes the requested artifact. `submit` performs deterministic integrity checks. After it returns `critic_required`, a fresh-context LLM writes the critique and `review` records its decision.

Continue immediately on `needs_repair` or after a receipt is sealed. Wait only on `human_gate`, safety/authority/contract boundary, unavailable required runtime, or exhausted non-fast-track attempts.

`05.5-motion-prompt` runs after the Stage 05 gate is resolved. It adds no human gate, generates no media, and may not return a selected plate for regeneration. After its AI critique passes, continue directly to `06-motion`; C01 must use its final prompt verbatim.

## Human gate

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m ai_video_pipeline.v3.cli \
  approve <attempt> --stage 05-plate --by user --decision approve
```

Valid decisions are `approve`, `revise`, and `reject`. Revisions use a remaining retry; rejection blocks the attempt.

## Mode change

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m ai_video_pipeline.v3.cli \
  set-mode <attempt> fast_track --by user --reason "explicit autonomous run request"
```

An explicit switch to fast-track at a passed AI preflight human gate seals that stage and continues. External side effects remain false.

## Verify

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m unittest \
  tests.test_v3_integrity tests.test_v3_orchestrator -v
```

The full legacy-plus-v3 test suite remains useful for compatibility adapters, but v3 tests define the new creative/state boundary.

## Observe a live attempt

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m ai_video_pipeline.v3.cli \
  dashboard runs/<production>/attempts/<attempt>
```

This opens the local, read-only Pipeline Observer. It shows direct stage inputs and outputs, prompts, structured artifacts, media, receipts, validation, critiques, and failed retry history. The same repository command can be started by Codex app or Codex CLI. See `dashboard.md` for the graph contract, GitHub packaging, and safety boundary.
