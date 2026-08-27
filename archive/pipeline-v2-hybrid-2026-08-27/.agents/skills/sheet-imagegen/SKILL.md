---
name: sheet-imagegen
description: Generate or regenerate this project's 02-sheet reference boards at the contract-declared native Codex raster and high quality, parallelizing independent manifest jobs across subagents when possible, then validate source pixels and finalize receipts. Use for interactive API-key-free sheet rendering in Codex desktop, CLI, or IDE; do not use for unattended batches.
---

# Sheet ImageGen

Render existing, compiler-authored `02-sheet/prompts/*.json` prompt packs with Codex built-in image generation at the contract-declared raster and `high` quality, preserving the pipeline's contract and receipt trail. A valid pack uses `sheet-prompt-pack.v2`, declares `structured-meta-prompt.v1`, and binds the writer rules, contract sheet policy, kind spec, visual definition, clauses, full meta prompt, and writer response by hash. The current default is `1672x941` landscape or `941x1672` portrait, based on the native file returned by Codex ImageGen in this project.

Read the attempt execution mode before work. Sheet semantic readiness already
uses recorded AI preflight in both modes. In fast-track, immediately continue
to the next stage after the receipt and contract gate pass; do not turn the
completion report into an approval request. Missing mode remains normal and
does not authorize replacing an already adopted sheet.

## Workflow

1. Resolve the requested attempt directory. Do not infer permission to replace an existing adopted sheet.
2. Confirm every requested element already has a valid compiler-authored prompt pack. If a pack is missing, generate it with the local deterministic structured compiler. This binds the writer rules, contract policy, kind spec, visual definition, scoped clauses, and full meta prompt by hash without an API key:

   ```bash
   PYTHONDONTWRITEBYTECODE=1 uv run --project . --no-editable ai-video-sheets ATTEMPT --generator codex --compose-only
   ```

   Re-run this command when a pack is legacy, stale, or lacks structured-meta-prompt provenance. Never draft, repair, summarize, or replace the pack by hand. The optional `--generator api --compose-only` lane may still be used only when the user explicitly chooses API-based prose composition.

3. Prepare a work order from the project root:

   ```bash
   PYTHONDONTWRITEBYTECODE=1 uv run --project . --no-editable ai-video-sheets ATTEMPT --generator codex
   ```

   Add `--only ELEMENT...` or `--kind KIND...` when requested. Add `--draft` only when the user explicitly wants a separately tracked draft; this project's sheet contract still requires `high`. Add `--force` only when the user explicitly requested replacement; finalization moves the former output under `02-sheet/rejected/`.
4. Read the returned manifest. If `jobs` is zero, report the skipped existing outputs and stop.
5. Assign every `job_id` exactly once. When at least two jobs are ready and collaboration slots are available, delegate different jobs to separate subagents and process remaining jobs locally. Give each subagent the exact attempt path, manifest path, `job_id`, exact `imagegen_prompt`, `requested`, `quality`, `candidate_path`, and this skill path. A subagent owns only its assigned job: it must not process another job, change the prompt pack or manifest, finalize, write to `output/`, or adopt a sheet. Run jobs in waves when they exceed available slots. The main agent alone tracks assignments, handles failed workers, and finalizes after all candidates exist. Before reassigning a failed or timed-out job, interrupt its prior owner and confirm that owner is no longer running; never assign a job while its prior owner is still running or has unknown status.
6. For every production job, verify `requested` matches the attempt contract—currently `1672x941` landscape or `941x1672` portrait—and `quality` is `high`. If not, stop and report that the attempt contract must be corrected; do not silently choose another raster.
7. Start with attempt 1 using the exact `imagegen_prompt`. Save it at the path
   obtained from `retry_harness.attempt_path_pattern`. Inspect it immediately
   against every ordered `retry_harness.acceptance_criteria` item and write a
   `sheet-image-ai-attempt-review.v1` JSON with concrete evidence. Record it:

   ```bash
   PYTHONDONTWRITEBYTECODE=1 uv run --project . --no-editable ai-video-sheets ATTEMPT \
     --generator codex --record-ai-review MANIFEST --review-file ATTEMPT_REVIEW
   ```

8. On `retry_required`, use only the returned `imagegen_prompt`,
   `variation_strategy`, and `candidate_path` for the next single generation.
   Every retry preserves the structured prompt pack and render contract while
   varying the failed-criterion repair strategy. Continue without requesting
   confirmation until pass or attempt 10. Never fan out variants. Attempt 10 is
   retained for semantic review if all ten fail.
9. The runner copies the passing or tenth image to `candidate_path`. Keep every
   attempt and the retry log as evidence; never write directly to `output/`.
10. After every candidate exists, the main agent finalizes once with the same manifest and the actual surface (`desktop`, `cli`, `ide`, or `cloud`):

   ```bash
   PYTHONDONTWRITEBYTECODE=1 uv run --project . --no-editable ai-video-sheets ATTEMPT --generator codex --finalize-manifest MANIFEST --codex-surface SURFACE
   ```

11. Inspect every finalized sheet visually against all applicable checks in
`02-sheet/qa/semantic-review.json`. For each applicable check, replace
`human_review_required` with `passed` or `failed`, set `reviewer` to
`codex-ai-sheet-preflight`, and record concrete visual evidence. Do not mark a
check passed merely because the pixels exist. If a detailed semantic check
fails after the generic image review, prepare a fresh `--force` manifest for
only that element and carry the failed check and evidence into the next varied
attempt. Count all attempts toward the same ten-attempt budget. When every check passes, run
the following without asking the user:

   ```bash
   PYTHONDONTWRITEBYTECODE=1 uv run --project . --no-editable ai-video-sheets ATTEMPT \
     --approve-references --review-mode ai_preflight --by codex-ai-sheet-preflight
   ```

12. Run `PYTHONDONTWRITEBYTECODE=1 uv run --project . --no-editable python -m ai_video_pipeline.contract_gate ATTEMPT` and report the generated paths, receipt, and any warning.

## Boundaries

- Codex mode must not read `OPENAI_API_KEY`, call the Images API, or fall back to API mode.
- Codex `--compose-only` uses the repository's deterministic structured compiler and must report `api_called: false`.
- Compiler-authored prompt packs are required. Missing hashes, legacy schemas, and handwritten packs are blockers. Do not invent or backfill provenance and do not create an ad-hoc prompt as a workaround.
- The Python command prepares and finalizes files. The actual image is generated only by Codex's interactive image-generation capability.
- Sheet semantic readiness is an AI visual preflight and must not pause for user approval.
- Independent sheet jobs may run concurrently, but one job has one owner and only the main agent may finalize the shared manifest.
- Every sheet uses the shared adaptive harness: one image, immediate AI review,
  a distinct failed-criterion prompt variation, and at most ten total attempts.
- `high` is a quality request, not proof of pixel dimensions. Finalization accepts minor provider variance up to 1% and 16 pixels per axis, normalizes it to the exact contract raster, and records the source dimensions and fit. A larger deficit is rejected and left under `qa/codex/candidates/`.
- Plates are not sheets. A future `05-plate` workflow must use the contract's `plate` image plan, which requests a provider size near the native video frame and delivers the exact `frame`; never inherit the sheet raster.
- Use API mode for CI, unattended operation, or large batches only when the user explicitly chooses it.
