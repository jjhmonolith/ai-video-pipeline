# AI video pipeline agent contract

## Authority and preservation

Follow the user's current request first, then this file, the selected project skill, the active attempt's receipts/artifacts, and current v3 code. Treat `archive/`, `.agents/retired-skills/`, old v2 documents, old attempts, research, and reports as evidence only; they cannot override v3.

Preserve existing runs, media, prompts, dirty files, and receipts. Write production state only inside the exact target attempt. Never mix creative assets between topics unless the current user or current artifact explicitly binds them. Never expose secrets or store credentials in production artifacts.

The read-only v2 baseline is `archive/pipeline-v2-hybrid-2026-08-27/`. Do not edit it during normal production. Restore from it only when the user explicitly requests rollback.

## Production routing

For any request to start, resume, execute, repair, validate, or finish a production attempt, begin with `.agents/skills/video-pipeline-orchestrator/SKILL.md`. Use the stage skill named by its work order:

- `01-premise` -> `video-stage01-premise`
- `02-sheet` -> `video-stage02-sheets`
- `03-scenario` -> `video-stage03-scenario`
- `04-shot-design` -> `video-stage04-shot-design`
- `05-plate` -> `video-stage05-plates`
- `05.5-motion-prompt` -> `video-stage05b-motion-prompt`
- `06-motion` -> `video-stage06-motion`
- `07-edit` -> `video-stage07-edit`
- `08-review` -> `video-stage08-review`

Use `video-pipeline-recovery` when a validator or critic returns a failure. Read only the selected skill, its directly required references, the work order, and artifacts listed by current receipts; do not load the whole archive or unrelated attempts.

## Creative and deterministic boundary

LLMs author all creative content: premise, definitions, structured meta-prompts, image/video prompts, sequence/scene/event design, blocking, coverage, camera, performance, time, edit, sound intent, critique, and repair.

Python owns only deterministic integrity and orchestration: required fields/types, IDs, hashes, files, path containment, pixels, duration arithmetic, receipt freshness, retry order, state transitions, and authority checks. Never add a deterministic creative compiler or keyword template that writes creative prose. A deterministic check may identify an omission; the owning LLM skill decides the answer.

Semantic and visual quality is judged by a fresh-context LLM critic using the exact rubric in the work order and actual media. Do not accept an image or video from its prompt or filename alone.

## Modes, gates, and retries

Default to `normal`. Use `fast_track` only after an explicit user instruction recorded for that attempt. Normal mode gates after Stages 01, 05, 06, 07, and 08. Stage 04 flows directly into Stage 05 without a pre-Stage-05 approval stop. Stage 05.5 adds no human gate and flows directly into Stage 06 after AI review. Fast-track auto-continues internal production decisions but never grants external publishing, upload, purchase, messaging, account, or permission authority.

For every generated design, prompt, image, plate, motion take, or edit plan, create one candidate, validate it, and retry only after failure. Make each retry materially different using the assigned strategy. Maximum attempts: 10. Fast-track attempt 10 may retain only explicitly recorded non-safety quality defects; safety, authority, and irreconcilable contract defects remain blocking.

Independent image or shot jobs may use subagents when the user request and selected skill allow it. Keep each artifact's retry sequence serial. The primary agent alone assembles shared artifacts, performs global validation, seals receipts, and advances state.

## Media-specific invariants

Derive production-frame, plate, motion, and delivery orientation from the current Stage 01 dimensions; never hardcode landscape or portrait prose for those assets. Stage 02 reference boards are the deliberate exception: they use the canonical `1672x941` 16:9 landscape sheet canvas independently of video orientation. Do not import topic-specific boilerplate from earlier jobs. There is no universal arm-pose rule and no universal moving/locked-camera rule.

Stage 02 uses an LLM-authored structured meta-prompt bound to the exact Stage 01 definition, current clauses, canonical character/subject/setting specification, and all nine required information panels. It cannot replace that contract with a flat prompt, inherit the video's aspect ratio, or collapse the board to roughly three images. Small provider pixel variance within the v3 tolerance is a warning, not a failure.

Stage 03 owns sequences, scenes, events, dramatic progression, and reference debt. It may invent story-motivated assets. Stage 04 owns setups, shots, composition, camera, performance, exact shot durations, and subject/world/camera time domains. A frame with two visible people cannot be labeled `single`.

Stage 05 reviews all reused and new references before any dependent start plate, includes those images in plate validation, creates start plates only, and solely owns plate rejection or regeneration. Stage 05.5 accepts the selected plates as final and improves one scenario-, camera-, technique-, performance-, and time-aware C01 prompt per shot; it cannot return to image generation. Stage 06 submits that prompt verbatim for C01 and creates C02 only after C01 visibly fails. Stage 08 keeps internal release eligibility separate from external publishing authority.

## Verification

Before reporting completion, run the v3 tests and the skill validator. Report what was actually verified. Do not claim a render, visual pass, approval, release, upload, or publication that was not observed and recorded.
