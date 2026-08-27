---
name: plate-imagegen
description: Immediately continue a successful 04-shot-design handoff into this project's production 05-plate workflow, fulfilling Stage-03/04 reference debt and interaction manuals with automatic AI preflight promotion before sequentially AI-reviewed start plates, while parallelizing independent jobs across subagents. In normal mode preserve final human plate review; in explicitly selected fast-track mode apply AI review and continue automatically.
---

# Stage 05 ImageGen

Render only a manifest prepared by `ai_video_pipeline.stage5`. The Python runner
owns contracts, paths, hashes, pixel validation, promotion, and receipts. This
skill only performs the interactive ImageGen calls and saves their raw results.

Before preparation, read the attempt execution mode with `ai-video-mode
<attempt> show`. Missing mode is normal. Never set fast-track unless the user
explicitly requested it; the pipeline-recovery-harness owns that opt-in.

## Stage 04 transition

When a pipeline run has just completed `04-shot-design` with `form_ok: true` and
its `stage05_handoff.human_confirmation_required` is false, invoke this workflow
immediately in the same task. Do not summarize stage 04 and wait for the user,
ask whether stage 05 should start, or treat non-blocking approval warnings as a
pause. Run the stage-05 audit first; only objective blockers returned by that
audit may stop the transition.

## Workflow

1. Run the input audit. If the only blocker is
   `stage02-semantic-approval-required` and canonical sheets exist, use the
   installed `sheet-imagegen` AI semantic-preflight procedure on those existing
   sheets, then rerun this audit without asking the user. Proceed through
   `premise-human-approval-not-recorded` because it is explicitly non-blocking.
   Stop only for remaining objective blockers; do not invent missing
   interaction facts or mark upstream human reviews approved.

   ```bash
   PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m ai_video_pipeline.stage5 \
     <attempt> --audit
   ```

2. Prepare 5A `references` first. This includes Stage-03 reference debt and
   Stage-04 interaction manuals. If the audit says no reference job is required,
   prepare 5B `plates`. A required reference does not wait for user approval:
   generate it, run the AI preflight in step 9, and continue to plates
   automatically after the runner promotes it.

   ```bash
   PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m ai_video_pipeline.stage5 \
     <attempt> --prepare references
   ```

3. For a plate manifest, complete the global reference-preflight wave before
   assigning or generating any start image. Read every unique item in
   `reference_preflight.references` and inspect its image against every item in
   `reference_preflight.criteria`. When at least two references need review and
   collaboration slots are available, different subagents may inspect different
   `reference_id` values concurrently; they must return only their exact binding,
   pass/fail criteria, and concrete visual evidence. The main agent combines all
   results, in manifest order, into one JSON object with schema
   `stage5-plate-reference-preflight.v1`, the exact `manifest_id`, every complete
   reference binding, per-reference `decision` and `criteria`, overall
   `decision`, `reviewer`, and `reviewed_at`, then records it:

   ```bash
   PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m ai_video_pipeline.stage5 \
     <attempt> --record-reference-review <manifest.json> --review-file <reference-review.json>
   ```

   Do not call ImageGen, create an attempt image, or assign a start-image job
   before this command returns `reference_preflight_passed`. If it returns
   `reference_repair_required`, repair canonical stage-02 references through the
   `sheet-imagegen` workflow and 5A supplemental references through this workflow,
   then prepare a fresh plate manifest and repeat the entire reference wave.
   Never backfill a reference review after start-image generation.

4. After the global reference barrier passes, read the returned manifest and
   assign each image-generation job exactly once. When at least
   two jobs are ready and collaboration slots are available, delegate different
   `job_id` values to separate subagents and process remaining jobs locally.
   Give each subagent the exact attempt path, manifest path, `job_id`, prompt,
   ordered reference paths, candidate path contract, and this skill path. A
   subagent owns only its assigned job: it must not process another job, edit
   the manifest, finalize the manifest, apply human review, or approve an
   upstream/manual asset. Run additional jobs in waves when there are more jobs
   than available slots. The main agent alone tracks assignments, handles
   failed workers, and performs finalization after every assigned job finishes.
   Before reassigning a failed or timed-out job, interrupt its prior owner and
   confirm that owner is no longer running. Never assign a job while its prior
   owner is still running or has unknown status.

5. Manual jobs use `imagegen_prompt` once. For each
   plate job, generate only attempt 1 with the exact `imagegen_prompt`; do not
   summarize, rewrite, omit, or add instructions, and do not fan out three
   candidates. Attach every `reference_images[].path` in ascending `order` and
   treat those files as references, not edit targets.

6. For a plate, copy the generated project-bound PNG to the path obtained by
   formatting `retry_harness.attempt_path_pattern` with the current 1-based
   attempt number. Do not resize it yourself; the runner normalizes provider
   variance up to 1% and 16 pixels per axis and rejects a larger deficit.

7. Inspect that one plate image visually against every criterion in
   `retry_harness.acceptance_criteria`, with every ordered reference image open
   again during the comparison. The criteria include both the shot's start-state
   requirements and explicit identity/topology/material/geometry agreement with
   the approved reference set. Write a single-attempt JSON with schema
   `stage5-plate-ai-attempt-review.v1`, the exact `job_id`, `decision` (`pass`
   only when every criterion passes), ordered `criteria` entries with
   `criterion`, `status`, and concrete `evidence`, plus `feedback`, `reviewer`,
   and `reviewed_at`. A failed attempt before attempt 10 needs concise corrective
   feedback. Record it through the runner:

   ```bash
   PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m ai_video_pipeline.stage5 \
     <attempt> --record-ai-review <manifest.json> --review-file <attempt-review.json>
   ```

8. If the runner returns `retry_required`, the same job owner uses only its returned
   `imagegen_prompt`, `candidate_path`, and original ordered references for the
   next single generation, then repeat the visual review. The returned retry
   prompt preserves the complete structured base prompt, appends the previous
   failed-criterion feedback, and names a distinct `variation_strategy` for that
   attempt. Continue without asking for confirmation and stop immediately on
   `pass`. Never exceed ten total attempts. If attempt 10 also fails, the runner
   retains attempt 10 as `max_attempts_exhausted`. Normal mode sends it to human
   review; fast-track records the remaining non-safety failures as accepted
   defects in the final AI review packet and continues.

9. Once every plate job returns `selected_for_human_review`, or every manual
   job has its candidate at `candidate_path`, finalize the same manifest:

   ```bash
   PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m ai_video_pipeline.stage5 \
     <attempt> --finalize-manifest <manifest.json> --codex-surface desktop
   ```

10. For a finalized manual manifest, inspect both `clean_board.path` and
   `annotated_qa_board.path` against every criterion in the generated manual
   review packet. Fill each criterion with `pass` or `fail` and concrete visual
   evidence, set `decision` to `approved` only when all criteria pass, set
   `reviewer` to `codex-ai-manual-preflight`, set `reviewed_at`, and keep
   `review_mode: ai_preflight`, `human_approval_required: false`, and
   `auto_approve_allowed: true` unchanged. Apply the packet with
   `--apply-review` without asking the user. If it fails, regenerate and inspect
   again, varying the failed-criterion correction through the shared adaptive
   strategy list, for at most ten total manual attempts. After ten objective
   failures, report the failed criteria as a production defect; do not ask the
   user to perform the same review. Once all manuals pass, immediately prepare
   the plate manifest.

11. For a finalized plate manifest, branch only on its recorded execution mode.
   In normal mode, show the generated review packet and selected image to the
   user, including whether selection came from AI pass or ten failed attempts.
   Do not fill the human reviewer, decision, criteria, or screen-direction
   fields; apply only after the human completes the packet.

   In fast-track, inspect the selected image again with every ordered reference
   and fill the packet yourself. Use `review_mode: ai_fast_track`,
   `human_approval_required: false`, `auto_approve_allowed: true`, a reviewer
   beginning `codex-ai-fast-track`, and concrete evidence for every criterion.
   Mark a criterion `pass` when supported. Only after attempt 10 may a remaining
   non-safety quality failure be `accepted_defect`, with evidence and a matching
   entry in `accepted_defects`. Resolve required screen direction from the shot
   contract and selected image, recording normalized coordinates and depth
   intent; do not fabricate values without visual/contract evidence. Set the
   decision, apply with `--apply-review`, and immediately start stage 06 without
   asking the user.

## Invariants

- Production generates only first plates; never generate an end plate.
- Attach all canonical stage-02 boards listed in the manifest. A supplemental
  manual never replaces one.
- Clean Stage-03 reference-debt boards and interaction manuals precede plates
  and are promoted by recorded AI preflight; they do not require user approval.
- Every unique plate reference is visually reviewed first. All references must
  pass the manifest-wide barrier before any start image is assigned or generated.
- Start-image AI review must compare the candidate against the same approved
  reference set; a start-only review without references is invalid.
- Independent jobs may run concurrently, but one job has one owner and only the
  main agent may finalize the shared manifest.
- Plate generation is sequential: one image, AI review, then retry only on
  failure; ten attempts total, with attempt 10 used after ten failures.
- Retry corrections never replace or rewrite the structured base prompt, and
  every retry uses the manifest-declared distinct variation strategy.
- A finalized candidate becomes an approved output only after the mode-bound
  review packet is applied: human review in normal, AI review in fast-track.
- Never use the API fallback without an explicit user request.
