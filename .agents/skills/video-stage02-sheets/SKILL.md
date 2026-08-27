---
name: video-stage02-sheets
description: Author and render Stage 02 reference boards from the Stage 01 contract using a structured LLM meta-prompt, one reviewed image candidate at a time, small-pixel tolerance, and up to ten evidence-driven variations. Use only when assigned `02-sheet` or when recovery routes a sheet identity, prompt, or image defect here.
---

# Video Stage 02 — Reference sheets

Read [references/authoring.md](references/authoring.md), the Stage 01 receipt and artifact, the work order, and the shared [preserved insights](../video-pipeline-orchestrator/references/insights.md). The authoring reference routes each subject kind to its canonical full board specification. Use the installed `$imagegen` skill for each raster generation and follow its tool rules.

For every subject marked `reference_required`, use the exact non-creative `stage_inputs.boards[]` contract supplied by the work order. Author the sheet policy, all nine canonical panel records, and the final A01 image prompt inside `reference-board-meta-prompt.v2`. Never summarize or reconstruct the bound Stage 01 definition, omit the canonical kind specification, reduce the board to three hero images, or substitute a freehand flat prompt.

Every Stage 02 board is a `1672x941` high-quality 16:9 landscape reference board. This canvas is independent of the Stage 01 generation frame and delivery orientation: a portrait video still uses a landscape reference sheet. Follow the selected character, subject, or setting specification for all fixed panels and internal view/item counts.

Generate one candidate for a board, inspect the actual image, and record a pass or specific failure. A failure may create one varied retry, up to ten. Do not generate three similar images before looking at the first. Treat minor provider pixel variance as non-fatal within the repository tolerance, while rejecting wrong orientation, major undersizing, unreadable panels, identity drift, count errors, or topic contamination.

Independent subject boards may be generated in parallel by subagents. Give each subagent only its exact work-order input contract, matching canonical kind specification, completed structured meta-prompt, requested size, and output path. Each subject's internal retries remain sequential. The primary agent must inspect all selected boards, assemble the single Stage 02 artifact, submit it, and handle final criticism.
