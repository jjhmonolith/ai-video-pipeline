---
name: video-pipeline-orchestrator
description: Run or resume this repository's nine-stage LLM-authored video production pipeline, including the Stage 05.5 approved-plate motion-prompt refinement, while dispatching integrity checks, independent LLM critics, varied repair loops, receipts, and mode-specific gates. Use whenever a production attempt should start, continue, recover, or finish.
---

# Video Pipeline Orchestrator

Treat this skill as the only production entry point. Keep creative authorship in the stage skills and keep Python limited to form, provenance, state, file, pixel, duration-arithmetic, and authority checks.

Before acting, read [references/architecture.md](references/architecture.md) and [references/insights.md](references/insights.md). Read [references/artifact-contract.md](references/artifact-contract.md) when writing an artifact or critique.

## Run the state machine

1. Locate the exact attempt directory under `runs/<production>/attempts/<attempt>/`. Do not mutate another attempt or the archived v2 snapshot.
2. If `pipeline-state.json` does not exist, initialize v3 with the user's direction verbatim. Default to `normal`; select `fast_track` only when the user explicitly requested it for this attempt. The `init` command opens that attempt's read-only Pipeline Observer by default. Keep the local dashboard launch enabled during production; use `--no-dashboard` only for an explicitly headless or test run. If `init` reports dashboard launch failure, retry once with `PYTHONPATH=src python3 -m ai_video_pipeline.v3.cli dashboard <attempt> --detach`; a sandboxed Codex host may require permission for the local loopback server. Report any remaining observer failure but continue production because it owns no state transition or approval gate.
3. Request one work order with `PYTHONPATH=src python3 -m ai_video_pipeline.v3.cli work <attempt>`.
4. Read only the skill named by `stage_skill`, its directly referenced authoring file, the work order, and the upstream artifacts named by its receipt list.
5. Act as the stage author. Write exactly one candidate to `artifact_path`; do not use a deterministic compiler to invent creative prose or prompts.
6. Submit the candidate. Repair deterministic omissions immediately when `needs_repair` is returned.
7. After integrity passes, perform a fresh-context semantic or visual review. Re-read the artifact as a critic, use every `critic_criteria` item in the exact order, bind the artifact hash, and write the critique to `critique_path`.
8. Submit the critique. On failure, request the next work order and author a materially changed candidate using its named `variation_strategy` and the failed evidence. Do not merely append negative tokens.
9. Continue until the stage passes, reaches a real human gate, or encounters a safety, authority, or irreconcilable contract boundary.
10. After a stage is sealed, immediately request the next work order. A passed Stage 04 must enter Stage 05 without asking for a separate pre-Stage-05 approval. After the configured Stage 05 gate is resolved, Stage 05.5 must run without adding another human gate and then flow directly into Stage 06.

## Gate behavior

- `normal` is the default. Preserve human gates after Stages 01, 05, 06, 07, and 08. Stages 02–04 use AI preflight and continue automatically.
- `fast_track` exists only after explicit user selection. It auto-continues internal creative decisions and AI reviews through Stage 08.
- Attempt 10 may be accepted automatically only in fast-track, only for explicitly recorded non-safety quality defects. Never auto-accept a safety, authority, or contract failure.
- Neither mode authorizes publishing, uploading, messaging, purchasing, account changes, or other external side effects.

## Persistence rules

- Do not pause because an artifact is imperfect while attempts remain. Route it through `$video-pipeline-recovery` and continue.
- Do not ask a human to choose among multiple speculative candidates. Generate one candidate, review it, and retry only after failure.
- Preserve every failed artifact, critique, file, prompt, and receipt under its attempt directory.
- Independent image jobs may be delegated to subagents when the image skill allows it, but the main agent must assemble the artifact, run final checks, and advance state.
- Never delegate one stage's authoritative state transition or receipt finalization.

## Stop conditions

Stop only for a configured normal-mode human gate, missing authority, safety boundary, unrecoverable upstream contradiction, missing required external credential or service, or attempt exhaustion not eligible for fast-track acceptance. Report the exact state and resume command; do not describe an ordinary retry as a blocker.
