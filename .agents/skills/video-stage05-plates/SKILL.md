---
name: video-stage05-plates
description: Execute Stage 05 immediately after shot design by fulfilling new reference sheets and interaction manuals, reviewing the complete reused-plus-new reference set, then generating one reviewed start plate per shot with those references and up to ten varied retries. Use only when assigned `05-plate` or recovery routes reference or plate defects here.
---

# Video Stage 05 — References and start plates

Read [references/authoring.md](references/authoring.md), every upstream receipt and current artifact, the work order, and the shared [preserved insights](../video-pipeline-orchestrator/references/insights.md). Use the installed `$imagegen` skill for every generated reference or plate.

Run Stage 05 in two strict phases. In 5A, inventory Stage 02 boards plus every Stage 03 `NEW-*` debt and every Stage 04 interaction or state requirement. Reuse valid approved boards, generate missing sheets or manuals one candidate at a time, and visually review each. Then run one global preflight over every unique reference image.

Only after 5A passes may 5B begin. For each shot, bind the exact reference images required by `required_reference_subject_ids`, write a start-state prompt from the Stage 04 contract, generate one start plate, and inspect it against both the shot contract and the actual reference images. Production creates no end plates.

Stage 05 is the sole owner of plate acceptance and regeneration. Resolve every material plate defect inside this stage's sequential image harness before selection. Once the package passes, downstream Stage 05.5 must treat the selected plates as final and may adapt only the video-generation prompt—not reopen image review.

Independent reference or plate jobs may use subagents after their dependencies are satisfied. Each job retries sequentially; the primary agent owns the global reference barrier, cross-job consistency, artifact assembly, and state submission. In normal mode, the completed Stage 05 package is the human review point—not a pause before starting Stage 05.
